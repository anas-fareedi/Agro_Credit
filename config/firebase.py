import os
import json
import firebase_admin
from firebase_admin import credentials, firestore, auth
from dotenv import load_dotenv
from functools import lru_cache

load_dotenv()


def initialize_firebase():
    """Initialize Firebase Admin SDK with credentials from env or file."""
    if firebase_admin._apps:
        return firestore.client()
    
    # Try loading from JSON string in env variable first
    cred_json = os.getenv("FIREBASE_CREDENTIALS_JSON")
    if cred_json:
        cred_dict = json.loads(cred_json)
        cred = credentials.Certificate(cred_dict)
    else:
        # Fall back to file path
        cred_path = os.getenv("FIREBASE_CREDENTIALS_PATH", "serviceAccountKey.json")
        
        # Check if it's a URL (common mistake)
        if cred_path.startswith("http://") or cred_path.startswith("https://"):
            raise ValueError(
                f"FIREBASE_CREDENTIALS_PATH should be a file path, not a URL.\n"
                f"Current value: {cred_path}\n\n"
                "To fix this:\n"
                "1. Go to Firebase Console > Project Settings > Service Accounts\n"
                "2. Click 'Generate new private key'\n"
                "3. Save the JSON file as 'serviceAccountKey.json' in the project root\n"
                "4. Set FIREBASE_CREDENTIALS_PATH=serviceAccountKey.json in .env"
            )
        
        if not os.path.exists(cred_path):
            raise FileNotFoundError(
                f"Firebase credentials file not found at: {cred_path}\n\n"
                "To fix this:\n"
                "1. Go to Firebase Console > Project Settings > Service Accounts\n"
                "2. Click 'Generate new private key'\n"
                "3. Save the JSON file as 'serviceAccountKey.json' in the project root\n"
                "4. Or update FIREBASE_CREDENTIALS_PATH in .env to point to your key file"
            )
        cred = credentials.Certificate(cred_path)
    
    firebase_admin.initialize_app(cred)
    return firestore.client()


# Initialize on module load
db = initialize_firebase()


@lru_cache()
def get_db():
    """Get Firestore client instance (cached)."""
    return db


def get_auth():
    """Get Firebase Auth instance."""
    return auth