import getpass
from db import supabase

def login_user():
    """
    Asks the user for email/password, authenticates with Supabase,
    and returns the User ID and the Access Token.
    """
    print("\n🔐 LOGIN REQUIRED")
    email = input("Email: ").strip()
    password = getpass.getpass("Password: ").strip()

    try:
        # Authenticate with Supabase
        response = supabase.auth.sign_in_with_password({
            "email": email,
            "password": password
        })
        
        user = response.user
        session = response.session
        
        print(f"✅ Successfully logged in as: {user.email}")
        return user.id

    except Exception as e:
        print(f"\n❌ Login Failed: {e}")
        print("Please check your email and password.")
        exit(1) # Stop the script immediately if login fails

if __name__ == "__main__":
    # Test the login function
    user_id = login_user()
    print(f"User ID: {user_id}")