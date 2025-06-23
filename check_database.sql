-- =====================================================
-- Database Status Check and Setup
-- =====================================================

-- 1. Check what tables exist in the database
-- =====================================================
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public';

-- 2. Check if reddit_logs table exists
-- =====================================================
SELECT EXISTS (
    SELECT FROM information_schema.tables 
    WHERE table_schema = 'public' 
    AND table_name = 'reddit_logs'
) as table_exists;

-- 3. If table doesn't exist, create it manually
-- =====================================================
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

-- 4. Verify table was created
-- =====================================================
SELECT 
    column_name, 
    data_type, 
    is_nullable
FROM information_schema.columns 
WHERE table_name = 'reddit_logs'
ORDER BY ordinal_position;

-- 5. Check table structure
-- =====================================================
\d reddit_logs; 