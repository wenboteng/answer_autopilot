import openai
import json
import logging
from config import Config

logger = logging.getLogger(__name__)

class ResponseGenerator:
    def __init__(self):
        """Initialize OpenAI client"""
        openai.api_key = Config.OPENAI_API_KEY
        self.client = openai.OpenAI(api_key=Config.OPENAI_API_KEY)
    
    def find_faq_match(self, post_text, faq_entries):
        """
        Find the best matching FAQ entry for a post
        
        Args:
            post_text (str): The text of the post
            faq_entries (list): List of FAQ entries from database
            
        Returns:
            dict: Best matching FAQ entry or None
        """
        post_text_lower = post_text.lower()
        best_match = None
        best_score = 0
        
        for keywords, question, answer in faq_entries:
            try:
                keywords_list = json.loads(keywords) if isinstance(keywords, str) else keywords
                
                # Calculate match score based on keyword overlap
                matched_keywords = [kw for kw in keywords_list if kw.lower() in post_text_lower]
                score = len(matched_keywords) / len(keywords_list) if keywords_list else 0
                
                if score > best_score and score > 0.3:  # Minimum 30% keyword match
                    best_score = score
                    best_match = {
                        'keywords': keywords_list,
                        'question': question,
                        'answer': answer,
                        'score': score
                    }
            except Exception as e:
                logger.warning(f"Error processing FAQ entry: {e}")
                continue
        
        return best_match
    
    def generate_openai_response(self, post_title, post_content, matched_keywords):
        """
        Generate a response using OpenAI API
        
        Args:
            post_title (str): The title of the post
            post_content (str): The content of the post
            matched_keywords (list): Keywords that matched the post
            
        Returns:
            str: Generated response text
        """
        try:
            # Create a context-aware prompt
            prompt = f"""
You are a helpful assistant for OTA (Online Travel Agency) vendors and hosts. A user has posted the following question on Reddit:

Title: {post_title}
Content: {post_content}

The post contains these OTA-related keywords: {', '.join(matched_keywords)}

Please provide a helpful, friendly response that:
1. Acknowledges their question/issue
2. Offers practical advice or information
3. Mentions that you've built a free tool to help with OTA-related questions
4. Includes a link to https://otaanswers.com
5. Keeps the tone conversational and helpful (not spammy)

Keep the response under 200 words and make it sound natural and genuine.
"""

            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant for OTA vendors and hosts. Be friendly, informative, and genuinely helpful."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=300,
                temperature=0.7
            )
            
            generated_response = response.choices[0].message.content.strip()
            
            # Ensure the tool URL is included
            if Config.TOOL_URL not in generated_response:
                generated_response += f"\n\nYou can also check out our free tool for quick OTA answers: {Config.TOOL_URL}"
            
            logger.info(f"Generated OpenAI response for post: {post_title[:50]}...")
            return generated_response
            
        except Exception as e:
            logger.error(f"Error generating OpenAI response: {e}")
            # Fallback response
            return self._generate_fallback_response(post_title, matched_keywords)
    
    def _generate_fallback_response(self, post_title, matched_keywords):
        """
        Generate a fallback response when OpenAI fails
        
        Args:
            post_title (str): The title of the post
            matched_keywords (list): Keywords that matched the post
            
        Returns:
            str: Fallback response text
        """
        # Create a simple template-based response
        keyword_str = ', '.join(matched_keywords[:3])  # Use first 3 keywords
        
        response = f"""Hi there! I see you're asking about {keyword_str} - this is a common question among OTA vendors and hosts.

We've built a free tool that helps vendors like you find quick answers and support contacts for various OTA platforms. It can save you a lot of time when dealing with common issues.

You can check it out here: {Config.TOOL_URL}

Hope this helps! Let me know if you need any clarification."""
        
        return response
    
    def generate_response(self, post_title, post_content, matched_keywords, faq_entries=None):
        """
        Generate the best possible response for a post
        
        Args:
            post_title (str): The title of the post
            post_content (str): The content of the post
            matched_keywords (list): Keywords that matched the post
            faq_entries (list): FAQ entries from database
            
        Returns:
            dict: Response information including text and source
        """
        post_text = f"{post_title} {post_content}"
        
        # First, try to find a FAQ match
        if faq_entries:
            faq_match = self.find_faq_match(post_text, faq_entries)
            if faq_match:
                logger.info(f"Using FAQ match for post: {post_title[:50]}...")
                return {
                    'text': faq_match['answer'],
                    'source': 'faq',
                    'matched_keywords': faq_match['keywords'],
                    'confidence': faq_match['score']
                }
        
        # If no FAQ match, generate with OpenAI
        logger.info(f"Generating OpenAI response for post: {post_title[:50]}...")
        generated_text = self.generate_openai_response(post_title, post_content, matched_keywords)
        
        return {
            'text': generated_text,
            'source': 'openai',
            'matched_keywords': matched_keywords,
            'confidence': 0.5  # Default confidence for generated responses
        }
    
    def test_openai_connection(self):
        """
        Test the OpenAI API connection
        
        Returns:
            dict: Test result
        """
        try:
            response = self.client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "user", "content": "Hello, this is a test message."}
                ],
                max_tokens=10
            )
            
            return {
                'status': 'ok',
                'message': 'OpenAI API is working correctly'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'OpenAI API error: {e}'
            } 