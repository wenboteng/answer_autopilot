-- =====================================================
-- OTA Bot Monitoring Queries for Neon Database
-- =====================================================

-- 1. OVERALL STATISTICS
-- =====================================================
SELECT 
    COUNT(*) as total_posts,
    SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successful_posts,
    SUM(CASE WHEN success = false THEN 1 ELSE 0 END) as failed_posts,
    ROUND(
        (SUM(CASE WHEN success = true THEN 1 ELSE 0 END)::float / COUNT(*)::float) * 100, 2
    ) as success_rate_percent
FROM reddit_logs;

-- 2. DAILY ACTIVITY (Last 7 days)
-- =====================================================
SELECT 
    DATE(posted_at) as date,
    COUNT(*) as total_posts,
    SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successful_posts,
    SUM(CASE WHEN success = false THEN 1 ELSE 0 END) as failed_posts
FROM reddit_logs 
WHERE posted_at >= NOW() - INTERVAL '7 days'
GROUP BY DATE(posted_at)
ORDER BY date DESC;

-- 3. SUBREDDIT PERFORMANCE
-- =====================================================
SELECT 
    subreddit,
    COUNT(*) as total_posts,
    SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successful_posts,
    SUM(CASE WHEN success = false THEN 1 ELSE 0 END) as failed_posts,
    ROUND(
        (SUM(CASE WHEN success = true THEN 1 ELSE 0 END)::float / COUNT(*)::float) * 100, 2
    ) as success_rate_percent
FROM reddit_logs
GROUP BY subreddit
ORDER BY total_posts DESC;

-- 4. RECENT ACTIVITY (Last 24 hours)
-- =====================================================
SELECT 
    posted_at,
    subreddit,
    LEFT(title, 50) as title_preview,
    success,
    comment_url,
    error_message
FROM reddit_logs 
WHERE posted_at >= NOW() - INTERVAL '24 hours'
ORDER BY posted_at DESC
LIMIT 20;

-- 5. ERROR ANALYSIS
-- =====================================================
SELECT 
    error_message,
    COUNT(*) as error_count,
    MAX(posted_at) as last_occurrence
FROM reddit_logs 
WHERE success = false AND error_message IS NOT NULL
GROUP BY error_message
ORDER BY error_count DESC
LIMIT 10;

-- 6. HOURLY ACTIVITY PATTERN (Last 7 days)
-- =====================================================
SELECT 
    EXTRACT(HOUR FROM posted_at) as hour_of_day,
    COUNT(*) as total_posts,
    SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as successful_posts
FROM reddit_logs 
WHERE posted_at >= NOW() - INTERVAL '7 days'
GROUP BY EXTRACT(HOUR FROM posted_at)
ORDER BY hour_of_day;

-- 7. REPLY LENGTH ANALYSIS
-- =====================================================
SELECT 
    AVG(LENGTH(reply_text)) as avg_reply_length,
    MIN(LENGTH(reply_text)) as min_reply_length,
    MAX(LENGTH(reply_text)) as max_reply_length,
    COUNT(*) as total_replies
FROM reddit_logs 
WHERE success = true AND reply_text IS NOT NULL;

-- 8. TOP POSTS BY TITLE LENGTH (Potential Issues)
-- =====================================================
SELECT 
    post_id,
    subreddit,
    LEFT(title, 100) as title_preview,
    LENGTH(title) as title_length,
    success,
    posted_at
FROM reddit_logs 
WHERE LENGTH(title) > 200
ORDER BY LENGTH(title) DESC
LIMIT 10;

-- 9. SUCCESS RATE BY HOUR (Last 7 days)
-- =====================================================
SELECT 
    EXTRACT(HOUR FROM posted_at) as hour_of_day,
    COUNT(*) as total_posts,
    ROUND(
        (SUM(CASE WHEN success = true THEN 1 ELSE 0 END)::float / COUNT(*)::float) * 100, 2
    ) as success_rate_percent
FROM reddit_logs 
WHERE posted_at >= NOW() - INTERVAL '7 days'
GROUP BY EXTRACT(HOUR FROM posted_at)
ORDER BY hour_of_day;

-- 10. BOT UPTIME CHECK (Posts in last hour)
-- =====================================================
SELECT 
    COUNT(*) as posts_last_hour,
    CASE 
        WHEN COUNT(*) > 0 THEN 'Bot is active'
        ELSE 'Bot may be down - no posts in last hour'
    END as status
FROM reddit_logs 
WHERE posted_at >= NOW() - INTERVAL '1 hour'; 