from auth import get_authorization_url, exchange_code_for_token
from db import supabase
import uuid

# 1. Create a Fake User in Supabase (if they don't exist)
# We need a valid UUID to link the tokens to.
TEST_USER_ID = "a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11"

try:
    # Try to insert a dummy user into the profiles table
    # If the user already exists, this might fail, which is fine.
    supabase.table("profiles").insert({"id": TEST_USER_ID}).execute()
    print("Created test user profile.")
except Exception:
    print("Test user profile already exists (skipping creation).")

# 2. Get the Link
print("\n--- STEP 1: AUTHORIZE ---")
url = get_authorization_url()
print(f"👉 CLICK THIS LINK:\n{url}\n")

# 3. Ask you for the code
print("--- STEP 2: PASTE THE CODE ---")
print("1. Login and click Authorize.")
print("2. When it redirects to localhost (error page), look at the URL bar.")
print("3. Copy the value after 'code='")
code = input("Paste code here: ").strip()

# 4. Save it
print("\n--- STEP 3: SAVING ---")
exchange_code_for_token(TEST_USER_ID, code)