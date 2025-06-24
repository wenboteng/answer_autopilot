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

# --- Overhauled Listening Filter for Tour Vendors/Operators/Hosts ---

# Subreddit weights (for scoring)
SUBREDDIT_WEIGHTS = {
    # Core
    "TourGuide": 15,
    "TravelIndustry": 15,
    "AirbnbHosts": 15,
    "ShortTermRentals": 15,
    "TravelAgents": 12,
    # Peripheral
    "SmallBusiness": 6,
    "Entrepreneur": 6,
    "PropertyManagement": 6,
}

# Subreddits to monitor (must exist and be public)
TARGET_SUBREDDITS = list(SUBREDDIT_WEIGHTS.keys())

# Platform keywords (regex, case-insensitive)
PLATFORM_REGEX = re.compile(r"gyg|get\s?your\s?guide|viator\b|booking\.com\b|airbnb\b|airbnb experiences|expedia\b|tripadvisor(\s+experiences)?|klook\b|musement\b|civitatis\b|headout\b|tiqets\b|kkday\b|vrbo\b|homeaway\b|flipkey\b|turo\b|getaround\b|bokun\b|ota\b|online\s+travel|tour(s)?bylocals|gowithguide|tourradar|trip\.com|agoda\b", re.I)

# Vendor-side context keywords (regex, case-insensitive)
CONTEXT_REGEX = re.compile(r"(operator|supplier|vendor|host|guide|activity\s+(provider|operator)|tour\s+(operator|business)|experience\s+(provider|host)|listing|inventory|channel\s+manager|commission|payout|net\s+rate|platform\s+fee|integration|api|dashboard|management\s+center|direct\s+booking|ranking|availability|extranet|partner\s+portal|supplier\s+api|property\s+manager|short[-\s]term\s+rental|reservation)", re.I)

# Negative keywords (regex, case-insensitive)
NEGATIVE_REGEX = re.compile(r"(scammed|refund(ed)?|cancellation\s+policy|trip\s+(report|review)|honeymoon|travel\s+tips|packing\s+list|lost\s+luggage)", re.I)

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

    def calculate_relevance_score(self, title: str, body: str, subreddit: str, author_flair: str = None) -> float:
        """
        Calculate a relevance score using regex-based matching, subreddit weights, and new scoring logic.
        """
        text = f"{title} {body}".lower()
        sub = subreddit.strip()
        score = 0.0
        # Platform keyword
        platform_match = PLATFORM_REGEX.search(text)
        if platform_match:
            score += 25
        # Context keyword(s)
        context_matches = CONTEXT_REGEX.findall(text)
        if context_matches:
            score += 25
            # Extra context keywords
            if len(context_matches) > 1:
                score += 5 * (len(context_matches) - 1)
        # Subreddit weight
        score += SUBREDDIT_WEIGHTS.get(sub, 0)
        # Post length bonus
        if len(text.split()) > 150:
            score += 5
        # Author flair bonus
        if author_flair and re.search(r"host|operator|guide|supplier|manager", author_flair, re.I):
            score += 10
        # Negative keyword penalty
        negative_match = NEGATIVE_REGEX.search(text)
        if negative_match and not context_matches:
            score -= 20
        # Proximity bonus (platform & context within 12 tokens)
        if platform_match and context_matches:
            platform_idx = platform_match.start()
            context_idx = text.find(context_matches[0][0]) if isinstance(context_matches[0], tuple) else text.find(context_matches[0])
            if abs(platform_idx - context_idx) < 60:  # ~12 tokens
                score += 10
        return score

    def is_relevant(self, title: str, body: str, subreddit: str, author_flair: str = None) -> bool:
        score = self.calculate_relevance_score(title, body, subreddit, author_flair)
        threshold = 45.0
        is_relevant = score >= threshold
        if is_relevant:
            logger.debug(f"Post scored {score:.1f}/100: '{title[:50]}...' (sub: {subreddit})")
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

                async for post in subreddit.new(limit=50):
                    post_count += 1
                    redis_key = f"processed_post:{post.id}"

                    if self.redis.exists(redis_key):
                        continue

                    # Use author_flair_text if available
                    flair = getattr(post, 'author_flair_text', None)
                    if self.is_relevant(post.title, post.selftext, post.subreddit.display_name, flair):
                        score = self.calculate_relevance_score(post.title, post.selftext, post.subreddit.display_name, flair)
                        relevant_count += 1
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
                    self.redis.set(redis_key, 1, ex=int(timedelta(days=7).total_seconds()))

                logger.info(f"Finished check. Processed {post_count} posts, found {relevant_count} relevant.")
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