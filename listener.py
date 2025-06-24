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
    "gyg", "getyourguide", "viator", "bokun", "booking.com", "airbnb", "expedia", "tripadvisor",
    "klook", "musement", "civitatis", "headout", "tiqets", "kkday", "vrbo", "homeaway", "flipkey",
    "turo", "getaround", "ota", "online travel", "travel platform", "booking platform"
]

CONTEXT_WORDS = [
    "tour operator", "tour vendor", "supplier", "vendor", "host", "property manager", "listing",
    "booking", "commission", "channel manager", "direct booking", "activity provider",
    "excursion", "short-term rental", "reservation", "payout", "fee", "platform fee", "api",
    "integration", "partner", "guide", "accommodation provider", "airbnb host", "tourism business"
]

# Subreddits that are highly relevant to tour vendors, operators, and hosts
TARGET_SUBREDDITS = [
    "TourOperators", "Tourism", "AirbnbHosts", "HostAdvice", "TravelIndustry",
    "SmallTourOperators", "PropertyManagement", "ShortTermRentals", "TourGuide"
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
        self.target_subreddits = TARGET_SUBREDDITS
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
        platform_matches = 0
        context_matches = 0
        for keyword in PLATFORM_KEYWORDS:
            if keyword in full_text or keyword in subreddit_lower:
                platform_matches += 1
                score += 10.0
        for keyword in CONTEXT_WORDS:
            if keyword in full_text:
                context_matches += 1
                score += 5.0
        # Require at least one platform and one context keyword
        if platform_matches > 0 and context_matches > 0:
            score += 20.0
        else:
            score = 0.0  # Not relevant if both not present
        # Bonus for multiple matches
        if platform_matches > 1:
            score += 10.0
        if context_matches > 1:
            score += 5.0
        # Subreddit-specific bonus
        if any(ota_term in subreddit_lower for ota_term in ["tour", "airbnb", "host", "operator"]):
            score += 5.0
        # Length bonus
        if len(full_text) > 200:
            score += 5.0
        return min(score, 100.0)

    def is_relevant(self, title: str, body: str, subreddit: str) -> bool:
        """
        Only consider a post relevant if it matches both a platform and a context keyword, and has a higher threshold.
        """
        score = self.calculate_relevance_score(title, body, subreddit)
        threshold = 40.0  # Stricter threshold for relevance
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