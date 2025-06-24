import openai
import yaml
import os
import logging
import redis
import json
import httpx
import asyncio
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
logger = logging.getLogger(__name__)

# Load configuration
with open('config.yaml', 'r') as f:
    config = yaml.safe_load(f)

# Initialize OpenAI client
openai.api_key = os.getenv('OPENAI_API_KEY')
client = openai.OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

# Initialize Redis
redis_url = os.getenv('REDIS_URL')
if redis_url:
    redis_client = redis.from_url(redis_url, decode_responses=True)
    logger.info("Connected to Redis via URL")
else:
    redis_client = redis.Redis(
        host=config['redis']['host'],
        port=config['redis']['port'],
        db=config['redis']['db'],
        decode_responses=True
    )
    logger.info("Connected to Redis via config.yaml")

# Initialize HTTP client for classifier
classifier_client = httpx.AsyncClient(base_url="http://localhost:8000")

PROMPT = """
You are a friendly tour-operator peer. A Reddit user asked:

{post}

Compose a 120-word answer that:
• Gives one actionable tip
• Mentions our free tool ({tool_url}) exactly ONCE
• Ends with "Hope that helps – I'm the creator of the tool, AMA!"
• Keep the tone conversational and helpful (not spammy)
"""

async def check_content_moderation(text):
    """Check if content is safe using OpenAI's moderation endpoint"""
    try:
        response = client.moderations.create(input=text)
        result = response.results[0]
        
        # Check for any flagged categories
        flagged = result.flagged
        categories = result.categories
        
        if flagged:
            logger.warning(f"Content flagged: {categories}")
            return False
        
        return True
    except Exception as e:
        logger.error(f"Error in content moderation: {e}")
        return True  # Allow if moderation fails

async def classify_post(post_text):
    """Classify a post using the classifier service"""
    try:
        response = await classifier_client.post("/score", json={"text": post_text})
        if response.status_code == 200:
            return response.json()
        else:
            logger.error(f"Classifier error: {response.status_code}")
            return None
    except Exception as e:
        logger.error(f"Error calling classifier: {e}")
        return None

def draft_reply(post_text, matched_keywords):
    """Generate a reply using OpenAI"""
    try:
        tool_url = config['tool']['url']
        
        # Create the prompt
        formatted_prompt = PROMPT.format(
            post=post_text,
            tool_url=tool_url
        )
        
        # Generate response
        response = client.chat.completions.create(
            model=config['api']['openai']['model'],
            messages=[
                {"role": "system", "content": "You are a helpful tour operator peer who has built a tool to help other vendors."},
                {"role": "user", "content": formatted_prompt}
            ],
            temperature=config['api']['openai']['temperature'],
            max_tokens=config['api']['openai']['max_tokens']
        )
        
        reply_text = response.choices[0].message.content.strip()
        
        # Ensure the tool URL is included
        if tool_url not in reply_text:
            reply_text += f"\n\nYou can also check out our free tool: {tool_url}"
        
        logger.info(f"Generated reply for keywords: {matched_keywords}")
        return reply_text
        
    except Exception as e:
        logger.error(f"Error generating reply: {e}")
        return None

async def process_reply_queue():
    """Process posts that have been queued for replies"""
    try:
        # Get posts from the reply queue
        queue_key = "posts_to_reply"
        
        while True:
            # Pop a post from the queue
            post_data = redis_client.rpop(queue_key)
            if not post_data:
                break
            
            # Ensure post_data is a dict
            if isinstance(post_data, str):
                post = json.loads(post_data)
            else:
                post = post_data
            
            # Generate reply
            post_text = f"{post['title']} {post['content']}"
            matched_keywords = post.get('matched_keywords', [])
            
            reply_text = draft_reply(post_text, matched_keywords)
            
            if reply_text:
                # Check content moderation
                is_safe = await check_content_moderation(reply_text)
                
                if is_safe:
                    # Add UTM parameters to the tool URL
                    utm_params = f"?utm_source={config['tool']['utm_source']}&utm_medium={config['tool']['utm_medium']}&utm_campaign={config['tool']['utm_campaign']}"
                    reply_text = reply_text.replace(config['tool']['url'], config['tool']['url'] + utm_params)
                    
                    # Queue for posting
                    post['reply_text'] = reply_text
                    post['generated_at'] = datetime.now().isoformat()
                    
                    redis_client.lpush("posts_to_post", json.dumps(post))
                    logger.info(f"Queued reply for post {post['id']}")
                else:
                    logger.warning(f"Reply flagged by content moderation for post {post['id']}")
            else:
                logger.error(f"Failed to generate reply for post {post['id']}")
                
    except Exception as e:
        logger.error(f"Error processing reply queue: {e}")

async def run():
    """Main run loop"""
    logger.info("Starting reply generator service...")
    
    while True:
        try:
            await process_reply_queue()
            await asyncio.sleep(10)  # Check every 10 seconds
        except Exception as e:
            logger.error(f"Reply generator error: {e}")
            await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(run()) 