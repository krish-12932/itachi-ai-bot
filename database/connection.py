from supabase import create_client, Client
from config import SUPABASE_URL, SUPABASE_KEY

def get_supabase() -> Client:
    if not SUPABASE_URL or not SUPABASE_KEY:
        raise ValueError("SUPABASE_URL or SUPABASE_KEY is not set in environment variables")
    return create_client(SUPABASE_URL, SUPABASE_KEY)

supabase = get_supabase()
