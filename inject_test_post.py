#!/usr/bin/env python3
"""
Test Utility to Manually Inject a Reddit Post into the Processing Queue.

This script allows you to manually trigger the reply and poster services
with a specific Reddit post URL. It's useful for end-to-end testing of the
processing pipeline without waiting for the listener to find a post organically.

Usage:
    python3 inject_test_post.py <full_reddit_post_url>
"""

import os
import sys
import json
import redis
import asyncpraw
import asyncio
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# --- Configuration ---
REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
REDDIT_REFRESH_TOKEN = os.getenv('REDDIT_REFRESH_TOKEN')
REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'OTA_Test_Injector/1.0')
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379')
REDIS_QUEUE_KEY = "posts_to_reply"

async def main(post_url):
    """
    Fetches a Reddit post by URL and injects it into the Redis queue.
    """
    print("--- OTA Bot Test Post Injector ---")

    # 1. Validate environment variables
    required_vars = ['REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET', 'REDDIT_REFRESH_TOKEN']
    if not all(v in os.environ for v in required_vars):
        missing = [v for v in required_vars if v not in os.environ]
        print(f"❌ Error: Missing required environment variables: {', '.join(missing)}")
        print("   Please ensure your .env file is present and correctly configured.")
        return

    # 2. Connect to Redis
    try:
        redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)
        redis_client.ping()
        print(f"✅ Connected to Redis at {REDIS_URL}")
    except Exception as e:
        print(f"❌ Error connecting to Redis: {e}")
        return

    # 3. Connect to Reddit
    print("Connecting to Reddit...")
    reddit = asyncpraw.Reddit(
        client_id=REDDIT_CLIENT_ID,
        client_secret=REDDIT_CLIENT_SECRET,
        refresh_token=REDDIT_REFRESH_TOKEN,
        user_agent=REDDIT_USER_AGENT
    )

    # 4. Fetch the post
    try:
        post = await reddit.submission(url=post_url)
        await post.load() # Eagerly load post data
        print(f"✅ Successfully fetched post: '{post.title[:60]}...'")
    except Exception as e:
        print(f"❌ Error fetching post from URL '{post_url}': {e}")
        return
        
    # 5. Prepare the data payload
    post_data = {
        'id': post.id,
        'title': post.title,
        'content': post.selftext,
        'subreddit': post.subreddit.display_name,
        'url': post.url,
        'created_utc': post.created_utc
    }
    
    # 6. Inject into Redis queue
    try:
        redis_client.lpush(REDIS_QUEUE_KEY, json.dumps(post_data))
        print(f"✅ Successfully injected post '{post.id}' into Redis queue '{REDIS_QUEUE_KEY}'.")
        print("\n--- Test Triggered! ---")
        print("👀 Now, check the logs for the 'reply' and 'poster' services on Render.")
        print("📊 A new entry should also appear in your Neon 'reddit_logs' table shortly.")

    except Exception as e:
        print(f"❌ Error injecting post into Redis: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    url = sys.argv[1]
    asyncio.run(main(url)) 