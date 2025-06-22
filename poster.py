import asyncpraw
import yaml
import os
import logging
import redis
import json
import random
import time
from datetime import datetime, timedelta
from dotenv import load_dotenv
from database import NeonDB

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Load configuration
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

class RedditPoster:
    def __init__(self):
        """Initialize Reddit poster with async PRAW"""
        self.reddit = asyncpraw.Reddit(
            client_id=os.getenv('REDDIT_CLIENT_ID'),
            client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
            refresh_token=os.getenv('REDDIT_REFRESH_TOKEN'),
            user_agent=os.getenv('REDDIT_USER_AGENT', 'OTA_Forum_Bot/1.0')
        )
        
        # Load configuration from config.yaml
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
        
        self.db = NeonDB()
        
        # Rate limiting tracking
        self.last_post_time = None
        self.posts_this_hour = 0
        self.hour_start = datetime.now()
        
        # Get account karma
        self.account_karma = 0
        self.load_account_info()
        
        logger.info("Reddit poster initialized")
    
    async def load_account_info(self):
        """Load account information including karma"""
        try:
            me = await self.reddit.user.me()
            self.account_karma = me.link_karma + me.comment_karma
            logger.info(f"Account karma: {self.account_karma}")
        except Exception as e:
            logger.error(f"Error loading account info: {e}")
            # Still allow the bot to run, just with default karma
            self.account_karma = 0
    
    def can_post_now(self):
        """Check if we can post based on rate limits"""
        now = datetime.now()
        
        # Reset hourly counter if needed
        if now - self.hour_start > timedelta(hours=1):
            self.posts_this_hour = 0
            self.hour_start = now
        
        # Check hourly limit
        max_posts_per_hour = self.config['api']['reddit']['max_comments_per_hour']
        if self.account_karma < self.config['api']['reddit']['min_karma_for_unlimited']:
            if self.posts_this_hour >= max_posts_per_hour:
                logger.info(f"Hourly limit reached: {self.posts_this_hour}/{max_posts_per_hour}")
                return False
        
        # Check if we need to wait between posts
        if self.last_post_time:
            min_sleep, max_sleep = self.config['api']['reddit']['sleep_range']
            time_since_last = (now - self.last_post_time).total_seconds()
            if time_since_last < random.uniform(min_sleep, max_sleep):
                return False
        
        return True
    
    async def post_reply(self, post_id, reply_text):
        """Post a reply to a Reddit post"""
        try:
            # Get the submission
            submission = await self.reddit.submission(id=post_id)
            
            # Post the reply
            comment = await submission.reply(reply_text)
            
            # Upvote our own comment (API allows this)
            await comment.upvote()
            
            # Update rate limiting
            self.last_post_time = datetime.now()
            self.posts_this_hour += 1
            
            logger.info(f"Successfully posted reply to post {post_id}")
            logger.info(f"Reply URL: https://reddit.com{comment.permalink}")
            
            return True, comment.permalink, None
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error posting reply to post {post_id}: {error_message}")
            return False, None, error_message
    
    async def process_reply_queue(self):
        """Process the queue of posts to reply to"""
        try:
            queue_key = "posts_to_post"
            # Pop from the right, as listener pushes to the left
            raw_post = self.redis.rpop(queue_key)
            
            if not raw_post:
                # Queue is empty, nothing to do
                return
            
            post = json.loads(raw_post)
            reply_text = post.get('reply_text')
            
            # Rate limit check
            if not self.can_post_now():
                logger.warning(f"Rate limited. Re-queuing post {post['id']}")
                self.redis.lpush(queue_key, raw_post)
                await asyncio.sleep(60)
                return
            
            # Dry run check
            if self.config['safety']['dry_run']:
                logger.info(f"DRY RUN: Would post reply to {post['id']}: {reply_text[:100]}...")
                return
            
            # Make sure we have a reply
            if not reply_text:
                logger.warning(f"No reply text for post {post['id']}")
                return
            
            # Post the reply
            success, comment_url, error_message = await self.post_reply(post['id'], reply_text)
            
            # Log the activity to Neon DB
            self.db.log_post(
                post_id=post['id'],
                subreddit=post['subreddit'],
                title=post['title'],
                reply_text=reply_text,
                success=success,
                comment_url=comment_url,
                error_message=error_message
            )
            
            # If successful, sleep between posts to be safe
            if success:
                min_sleep, max_sleep = self.config['api']['reddit']['sleep_range']
                sleep_time = random.uniform(min_sleep, max_sleep)
                logger.info(f"Sleeping for {sleep_time:.1f} seconds before next post")
                await asyncio.sleep(sleep_time)
            
        except Exception as e:
            logger.error(f"Error processing reply queue: {e}")
    
    async def run(self):
        """Main run loop"""
        logger.info("Starting Reddit poster service...")
        self.db.connect() # Connect to Neon DB at startup
        
        while True:
            try:
                await self.process_reply_queue()
                await asyncio.sleep(15)  # Check every 15 seconds
            except Exception as e:
                logger.error(f"Poster error: {e}")
                await asyncio.sleep(30)
        
        self.db.close()

async def main():
    poster = RedditPoster()
    await poster.run()

if __name__ == "__main__":
    import asyncio
    asyncio.run(main()) 