import praw
import os
import sys
import uuid
from dotenv import load_dotenv
from urllib.parse import urlparse, parse_qs

# Load environment variables from .env
load_dotenv()

def get_refresh_token():
    """
    A one-time script to get the Reddit refresh token.
    """
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT")
    # This must match the 'redirect uri' from your Reddit app settings
    redirect_uri = "http://localhost:8080"

    if not all([client_id, client_secret, user_agent]):
        print("❌ Please make sure REDDIT_CLIENT_ID, REDDIT_CLIENT_SECRET, and REDDIT_USER_AGENT are set in your .env file.")
        return

    # Check if praw is installed
    try:
        import praw
    except ImportError:
        print("❌ PRAW is not installed. Please run: pip install praw")
        sys.exit(1)


    # Create a PRAW instance
    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
        redirect_uri=redirect_uri,
    )

    # Generate a random state string
    state = str(uuid.uuid4())

    # Generate the authorization URL
    # Scopes needed: identity (for karma), read (posts), submit (comments), vote (for upvoting)
    scopes = ["identity", "read", "submit", "vote", "edit", "history"]
    auth_url = reddit.auth.url(scopes=scopes, state=state, duration="permanent")

    print("\n--- Reddit Refresh Token Generator ---")
    print("\n1. Open the following URL in your browser:")
    print(f"\n   {auth_url}\n")
    print("2. Log in to your Reddit account ('wbobteng') and click 'allow' to authorize the application.")
    print("3. You will be redirected to a blank page or an error page on localhost. This is OK.")
    print("   Copy the FULL URL from your browser's address bar (it will contain a 'code' parameter).")
    
    redirected_url = input("\n4. Paste the full redirected URL here and press Enter:\n   ")

    # Extract the authorization code from the URL
    try:
        parsed_url = urlparse(redirected_url)
        query_params = parse_qs(parsed_url.query)
        code = query_params["code"][0]
    except (IndexError, KeyError):
        print("\n❌ Could not find 'code' in the redirected URL.")
        print("   It should look like: http://localhost:8080/?state=...&code=SOME_LONG_STRING")
        return

    # Exchange the code for a refresh token
    try:
        print("\n⏳ Exchanging code for refresh token...")
        refresh_token = reddit.auth.authorize(code)
        print("\n✅ Success! Here is your refresh token:")
        print(f"\n   {refresh_token}\n")
        print("Copy this token and paste it into your .env file for the REDDIT_REFRESH_TOKEN variable.")
        print("You only need to do this once.")
    except Exception as e:
        print(f"\n❌ An error occurred: {e}")
        print("   Please double-check your Client ID, Secret, and that you pasted the correct URL.")

if __name__ == "__main__":
    get_refresh_token() 