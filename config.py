import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

class Config:
    # Reddit API Configuration
    REDDIT_CLIENT_ID = os.getenv('REDDIT_CLIENT_ID')
    REDDIT_CLIENT_SECRET = os.getenv('REDDIT_CLIENT_SECRET')
    REDDIT_REFRESH_TOKEN = os.getenv('REDDIT_REFRESH_TOKEN')
    REDDIT_USER_AGENT = os.getenv('REDDIT_USER_AGENT', 'OTA_Forum_Bot/1.0')
    
    # OpenAI API Configuration
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
    
    # Application Configuration
    MAX_REPLIES_PER_DAY = int(os.getenv('MAX_REPLIES_PER_DAY', 10))
    SEARCH_INTERVAL_HOURS = int(os.getenv('SEARCH_INTERVAL_HOURS', 2))
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    
    # Database Configuration
    DATABASE_PATH = os.getenv('DATABASE_PATH', 'ota_forum_bot.db')
    
    # OTA Keywords for filtering posts
    OTA_KEYWORDS = [
        'viator', 'getyourguide', 'airbnb', 'booking.com', 'payout', 
        'support', 'vendor', 'confirmation', 'email', 'cancel', 'refund',
        'host', 'guest', 'reservation', 'booking', 'trip', 'travel',
        'tourism', 'accommodation', 'property', 'listing'
    ]
    
    # Target subreddits
    TARGET_SUBREDDITS = [
        'airbnb_hosts', 'travel', 'tourism', 'airbnb', 'booking',
        'travelagents', 'hospitality', 'hotels'
    ]
    
    # Tool URL
    TOOL_URL = "https://otaanswers.com"
    
    @classmethod
    def validate_config(cls):
        """Validate that all required configuration is present"""
        required_vars = [
            'REDDIT_CLIENT_ID', 'REDDIT_CLIENT_SECRET', 
            'REDDIT_REFRESH_TOKEN', 'OPENAI_API_KEY'
        ]
        
        missing_vars = []
        for var in required_vars:
            if not getattr(cls, var):
                missing_vars.append(var)
        
        if missing_vars:
            raise ValueError(f"Missing required environment variables: {', '.join(missing_vars)}")
        
        return True 