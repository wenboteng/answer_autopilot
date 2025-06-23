import asyncio
import asyncpraw
import yaml
import os
import logging
import redis
import json
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from config import Config

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=Config.LOG_LEVEL, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# --- New High-Precision Filtering Logic ---

# Context keywords identify the post as being from a vendor or about a vendor issue.
CONTEXT_WORDS = [
    # General Problems & Questions
    "problem", "issue", "question", "help", "support", "trouble", "error",
    # Vendor Identity
    "supplier", "vendor", "operator", "partner", "guide", "host",
    # Business & Technical Terms
    "payout", "commission", "ranking", "api", "search", "visibility", "fee",
    "account", "listing", "booking", "review", "payment"
]
CONTEXT_REGEX = "|".join(CONTEXT_WORDS)

# Compile regex patterns for efficiency.
# Each pattern requires a platform brand AND a context word.
BRAND_PATTERNS = [
    # Matches (GYG or Viator) followed by any of the context words.
    re.compile(fr"(gyg|get ?your ?guide|viator).*(?:{CONTEXT_REGEX})", re.IGNORECASE),
    
    # Matches (Airbnb Experience) followed by any of the context words.
    re.compile(fr"airbnb (?:experience|experiences).*(?:{CONTEXT_REGEX})", re.IGNORECASE),

    # Matches (Booking.com + Experience/Tour) followed by any of the context words.
    re.compile(fr"booking\.com.*(?:experience|tour).*(?:{CONTEXT_REGEX})", re.IGNORECASE),

    # Catches cases where the context word appears before the brand.
    # e.g., "As a supplier, I have a problem with GetYourGuide."
    re.compile(fr"(?:{CONTEXT_REGEX}).*(gyg|get ?your ?guide|viator|airbnb|booking\.com)", re.IGNORECASE)
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
    
    async def run(self):
        """Main run loop for the listener, polls for new posts."""
        logger.info("Starting Reddit listener service...")
        subreddits_str = "+".join(self.target_subreddits)
        subreddit = await self.reddit.subreddit(subreddits_str)

        while True:
            try:
                logger.info(f"❤️ Heartbeat: Checking for new posts in r/{subreddits_str}...")
                post_count = 0
                relevant_count = 0

                async for post in subreddit.new(limit=25):
                    post_count += 1
                    redis_key = f"processed_post:{post.id}"

                    if self.redis.exists(redis_key):
                        continue

                    full_text = f"{post.title} {post.selftext}"
                    if self.is_relevant(full_text):
                        relevant_count += 1
                        logger.info(f"Found relevant post: '{post.title[:50]}...' in r/{post.subreddit.display_name}")
                        post_data = {
                            'id': post.id,
                            'title': post.title,
                            'content': post.selftext,
                            'subreddit': post.subreddit.display_name,
                            'url': post.url,
                            'created_utc': post.created_utc
                        }
                        self.redis.lpush("posts_to_reply", json.dumps(post_data))
                        logger.info(f"Queued post {post.id} for reply generation.")
                    
                    # Mark post as processed with a 7-day expiry to keep Redis clean
                    self.redis.set(redis_key, 1, ex=int(timedelta(days=7).total_seconds()))

                logger.info(f"Finished check. Processed {post_count} posts, found {relevant_count} relevant.")
                
                # Wait for 5 minutes before the next poll
                logger.info("Sleeping for 5 minutes...")
                await asyncio.sleep(300)

            except Exception as e:
                logger.error(f"Listener loop encountered an error: {e}", exc_info=True)
                logger.info("Restarting loop after a 60 second delay...")
                await asyncio.sleep(60)

async def main():
    listener = RedditListener()
    await listener.run()

if __name__ == "__main__":
    asyncio.run(main()) 