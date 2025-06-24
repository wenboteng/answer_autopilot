#!/usr/bin/env python3
"""
Test script to verify Reddit API authentication
"""
import asyncio
import asyncpraw
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

async def test_reddit_auth():
    """Test Reddit authentication"""
    print("🔍 Testing Reddit API Authentication...")
    
    # Get credentials from environment
    client_id = os.getenv('REDDIT_CLIENT_ID')
    client_secret = os.getenv('REDDIT_CLIENT_SECRET')
    refresh_token = os.getenv('REDDIT_REFRESH_TOKEN')
    user_agent = os.getenv('REDDIT_USER_AGENT', 'OTA_Forum_Bot/1.0')
    
    print(f"Client ID: {client_id[:10]}..." if client_id else "❌ Client ID not found")
    print(f"Client Secret: {client_secret[:10]}..." if client_secret else "❌ Client Secret not found")
    print(f"Refresh Token: {refresh_token[:20]}..." if refresh_token else "❌ Refresh Token not found")
    print(f"User Agent: {user_agent}")
    
    if not all([client_id, client_secret, refresh_token]):
        print("❌ Missing required credentials")
        return False
    
    try:
        # Initialize Reddit client
        print("\n🔄 Initializing Reddit client...")
        reddit = asyncpraw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            refresh_token=refresh_token,
            user_agent=user_agent
        )
        
        # Test authentication by getting user info
        print("🔄 Testing authentication...")
        user = await reddit.user.me()
        print(f"✅ Authentication successful! Logged in as: {user.name}")
        
        # Test accessing a subreddit
        print("🔄 Testing subreddit access...")
        subreddit = await reddit.subreddit("test")
        print(f"✅ Subreddit access successful!")
        
        # Test getting new posts
        print("🔄 Testing post retrieval...")
        async for post in subreddit.new(limit=1):
            print(f"✅ Post retrieval successful! Found post: {post.title[:50]}...")
            break
        
        print("\n🎉 All tests passed! Reddit API is working correctly.")
        return True
        
    except Exception as e:
        print(f"\n❌ Authentication failed: {e}")
        print(f"Error type: {type(e).__name__}")
        return False

if __name__ == "__main__":
    asyncio.run(test_reddit_auth()) 