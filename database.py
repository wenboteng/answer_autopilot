import sqlite3
import json
from datetime import datetime
from config import Config
import psycopg
from psycopg_pool import ConnectionPool
import os
import logging
import time

logger = logging.getLogger(__name__)

class NeonDB:
    def __init__(self):
        self.pool = None
        self.db_url = os.getenv("NEON_DATABASE_URL")

    def connect(self):
        """Creates a connection pool to the database."""
        if not self.db_url:
            logger.error("NEON_DATABASE_URL is not set. Cannot connect to the database.")
            return
        try:
            self.pool = ConnectionPool(conninfo=self.db_url, min_size=1, max_size=20)
            logger.info("Successfully connected to Neon database.")
            self.init_database()
        except Exception as e:
            logger.error(f"Failed to connect to Neon database: {e}")
            self.pool = None

    def reconnect(self):
        """Reconnects the connection pool."""
        logger.warning("Reconnecting to Neon database...")
        self.close()
        self.connect()

    def init_database(self):
        """Initializes the database with the required tables if they don't exist."""
        if not self.pool:
            return
        # Use a context manager for clean connection handling
        with self.pool.connection() as conn:
            with conn.cursor() as cursor:
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
                logger.info("Database initialized (tables created if not exists).")

    def log_post(self, post_id, subreddit, title, reply_text, success, comment_url=None, error_message=None, max_retries=2):
        """Logs a record of a posted reply to the database, with retry on connection failure."""
        if not self.pool:
            logger.warning("No database connection. Skipping log.")
            return
        insert_query = """
            INSERT INTO reddit_logs (post_id, subreddit, title, reply_text, success, comment_url, posted_at, error_message)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        attempt = 0
        while attempt <= max_retries:
            try:
                with self.pool.connection() as conn:
                    with conn.cursor() as cursor:
                        cursor.execute(
                            insert_query,
                            (
                                post_id,
                                subreddit,
                                title,
                                reply_text,
                                success,
                                comment_url,
                                datetime.utcnow(),
                                error_message
                            )
                        )
                    logger.info(f"Logged post {post_id} to Neon database.")
                return
            except Exception as e:
                logger.error(f"Error logging post {post_id} to Neon (attempt {attempt+1}): {e}")
                if attempt < max_retries:
                    self.reconnect()
                    time.sleep(1)
                    attempt += 1
                else:
                    logger.error(f"Failed to log post {post_id} after {max_retries+1} attempts.")
                    return

    def close(self):
        """Closes the database connection pool."""
        if self.pool:
            self.pool.close()
            logger.info("Neon database connection pool closed.")

def get_db():
    """Dependency function to get a db connection."""
    db = NeonDB()
    db.connect()
    return db

class Database:
    def __init__(self, db_path=None):
        self.db_path = db_path or Config.DATABASE_PATH
        self.init_database()
    
    def init_database(self):
        """Initialize the database with required tables"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Create posts table to track processed posts
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS processed_posts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    post_id TEXT UNIQUE NOT NULL,
                    subreddit TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT,
                    matched_keywords TEXT,
                    response_text TEXT,
                    posted_at TIMESTAMP,
                    success BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create daily_replies table to track daily reply limits
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_replies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    date DATE UNIQUE NOT NULL,
                    reply_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            # Create faq_entries table for storing FAQ responses
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS faq_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    keywords TEXT NOT NULL,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            
            conn.commit()
    
    def is_post_processed(self, post_id):
        """Check if a post has already been processed"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT id FROM processed_posts WHERE post_id = ?', (post_id,))
            return cursor.fetchone() is not None
    
    def log_post_processing(self, post_id, subreddit, title, content, matched_keywords, response_text, success):
        """Log a post processing attempt"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO processed_posts 
                (post_id, subreddit, title, content, matched_keywords, response_text, posted_at, success)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                post_id, subreddit, title, content, 
                json.dumps(matched_keywords), response_text, 
                datetime.now(), success
            ))
            conn.commit()
    
    def can_reply_today(self):
        """Check if we can still reply today (within daily limit)"""
        today = datetime.now().date()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            # Get today's reply count
            cursor.execute('SELECT reply_count FROM daily_replies WHERE date = ?', (today,))
            result = cursor.fetchone()
            
            if result:
                return result[0] < Config.MAX_REPLIES_PER_DAY
            else:
                # No entry for today, create one
                cursor.execute('INSERT INTO daily_replies (date, reply_count) VALUES (?, 0)', (today,))
                conn.commit()
                return True
    
    def increment_daily_replies(self):
        """Increment the daily reply count"""
        today = datetime.now().date()
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT OR REPLACE INTO daily_replies (date, reply_count)
                VALUES (?, COALESCE((SELECT reply_count FROM daily_replies WHERE date = ?), 0) + 1)
            ''', (today, today))
            conn.commit()
    
    def get_faq_entries(self):
        """Get all FAQ entries"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT keywords, question, answer FROM faq_entries')
            return cursor.fetchall()
    
    def add_faq_entry(self, keywords, question, answer):
        """Add a new FAQ entry"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO faq_entries (keywords, question, answer)
                VALUES (?, ?, ?)
            ''', (json.dumps(keywords), question, answer))
            conn.commit()
    
    def get_processing_stats(self, days=7):
        """Get processing statistics for the last N days"""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT 
                    DATE(created_at) as date,
                    COUNT(*) as total_posts,
                    SUM(CASE WHEN success = 1 THEN 1 ELSE 0 END) as successful_replies
                FROM processed_posts 
                WHERE created_at >= DATE('now', '-{} days')
                GROUP BY DATE(created_at)
                ORDER BY date DESC
            '''.format(days))
            return cursor.fetchall() 