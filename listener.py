import asyncio
import asyncpraw
import yaml
import os
import logging
import redis
import json
import re
from datetime import datetime
from dotenv import load_dotenv
from config import Config

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=Config.LOG_LEVEL, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Compile regex patterns for efficiency
BRAND_PATTERNS = [
    re.compile(r"(gyg|get ?your ?guide).*(payout|commission|ranking|api|search)", re.IGNORECASE),
    re.compile(r"viator.*(payout|commission|ranking|api|search)", re.IGNORECASE),
    re.compile(r"airbnb (experience|experiences).*(host fee|ranking|visibility|api)", re.IGNORECASE),
    re.compile(r"booking\.com.*(experiences|tours).*(ranking|visibility|api)", re.IGNORECASE),
]

class RedditListener:
    def __init__(self):
        """Initialize Reddit listener"""
        self.reddit = asyncpraw.Reddit(
            client_id=Config.REDDIT_CLIENT_ID,
            client_secret=Config.REDDIT_CLIENT_SECRET,
            refresh_token=Config.REDDIT_REFRESH_TOKEN,
            user_agent=Config.REDDIT_USER_AGENT
        )
        self.target_subreddits = Config.TARGET_SUBREDDITS
        self.redis = redis.Redis.from_url(
            os.getenv('REDIS_URL', 'redis://localhost:6379'),
            decode_responses=True
        )
        logger.info("Connected to Redis for queuing.")
        logger.info(f"Monitoring subreddits: {', '.join(self.target_subreddits)}")

    def is_relevant(self, text: str) -> bool:
        """
        Check if a post is relevant based on compiled regex patterns.
        A post is relevant if it matches at least one brand+pain pattern.
        """
        # The sum() of booleans acts as a counter for matched patterns.
        hits = sum(bool(p.search(text)) for p in BRAND_PATTERNS)
        return hits > 0
    
    async def stream_posts(self):
        """Stream new posts from target subreddits."""
        subreddits_str = "+".join(self.target_subreddits)
        subreddit = await self.reddit.subreddit(subreddits_str)
        logger.info(f"Streaming posts from: r/{subreddits_str}")

        try:
            async for post in subreddit.stream.submissions(skip_existing=True):
                full_text = f"{post.title} {post.selftext}"

                if self.is_relevant(full_text):
                    logger.info(f"Found relevant post: '{post.title[:50]}...' in r/{post.subreddit.display_name}")
                    post_data = {
                        'id': post.id,
                        'title': post.title,
                        'content': post.selftext,
                        'subreddit': post.subreddit.display_name,
                        'url': post.url,
                        'created_utc': post.created_utc
                    }
                    # Push to Redis queue
                    self.redis.lpush("posts_to_reply", json.dumps(post_data))
                    logger.info(f"Queued post {post.id} to Redis for reply generation.")

        except Exception as e:
            logger.error(f"Error in post stream: {e}", exc_info=True)
            await asyncio.sleep(60)
    
    async def run(self):
        """Main run loop for the listener"""
        logger.info("Starting Reddit listener service...")
        while True:
            try:
                await self.stream_posts()
            except Exception as e:
                logger.error(f"Listener stream encountered a fatal error: {e}", exc_info=True)
                logger.info("Restarting stream after a 60 second delay...")
                await asyncio.sleep(60)

async def main():
    listener = RedditListener()
    await listener.run()

if __name__ == "__main__":
    asyncio.run(main()) 