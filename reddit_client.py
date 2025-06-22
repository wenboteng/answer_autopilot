import praw
import logging
from datetime import datetime, timedelta
from config import Config

logger = logging.getLogger(__name__)

class RedditClient:
    def __init__(self):
        """Initialize Reddit client with OAuth credentials"""
        self.reddit = praw.Reddit(
            client_id=Config.REDDIT_CLIENT_ID,
            client_secret=Config.REDDIT_CLIENT_SECRET,
            refresh_token=Config.REDDIT_REFRESH_TOKEN,
            user_agent=Config.REDDIT_USER_AGENT
        )
        
        # Test the connection
        try:
            self.reddit.user.me()
            logger.info("Reddit client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Reddit client: {e}")
            raise
    
    def search_posts(self, subreddit_name, keywords, time_filter='day', limit=25):
        """
        Search for posts in a subreddit containing OTA-related keywords
        
        Args:
            subreddit_name (str): Name of the subreddit
            keywords (list): List of keywords to search for
            time_filter (str): Time filter ('hour', 'day', 'week', 'month', 'year', 'all')
            limit (int): Maximum number of posts to return
            
        Returns:
            list: List of relevant posts
        """
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            
            # Create search query from keywords
            search_query = ' OR '.join(keywords)
            
            logger.info(f"Searching r/{subreddit_name} for: {search_query}")
            
            relevant_posts = []
            
            # Search for posts containing keywords
            for post in subreddit.search(search_query, time_filter=time_filter, limit=limit):
                # Check if post is recent (within last 24 hours)
                post_time = datetime.fromtimestamp(post.created_utc)
                if post_time < datetime.now() - timedelta(days=1):
                    continue
                
                # Check if post has any replies (we don't want to reply to posts that already have responses)
                if post.num_comments > 0:
                    continue
                
                # Check if post contains OTA keywords
                post_text = f"{post.title} {post.selftext}".lower()
                matched_keywords = [keyword for keyword in keywords if keyword.lower() in post_text]
                
                if matched_keywords:
                    relevant_posts.append({
                        'id': post.id,
                        'title': post.title,
                        'content': post.selftext,
                        'subreddit': subreddit_name,
                        'url': f"https://reddit.com{post.permalink}",
                        'created_utc': post.created_utc,
                        'matched_keywords': matched_keywords,
                        'score': post.score,
                        'num_comments': post.num_comments
                    })
            
            logger.info(f"Found {len(relevant_posts)} relevant posts in r/{subreddit_name}")
            return relevant_posts
            
        except Exception as e:
            logger.error(f"Error searching subreddit r/{subreddit_name}: {e}")
            return []
    
    def post_reply(self, post_id, reply_text):
        """
        Post a reply to a Reddit post
        
        Args:
            post_id (str): The ID of the post to reply to
            reply_text (str): The text of the reply
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            # Get the submission
            submission = self.reddit.submission(id=post_id)
            
            # Post the reply
            comment = submission.reply(reply_text)
            
            logger.info(f"Successfully posted reply to post {post_id}")
            logger.info(f"Reply URL: https://reddit.com{comment.permalink}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error posting reply to post {post_id}: {e}")
            return False
    
    def get_subreddit_posts(self, subreddit_name, limit=50):
        """
        Get recent posts from a subreddit (for monitoring new posts)
        
        Args:
            subreddit_name (str): Name of the subreddit
            limit (int): Maximum number of posts to return
            
        Returns:
            list: List of recent posts
        """
        try:
            subreddit = self.reddit.subreddit(subreddit_name)
            posts = []
            
            for post in subreddit.new(limit=limit):
                posts.append({
                    'id': post.id,
                    'title': post.title,
                    'content': post.selftext,
                    'subreddit': subreddit_name,
                    'url': f"https://reddit.com{post.permalink}",
                    'created_utc': post.created_utc,
                    'score': post.score,
                    'num_comments': post.num_comments
                })
            
            return posts
            
        except Exception as e:
            logger.error(f"Error getting posts from r/{subreddit_name}: {e}")
            return []
    
    def check_rate_limits(self):
        """
        Check current Reddit API rate limits
        
        Returns:
            dict: Rate limit information
        """
        try:
            # This is a basic check - Reddit doesn't expose detailed rate limit info
            # We'll just test if we can make a simple API call
            self.reddit.user.me()
            return {
                'status': 'ok',
                'message': 'Reddit API is accessible'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Reddit API error: {e}'
            } 