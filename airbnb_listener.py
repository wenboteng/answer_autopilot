import asyncio
import aiohttp
import yaml
import os
import logging
import redis
import json
import re
from datetime import datetime, timedelta
from dotenv import load_dotenv
from bs4 import BeautifulSoup

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Airbnb Community Center keywords
AIRBNB_KEYWORDS = [
    "problem", "issue", "question", "help", "support", "trouble", "error",
    "payout", "commission", "booking", "review", "payment", "account",
    "listing", "guest", "host", "reservation", "cancel", "refund",
    "banned", "suspended", "discrimination", "complaint"
]

class AirbnbListener:
    def __init__(self):
        """Initialize Airbnb Community Center listener"""
        self.base_url = "https://community.withairbnb.com"
        self.target_forums = [
            "Help with your business",
            "Airbnb updates",
            "Community cafe"
        ]
        self.redis = redis.Redis.from_url(
            os.getenv('REDIS_URL', 'redis://localhost:6379'),
            decode_responses=True
        )
        self.session = None
        logger.info("Airbnb listener initialized")

    async def create_session(self):
        """Create aiohttp session with headers"""
        if not self.session:
            self.session = aiohttp.ClientSession(
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
                }
            )

    def is_relevant(self, title: str, content: str) -> bool:
        """Check if a post is relevant based on keywords"""
        full_text = f"{title} {content}".lower()
        
        # Check for Airbnb-related keywords
        keyword_count = sum(1 for keyword in AIRBNB_KEYWORDS if keyword in full_text)
        return keyword_count >= 2  # At least 2 keywords to be relevant

    async def fetch_forum_posts(self, forum_url: str) -> list:
        """Fetch recent posts from a forum"""
        try:
            async with self.session.get(forum_url) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    
                    posts = []
                    # Look for post elements (this will need adjustment based on actual HTML structure)
                    post_elements = soup.find_all('div', class_='post')
                    
                    for element in post_elements[:10]:  # Limit to 10 most recent
                        try:
                            title_elem = element.find('h3') or element.find('a', class_='title')
                            content_elem = element.find('div', class_='content') or element.find('p')
                            
                            if title_elem and content_elem:
                                title = title_elem.get_text(strip=True)
                                content = content_elem.get_text(strip=True)
                                
                                if self.is_relevant(title, content):
                                    post_id = element.get('data-post-id') or element.get('id')
                                    post_url = self.base_url + (title_elem.get('href') or '')
                                    
                                    posts.append({
                                        'id': post_id,
                                        'title': title,
                                        'content': content,
                                        'url': post_url,
                                        'forum': forum_url,
                                        'created_at': datetime.now().isoformat()
                                    })
                        except Exception as e:
                            logger.warning(f"Error parsing post element: {e}")
                            continue
                    
                    return posts
                else:
                    logger.warning(f"Failed to fetch forum {forum_url}: {response.status}")
                    return []
                    
        except Exception as e:
            logger.error(f"Error fetching forum {forum_url}: {e}")
            return []

    async def run(self):
        """Main run loop for monitoring Airbnb Community Center"""
        logger.info("Starting Airbnb Community Center listener...")
        await self.create_session()
        
        while True:
            try:
                logger.info("🔍 Checking Airbnb Community Center for new posts...")
                
                all_posts = []
                
                # Monitor target forums
                for forum in self.target_forums:
                    forum_url = f"{self.base_url}/t5/{forum.replace(' ', '-')}/bd-p/help"
                    posts = await self.fetch_forum_posts(forum_url)
                    all_posts.extend(posts)
                
                # Process new posts
                for post in all_posts:
                    redis_key = f"airbnb_processed:{post['id']}"
                    
                    if not self.redis.exists(redis_key):
                        logger.info(f"✅ Found relevant Airbnb post: '{post['title'][:50]}...'")
                        
                        # Queue for reply generation
                        self.redis.lpush("airbnb_posts_to_reply", json.dumps(post))
                        logger.info(f"Queued Airbnb post {post['id']} for reply generation.")
                        
                        # Mark as processed with 7-day expiry
                        self.redis.set(redis_key, 1, ex=int(timedelta(days=7).total_seconds()))
                
                logger.info(f"Finished Airbnb check. Found {len(all_posts)} relevant posts.")
                
                # Wait 10 minutes before next check (longer interval for forum scraping)
                logger.info("Sleeping for 10 minutes...")
                await asyncio.sleep(600)
                
            except Exception as e:
                logger.error(f"Airbnb listener error: {e}", exc_info=True)
                await asyncio.sleep(60)

    async def close(self):
        """Clean up resources"""
        if self.session:
            await self.session.close()

async def main():
    listener = AirbnbListener()
    try:
        await listener.run()
    finally:
        await listener.close()

if __name__ == "__main__":
    asyncio.run(main()) 