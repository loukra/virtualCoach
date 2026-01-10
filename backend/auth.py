import os
import time
from stravalib.client import Client
from db import supabase
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID")
CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET")

def get_authorization_url():
    """Generates the URL you need to click to login."""
    client = Client()
    url = client.authorization_url(
        client_id=CLIENT_ID,
        redirect_uri='http://localhost/exchange_token',
        scope=['activity:read_all']
    )
    return url

def exchange_code_for_token(user_id: str, code: str):
    """Swaps the code for a token and saves it to Supabase."""
    client = Client()
    print(f"Talking to Strava to exchange code...")
    
    try:
        token_response = client.exchange_code_for_token(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            code=code
        )
    except Exception as e:
        print(f"❌ Strava Error: {e}")
        return False

    # 1. Extract tokens
    access_token = token_response['access_token']
    refresh_token = token_response['refresh_token']
    expires_at = token_response['expires_at']
    
    # 2. Robust Check: Did Strava send the athlete info?
    if 'athlete' in token_response:
        athlete_id = token_response['athlete']['id']
    else:
        print("⚠️ Athlete info missing in handshake. Fetching manually...")
        client.access_token = access_token
        athlete = client.get_athlete()
        athlete_id = athlete.id
        print(f"   Found Athlete ID: {athlete_id}")

    # 3. Save to Supabase
    data = {
        "user_id": user_id,
        "athlete_id": athlete_id,
        "access_token": access_token,
        "refresh_token": refresh_token,
        "expires_at": expires_at
    }

    try:
        supabase.table("strava_connection").upsert(data).execute()
        print(f"✅ SUCCESS! User {user_id} connected.")
        return True
    except Exception as e:
        print(f"❌ Database Error: {e}")
        return False

def refresh_access_token(user_id: str, refresh_token: str):
    """Refreshes the token if it is expired."""
    client = Client()
    print(f"🔄 Refreshing token for user {user_id}...")
    
    try:
        new_tokens = client.refresh_access_token(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
            refresh_token=refresh_token
        )
    except Exception as e:
        print(f"❌ Failed to refresh token: {e}")
        raise e

    # Update DB
    supabase.table("strava_connection").update({
        "access_token": new_tokens['access_token'],
        "refresh_token": new_tokens['refresh_token'], 
        "expires_at": new_tokens['expires_at']
    }).eq("user_id", user_id).execute()
    
    return new_tokens['access_token']

def get_valid_token(user_id: str):
    """The Master Key: Checks DB, refreshes if needed, returns token."""
    response = supabase.table("strava_connection").select("*").eq("user_id", user_id).execute()
    
    if not response.data:
        raise Exception(f"User {user_id} has not connected Strava yet.")
    
    user_data = response.data[0]
    
    # Check if expired (with 5 min buffer)
    if user_data['expires_at'] < time.time() + 300:
        return refresh_access_token(user_id, user_data['refresh_token'])
    
    return user_data['access_token']