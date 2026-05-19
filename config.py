import os
from dotenv import load_dotenv

load_dotenv(override=True)

# Bot Config
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
# Parse ADMIN_ID as a list of strings (e.g., "ID1,ID2,ID3")
raw_admin_ids = os.getenv("ADMIN_ID", "")
ADMIN_IDS = [id.strip() for id in raw_admin_ids.split(",") if id.strip()]

# Database Config (Supabase)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# AI Config
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Web Server Config
PORT = int(os.getenv("PORT", 8080))
WEB_DOMAIN = os.getenv("WEB_DOMAIN", "https://your-deployed-domain.com")

# Dynamic Channel Config
FORCE_JOIN_CHANNELS = []
for i in range(1, 11):
    suffix = "" if i == 1 else f"_{i}"
    ch_id = os.getenv(f"REQUIRED_CHANNEL_ID{suffix}")
    ch_link = os.getenv(f"CHANNEL_INVITE_LINK{suffix}")
    
    if ch_id and ch_link:
        FORCE_JOIN_CHANNELS.append({
            "id": ch_id.strip(),
            "link": ch_link.strip(),
            "index": i
        })
