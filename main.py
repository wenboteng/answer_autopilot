import logging
import time
from config import Config
from database import Database
from reddit_client import RedditClient
from response_generator import ResponseGenerator

# Configure logging
logging.basicConfig(level=Config.LOG_LEVEL, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

def main():
    Config.validate_config()
    db = Database()
    reddit = RedditClient()
    responder = ResponseGenerator()

    logger.info("Starting OTA Forum Auto-Reply System...")

    for subreddit in Config.TARGET_SUBREDDITS:
        logger.info(f"Checking subreddit: r/{subreddit}")
        posts = reddit.get_subreddit_posts(subreddit, limit=30)
        faq_entries = db.get_faq_entries()

        for post in posts:
            post_id = post['id']
            title = post['title']
            content = post['content']
            post_url = post['url']
            matched_keywords = [kw for kw in Config.OTA_KEYWORDS if kw.lower() in (title + ' ' + content).lower()]

            if not matched_keywords:
                continue
            if db.is_post_processed(post_id):
                continue
            if not db.can_reply_today():
                logger.info("Daily reply limit reached. Skipping further replies today.")
                return

            # Generate response
            response_info = responder.generate_response(title, content, matched_keywords, faq_entries)
            response_text = response_info['text']

            # Post reply
            success = reddit.post_reply(post_id, response_text)
            db.log_post_processing(
                post_id=post_id,
                subreddit=subreddit,
                title=title,
                content=content,
                matched_keywords=matched_keywords,
                response_text=response_text,
                success=success
            )
            if success:
                db.increment_daily_replies()
                logger.info(f"Replied to post: {post_url}")
            else:
                logger.warning(f"Failed to reply to post: {post_url}")
            # Sleep to avoid rate limits
            time.sleep(10)

    logger.info("Run complete.")

if __name__ == "__main__":
    main() 