#!/usr/bin/env python3
"""
Test script to verify the new listener filtering logic
Run this to see what posts would be caught with the more flexible rules
"""

import asyncio
import asyncpraw
import os
from dotenv import load_dotenv
from listener import RedditListener, PLATFORM_KEYWORDS, CONTEXT_WORDS

# Load environment variables
load_dotenv()

async def test_listener():
    """Test the listener with current posts to see what would be caught"""
    
    # Initialize Reddit client
    reddit = asyncpraw.Reddit(
        client_id=os.getenv('REDDIT_CLIENT_ID'),
        client_secret=os.getenv('REDDIT_CLIENT_SECRET'),
        refresh_token=os.getenv('REDDIT_REFRESH_TOKEN'),
        user_agent=os.getenv('REDDIT_USER_AGENT', 'OTA_Forum_Bot/1.0')
    )
    
    # Test with a few high-traffic subreddits
    test_subreddits = ["SmallBusiness", "Entrepreneur", "Travel", "AirbnbHosts"]
    
    print("🔍 Testing new listener filtering logic...")
    print(f"📊 Platform keywords: {len(PLATFORM_KEYWORDS)}")
    print(f"📊 Context keywords: {len(CONTEXT_WORDS)}")
    print(f"📊 Target subreddits: {len(test_subreddits)}")
    print()
    
    listener = RedditListener()
    total_posts = 0
    relevant_posts = 0
    
    for subreddit_name in test_subreddits:
        try:
            print(f"📋 Checking r/{subreddit_name}...")
            subreddit = await reddit.subreddit(subreddit_name)
            
            subreddit_posts = 0
            subreddit_relevant = 0
            
            async for post in subreddit.new(limit=20):
                total_posts += 1
                subreddit_posts += 1
                
                score = listener.calculate_relevance_score(
                    post.title, post.selftext, post.subreddit.display_name
                )
                
                if listener.is_relevant(post.title, post.selftext, post.subreddit.display_name):
                    relevant_posts += 1
                    subreddit_relevant += 1
                    print(f"  ✅ Score {score:.1f}: {post.title[:60]}...")
                elif score > 5:  # Show posts that are close to being relevant
                    print(f"  ⚠️  Score {score:.1f}: {post.title[:60]}...")
            
            print(f"  📈 r/{subreddit_name}: {subreddit_relevant}/{subreddit_posts} relevant")
            print()
            
        except Exception as e:
            print(f"  ❌ Error checking r/{subreddit_name}: {e}")
            print()
    
    print("📊 SUMMARY:")
    print(f"   Total posts checked: {total_posts}")
    print(f"   Relevant posts found: {relevant_posts}")
    print(f"   Relevance rate: {(relevant_posts/total_posts*100):.1f}%")
    
    if relevant_posts == 0:
        print("\n💡 SUGGESTIONS:")
        print("   - The filtering might still be too strict")
        print("   - Consider lowering the threshold further")
        print("   - Add more general travel/business keywords")
        print("   - Check if subreddits have recent activity")
    else:
        print(f"\n🎉 Success! Found {relevant_posts} relevant posts with new logic")

if __name__ == "__main__":
    asyncio.run(test_listener()) 