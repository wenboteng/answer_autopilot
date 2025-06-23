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

# --- More Flexible Filtering Logic with Scoring ---
PLATFORM_KEYWORDS = [
    # OTA Platforms
    "gyg", "getyourguide", "viator", "booking.com", "airbnb", "expedia", "tripadvisor",
    "kayak", "hotels.com", "vrbo", "homeaway", "flipkey", "turo", "getaround",
    # Travel Platforms
    "klook", "musement", "civitatis", "headout", "tiqets", "klook", "kkday",
    # Generic terms
    "ota", "online travel", "travel platform", "booking platform"
]

CONTEXT_WORDS = [
    # General Problems & Questions
    "problem", "issue", "question", "help", "support", "trouble", "error", "app", "website",
    "how", "what", "why", "when", "where", "advice", "suggestion", "recommendation",
    
    # Business Terms
    "payout", "commission", "ranking", "api", "search", "visibility", "fee", "revenue",
    "account", "listing", "booking", "review", "payment", "earnings", "income",
    
    # Vendor/Supplier Terms
    "supplier", "vendor", "operator", "partner", "guide", "host", "property owner",
    "tour operator", "activity provider", "accommodation provider",
    
    # Customer Service
    "customer", "guest", "traveler", "tourist", "visitor", "client",
    "service", "experience", "trip", "tour", "activity", "excursion",
    
    # Technical Issues
    "bug", "glitch", "crash", "loading", "slow", "broken", "not working",
    "update", "sync", "integration", "connection", "login", "password",
    
    # Business Operations
    "marketing", "advertising", "promotion", "sales", "conversion", "leads",
    "pricing", "cost", "expense", "profit", "loss", "budget",
    
    # Travel Industry Terms
    "tourism", "travel", "vacation", "holiday", "destination", "attraction",
    "hotel", "resort", "apartment", "house", "room", "accommodation"
]

# Subreddits that are more likely to have OTA-related content
TARGET_SUBREDDITS = [
    "TourGuide", "AirbnbHosts", "TravelIndustry", "Arival", "tour_operator",
    "SmallBusiness", "Entrepreneur", "DigitalMarketing", "SEO", "Marketing",
    "Travel", "SoloTravel", "Backpacking", "Hosting", "PropertyManagement",
    "CustomerService", "Business", "Startups", "Freelance", "SideHustle"
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
        self.target_subreddits = TARGET_SUBREDDITS  # Use expanded list
        self.redis = redis.Redis.from_url(
            os.getenv('REDIS_URL', 'redis://localhost:6379'),
            decode_responses=True
        )
        logger.info("Connected to Redis for queuing.")
        logger.info(f"Monitoring subreddits: {', '.join(self.target_subreddits)}")

    def calculate_relevance_score(self, title: str, body: str, subreddit: str) -> float:
        """
        Calculate a relevance score (0-100) based on keyword matches.
        Higher score = more relevant.
        """
        full_text = f"{title} {body}".lower()
        subreddit_lower = subreddit.lower()
        
        score = 0.0
        
        # Platform keywords are weighted heavily (10 points each)
        platform_matches = 0
        for keyword in PLATFORM_KEYWORDS:
            if keyword in full_text or keyword in subreddit_lower:
                platform_matches += 1
                score += 10.0
        
        # Context keywords are weighted moderately (3 points each)
        context_matches = 0
        for keyword in CONTEXT_WORDS:
            if keyword in full_text:
                context_matches += 1
                score += 3.0
        
        # Bonus for having both platform and context keywords
        if platform_matches > 0 and context_matches > 0:
            score += 20.0
        
        # Bonus for multiple platform mentions
        if platform_matches > 1:
            score += 15.0
        
        # Bonus for multiple context mentions
        if context_matches > 2:
            score += 10.0
        
        # Subreddit-specific bonuses
        if any(ota_term in subreddit_lower for ota_term in ["tour", "travel", "airbnb", "hosting"]):
            score += 5.0
        
        # Length bonus (longer posts might be more detailed)
        if len(full_text) > 200:
            score += 5.0
        
        return min(score, 100.0)  # Cap at 100

    def is_relevant(self, title: str, body: str, subreddit: str) -> bool:
        """
        Check if a post is relevant using a more flexible scoring system.
        Lower threshold for inclusion.
        """
        score = self.calculate_relevance_score(title, body, subreddit)
        
        # Much lower threshold - anything with a reasonable score gets included
        threshold = 15.0  # Reduced from requiring both platform + context
        
        is_relevant = score >= threshold
        if is_relevant:
            logger.debug(f"Post scored {score:.1f}/100: '{title[:50]}...'")
        
        return is_relevant

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

                # Increased limit to check more posts
                async for post in subreddit.new(limit=50):
                    post_count += 1
                    redis_key = f"processed_post:{post.id}"

                    if self.redis.exists(redis_key):
                        continue

                    if self.is_relevant(post.title, post.selftext, post.subreddit.display_name):
                        relevant_count += 1
                        score = self.calculate_relevance_score(post.title, post.selftext, post.subreddit.display_name)
                        logger.info(f"✅ Found relevant post (score: {score:.1f}): '{post.title[:50]}...' in r/{post.subreddit.display_name}")
                        post_data = {
                            'id': post.id,
                            'title': post.title,
                            'content': post.selftext,
                            'subreddit': post.subreddit.display_name,
                            'url': post.url,
                            'created_utc': post.created_utc,
                            'relevance_score': score
                        }
                        self.redis.lpush("posts_to_reply", json.dumps(post_data))
                        logger.info(f"Queued post {post.id} for reply generation.")
                    
                    # Mark post as processed with a 7-day expiry to keep Redis clean
                    self.redis.set(redis_key, 1, ex=int(timedelta(days=7).total_seconds()))

                logger.info(f"Finished check. Processed {post_count} posts, found {relevant_count} relevant.")
                
                # Reduced wait time to check more frequently
                logger.info("Sleeping for 3 minutes...")
                await asyncio.sleep(180)

            except Exception as e:
                logger.error(f"Listener loop encountered an error: {e}", exc_info=True)
                logger.info("Restarting loop after a 60 second delay...")
                await asyncio.sleep(60)

async def main():
    listener = RedditListener()
    await listener.run()

if __name__ == "__main__":
    asyncio.run(main()) 