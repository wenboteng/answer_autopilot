import asyncio
import asyncpraw
import yaml
import os
import logging
import redis
import json
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

class RedditListener:
    def __init__(self):
        """Initialize Reddit listener with async PRAW"""
        self.reddit = asyncpraw.Reddit(
            client_id=os.getenv('REDDIT_CLIENT_ID'),
            client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
            refresh_token=os.getenv('REDDIT_REFRESH_TOKEN'),
            user_agent=os.getenv('REDDIT_USER_AGENT', 'OTA_Forum_Bot/1.0')
        )
        
        # Load configuration
        with open('config.yaml', 'r') as f:
            self.config = yaml.safe_load(f)
        
        # Initialize Redis
        redis_url = os.getenv('REDIS_URL')
        if redis_url:
            self.redis = redis.from_url(redis_url, decode_responses=True)
            logger.info("Connected to Redis via URL")
        else:
            self.redis = redis.Redis(
                host=self.config['redis']['host'],
                port=self.config['redis']['port'],
                db=self.config['redis']['db'],
                decode_responses=True
            )
            logger.info("Connected to Redis via config.yaml")
        
        # Pre-compile keyword regex
        self.keywords = self.config['reddit']['keywords']
        self.target_subreddits = self.config['reddit']['target_subreddits']
        
        logger.info(f"Initialized listener with {len(self.keywords)} keywords")
        logger.info(f"Monitoring subreddits: {self.target_subreddits}")
    
    async def check_keywords(self, text):
        """Check if text contains any OTA keywords"""
        text_lower = text.lower()
        matched_keywords = [kw for kw in self.keywords if kw.lower() in text_lower]
        return matched_keywords
    
    async def is_already_processed(self, subreddit, thread_id):
        """Check if we've already processed this thread"""
        key = f"processed:{subreddit}:{thread_id}"
        return self.redis.exists(key)
    
    async def mark_processed(self, subreddit, thread_id):
        """Mark a thread as processed"""
        key = f"processed:{subreddit}:{thread_id}"
        ttl_days = self.config['redis']['ttl_days']
        self.redis.setex(key, ttl_days * 24 * 3600, "1")
    
    async def queue_for_reply(self, post_data):
        """Queue a post directly for the reply service"""
        queue_key = "posts_to_reply"
        self.redis.lpush(queue_key, json.dumps(post_data))
        logger.info(f"Queued post {post_data['id']} directly for reply")
    
    async def stream_posts(self):
        """Stream posts from target subreddits"""
        try:
            # Combine all target subreddits
            subreddit_names = "+".join(self.target_subreddits)
            subreddit = await self.reddit.subreddit(subreddit_names)
            
            logger.info(f"Starting stream for: {subreddit_names}")
            
            async for post in subreddit.stream.submissions(skip_existing=True, pause_after=0):
                if post is None:
                    continue
                
                try:
                    # Check if already processed
                    if await self.is_already_processed(post.subreddit.display_name, post.id):
                        continue
                    
                    # Check for keywords
                    post_text = f"{post.title} {post.selftext}"
                    matched_keywords = await self.check_keywords(post_text)
                    
                    if not matched_keywords:
                        continue
                    
                    # Skip posts with existing comments
                    if post.num_comments > 0:
                        continue
                    
                    # Prepare post data for reply
                    post_data = {
                        'id': post.id,
                        'title': post.title,
                        'content': post.selftext,
                        'subreddit': post.subreddit.display_name,
                        'url': f"https://reddit.com{post.permalink}",
                        'created_utc': post.created_utc,
                        'matched_keywords': matched_keywords,
                        'score': post.score,
                        'num_comments': post.num_comments,
                        'author': str(post.author) if post.author else '[deleted]',
                        'timestamp': datetime.now().isoformat()
                    }
                    
                    # Queue for reply service
                    await self.queue_for_reply(post_data)
                    
                    # Mark as processed to avoid duplicates
                    await self.mark_processed(post.subreddit.display_name, post.id)
                    
                    logger.info(f"Found relevant post: {post.title[:50]}... in r/{post.subreddit.display_name}")
                    
                except Exception as e:
                    logger.error(f"Error processing post {post.id}: {e}")
                    continue
                
        except Exception as e:
            logger.error(f"Error in stream: {e}")
            # Implement exponential backoff
            await asyncio.sleep(60)
            await self.stream_posts()
    
    async def run(self):
        """Main run loop"""
        logger.info("Starting Reddit listener service...")
        
        while True:
            try:
                await self.stream_posts()
            except Exception as e:
                logger.error(f"Listener error: {e}")
                await asyncio.sleep(30)

async def main():
    listener = RedditListener()
    await listener.run()

if __name__ == "__main__":
    asyncio.run(main()) 