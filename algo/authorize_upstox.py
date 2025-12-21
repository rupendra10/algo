import requests
import upstox_client
import config
import os

def generate_auth_url():
    """Step 1: Generate the URL for the user to visit."""
    client_id = config.UPSTOX_API_KEY
    redirect_uri = config.UPSTOX_REDIRECT_URI
    state = "strategy_auth_state" # Can be any string to track session
    
    url = f"https://api.upstox.com/v2/login/authorization/dialog?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}&state={state}"
    
    print("\n" + "="*50)
    print("UPSTOX AUTHORIZATION STEP 1")
    print("="*50)
    print("1. Visit the following URL in your browser:")
    print(f"\n{url}\n")
    print("2. Log in with your Upstox credentials.")
    print("3. After logging in, you will be redirected to a page (it might look like an error, that's okay).")
    print("4. Copy the 'code' parameter from the URL in your browser address bar.")
    print("   Example: https://127.0.0.1:5000/?code=ABC123XYZ")
    print("="*50)

def exchange_code_for_token(auth_code):
    """Step 2: Exchange the auth code for an access token."""
    url = "https://api.upstox.com/v2/login/authorization/token"
    
    payload = {
        'code': auth_code,
        'client_id': config.UPSTOX_API_KEY,
        'client_secret': config.UPSTOX_API_SECRET,
        'redirect_uri': config.UPSTOX_REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    headers = {
        'accept': 'application/json',
        'Content-Type': 'application/x-www-form-urlencoded'
    }
    
    response = requests.post(url, data=payload, headers=headers)
    
    if response.status_code == 200:
        data = response.json()
        access_token = data.get('access_token')
        print("\nSUCCESS! Access Token obtained.")
        print("-" * 50)
        print(f"Token: {access_token}")
        print("-" * 50)
        print("\nNOTE: This token is valid for 24 hours (until the next day's market open).")
        print("You will need to run this script once daily before starting your algo.")
        print("\nTo use this token, copy it into your config.py file:")
        print(f"UPSTOX_ACCESS_TOKEN = '{access_token}'")
        return access_token
    else:
        print(f"\nFAILED to obtain token. Status Code: {response.status_code}")
        print(f"Error: {response.text}")
        return None

if __name__ == "__main__":
    if config.UPSTOX_API_KEY == 'your_api_key_here' or config.UPSTOX_API_SECRET == 'your_api_secret_here':
        print("ERROR: Please update your UPSTOX_API_KEY and UPSTOX_API_SECRET in config.py first.")
    else:
        generate_auth_url()
        code = input("\nEnter the 'code' from the redirected URL: ").strip()
        if code:
            exchange_code_for_token(code)
        else:
            print("No code entered. Exiting.")
