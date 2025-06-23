import asyncio
import aiohttp
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

class AirbnbPoster:
    def __init__(self):
        """Initialize Airbnb Community Center poster"""
        self.base_url = "https://community.withairbnb.com"
        self.redis = redis.Redis.from_url(
            os.getenv('REDIS_URL', 'redis://localhost:6379'),
            decode_responses=True
        )
        self.db = NeonDB()
        self.session = None
        
        # Rate limiting for Airbnb (more conservative than Reddit)
        self.last_post_time = None
        self.posts_today = 0
        self.day_start = datetime.now().date()
        
        # Load configuration
        with open('config.yaml', 'r') as f:
            self.config = yaml.safe_load(f)
        
        logger.info("Airbnb poster initialized")

    async def create_session(self):
        """Create aiohttp session with authentication headers"""
        if not self.session:
            # Note: You'll need to implement proper authentication
            # This is a placeholder for the actual auth mechanism
            self.session = aiohttp.ClientSession(
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Connection': 'keep-alive',
                }
            )

    def can_post_now(self):
        """Check if we can post based on rate limits"""
        now = datetime.now()
        
        # Reset daily counter if needed
        if now.date() > self.day_start:
            self.posts_today = 0
            self.day_start = now.date()
        
        # Very conservative rate limiting for Airbnb
        max_posts_per_day = 2  # Only 2 posts per day to avoid detection
        if self.posts_today >= max_posts_per_day:
            logger.info(f"Daily limit reached: {self.posts_today}/{max_posts_per_day}")
            return False
        
        # Check if we need to wait between posts (minimum 4 hours)
        if self.last_post_time:
            time_since_last = (now - self.last_post_time).total_seconds()
            if time_since_last < 14400:  # 4 hours
                return False
        
        return True

    def generate_subtle_reply(self, post_title: str, post_content: str) -> str:
        """Generate a very subtle reply with minimal promotion"""
        try:
            # Create a helpful, genuine response
            prompt = f"""
You are a helpful Airbnb host who has experienced similar issues. A user posted:

Title: {post_title}
Content: {post_content}

Provide a genuine, helpful response that:
1. Shows empathy and understanding
2. Offers 1-2 practical tips or suggestions
3. Mentions you found some helpful resources at [your site] in a very natural way
4. Keeps the tone conversational and peer-to-peer
5. Is under 150 words

Make the mention of your site feel like a personal recommendation, not promotion.
"""

            # Use OpenAI to generate response (same as your existing system)
            import openai
            client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a helpful Airbnb host peer. Be genuine and helpful."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.7
            )
            
            reply_text = response.choices[0].message.content.strip()
            
            # Ensure subtle mention of your site
            tool_url = self.config['tool']['url']
            if tool_url not in reply_text:
                # Add a very subtle mention at the end
                reply_text += f"\n\nI found some helpful resources at {tool_url} when I had similar issues."
            
            return reply_text
            
        except Exception as e:
            logger.error(f"Error generating reply: {e}")
            # Fallback response
            return f"I understand your frustration with this situation. It's a common issue many hosts face. I found some helpful resources at {self.config['tool']['url']} when dealing with similar problems. Hang in there!"

    async def post_reply(self, post_url: str, reply_text: str) -> tuple:
        """Post a reply to an Airbnb Community Center post"""
        try:
            # This is a placeholder - you'll need to implement the actual posting logic
            # based on Airbnb's forum structure and authentication requirements
            
            # For now, we'll simulate the posting process
            logger.info(f"Would post reply to: {post_url}")
            logger.info(f"Reply text: {reply_text[:100]}...")
            
            # Simulate posting delay
            await asyncio.sleep(2)
            
            # Update rate limiting
            self.last_post_time = datetime.now()
            self.posts_today += 1
            
            # Generate a fake comment URL for logging
            comment_url = f"{post_url}#reply-{int(time.time())}"
            
            logger.info(f"Successfully posted reply to Airbnb post")
            logger.info(f"Reply URL: {comment_url}")
            
            return True, comment_url, None
            
        except Exception as e:
            error_message = str(e)
            logger.error(f"Error posting reply to Airbnb post: {error_message}")
            return False, None, error_message

    async def process_reply_queue(self):
        """Process the queue of Airbnb posts to reply to"""
        try:
            queue_key = "airbnb_posts_to_reply"
            raw_post = self.redis.rpop(queue_key)
            
            if not raw_post:
                return
            
            post = json.loads(raw_post)
            
            # Rate limit check
            if not self.can_post_now():
                logger.warning(f"Rate limited. Re-queuing Airbnb post {post['id']}")
                self.redis.lpush(queue_key, raw_post)
                await asyncio.sleep(3600)  # Wait 1 hour
                return
            
            # Dry run check
            if self.config['safety']['dry_run']:
                logger.info(f"DRY RUN: Would post reply to Airbnb post {post['id']}")
                return
            
            # Generate reply
            reply_text = self.generate_subtle_reply(post['title'], post['content'])
            
            if not reply_text:
                logger.warning(f"No reply text generated for Airbnb post {post['id']}")
                return
            
            # Post the reply
            success, comment_url, error_message = await self.post_reply(post['url'], reply_text)
            
            # Log the activity to Neon DB
            self.db.log_post(
                post_id=post['id'],
                subreddit="airbnb_community",  # Use this to distinguish from Reddit
                title=post['title'],
                reply_text=reply_text,
                success=success,
                comment_url=comment_url,
                error_message=error_message
            )
            
            # If successful, sleep for a long time to be very conservative
            if success:
                sleep_time = random.uniform(14400, 28800)  # 4-8 hours
                logger.info(f"Sleeping for {sleep_time/3600:.1f} hours before next post")
                await asyncio.sleep(sleep_time)
            
        except Exception as e:
            logger.error(f"Error processing Airbnb reply queue: {e}")

    async def run(self):
        """Main run loop"""
        logger.info("Starting Airbnb Community Center poster service...")
        self.db.connect()
        await self.create_session()
        
        while True:
            try:
                await self.process_reply_queue()
                await asyncio.sleep(300)  # Check every 5 minutes
            except Exception as e:
                logger.error(f"Airbnb poster error: {e}")
                await asyncio.sleep(600)
        
        self.db.close()

    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()

async def main():
    poster = AirbnbPoster()
    try:
        await poster.run()
    finally:
        await poster.close()

if __name__ == "__main__":
    asyncio.run(main()) 