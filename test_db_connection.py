#!/usr/bin/env python3
"""
Test script to check Neon database connection and table creation
"""

import os
import psycopg2
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def test_neon_connection():
    """Test connection to Neon database"""
    db_url = os.getenv("NEON_DATABASE_URL")
    
    if not db_url:
        print("❌ NEON_DATABASE_URL not found in environment variables")
        return False
    
    print(f"🔗 Testing connection to Neon database...")
    print(f"URL: {db_url[:50]}...")  # Show first 50 chars for security
    
    try:
        # Test connection
        conn = psycopg2.connect(db_url)
        print("✅ Successfully connected to Neon database")
        
        # Check if reddit_logs table exists
        cursor = conn.cursor()
        cursor.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_schema = 'public' 
                AND table_name = 'reddit_logs'
            );
        """)
        
        table_exists = cursor.fetchone()[0]
        
        if table_exists:
            print("✅ reddit_logs table already exists")
            
            # Count records
            cursor.execute("SELECT COUNT(*) FROM reddit_logs;")
            count = cursor.fetchone()[0]
            print(f"📊 Table has {count} records")
            
        else:
            print("❌ reddit_logs table does not exist")
            print("🔧 Creating table...")
            
            # Create the table
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS reddit_logs (
                    id SERIAL PRIMARY KEY,
                    post_id TEXT NOT NULL,
                    subreddit TEXT NOT NULL,
                    title TEXT,
                    reply_text TEXT,
                    success BOOLEAN,
                    comment_url TEXT,
                    posted_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
                    error_message TEXT
                );
            """)
            conn.commit()
            print("✅ reddit_logs table created successfully")
        
        cursor.close()
        conn.close()
        return True
        
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False

def test_bot_database_module():
    """Test the bot's database module"""
    print("\n🔧 Testing bot's database module...")
    
    try:
        from database import NeonDB
        
        db = NeonDB()
        db.connect()
        
        if db.pool:
            print("✅ Bot database module works correctly")
            
            # Test logging a sample record
            db.log_post(
                post_id="test_123",
                subreddit="test_subreddit",
                title="Test post",
                reply_text="This is a test reply",
                success=True,
                comment_url="https://reddit.com/test",
                error_message=None
            )
            print("✅ Successfully logged test record")
            
            db.close()
            return True
        else:
            print("❌ Bot database module failed to connect")
            return False
            
    except Exception as e:
        print(f"❌ Bot database module test failed: {e}")
        return False

if __name__ == "__main__":
    print("🚀 Testing Neon Database Connection and Setup")
    print("=" * 50)
    
    # Test 1: Direct connection
    connection_ok = test_neon_connection()
    
    # Test 2: Bot module
    if connection_ok:
        module_ok = test_bot_database_module()
    
    print("\n" + "=" * 50)
    if connection_ok:
        print("✅ Database setup is working correctly!")
        print("📊 You can now run monitoring queries in Neon Console")
    else:
        print("❌ Database setup needs attention")
        print("🔧 Check your NEON_DATABASE_URL environment variable") 