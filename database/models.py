from database.connection import supabase

def get_user(user_id: int):
    res = supabase.table("users").select("*").eq("user_id", user_id).execute()
    return res.data[0] if res.data else None

def add_user(user_id: int, first_name: str, username: str, referrer_id: int = None):
    # Check if user exists
    user = get_user(user_id)
    if user:
        return user
    
    data = {
        "user_id": user_id,
        "first_name": first_name,
        "username": username,
        "coins": 50,
        "referral_id": referrer_id,
        "is_chatting": False,
        "personality_summary": "",
        "message_count": 0,
        "unlimited_chat": False
    }
    res = supabase.table("users").insert(data).execute()
    
    # Reward referrer if applicable
    if referrer_id:
        reward_referrer(referrer_id)
        
    return res.data[0] if res.data else None

def reward_referrer(referrer_id: int):
    # Add 30 coins to referrer
    referrer = get_user(referrer_id)
    if referrer:
        new_coins = referrer.get("coins", 0) + 30
        supabase.table("users").update({"coins": new_coins}).eq("user_id", referrer_id).execute()

def update_user_coins(user_id: int, amount: int):
    user = get_user(user_id)
    if user and not user.get("unlimited_chat"):
        new_coins = max(0, user.get("coins", 0) + amount)
        supabase.table("users").update({"coins": new_coins}).eq("user_id", user_id).execute()
        return new_coins
    return user.get("coins") if user else 0

def set_chat_mode(user_id: int, mode: bool):
    supabase.table("users").update({"is_chatting": mode}).eq("user_id", user_id).execute()

def update_personality(user_id: int, summary: str):
    supabase.table("users").update({"personality_summary": summary}).eq("user_id", user_id).execute()

def increment_message_count(user_id: int):
    user = get_user(user_id)
    if user:
        new_count = user.get("message_count", 0) + 1
        supabase.table("users").update({"message_count": new_count}).eq("user_id", user_id).execute()
        return new_count
    return 0

def create_ad_session(user_id: int, code: str, message_id: int, session_type: str):
    data = {
        "unique_code": code,
        "user_id": user_id,
        "message_id": message_id,
        "type": session_type
    }
    supabase.table("user_sessions").insert(data).execute()

def get_ad_session(code: str):
    res = supabase.table("user_sessions").select("*").eq("unique_code", code).execute()
    return res.data[0] if res.data else None

def delete_ad_session(code: str):
    supabase.table("user_sessions").delete().eq("unique_code", code).execute()

def set_unlimited_chat(user_id: int, status: bool):
    supabase.table("users").update({"unlimited_chat": status}).eq("user_id", user_id).execute()

def save_message(user_id: int, role: str, content: str):
    data = {
        "user_id": user_id,
        "role": role,
        "content": content
    }
    supabase.table("messages").insert(data).execute()

def get_recent_messages(user_id: int, limit: int = 10):
    res = supabase.table("messages").select("role, content").eq("user_id", user_id).order("created_at", desc=True).limit(limit).execute()
    # Reverse to get chronological order
    return res.data[::-1] if res.data else []

def get_all_users():
    """Fetches all users from the database."""
    res = supabase.table("users").select("user_id, first_name").execute()
    return res.data if res.data else []

def get_top_users(limit: int = 10):
    """Fetches the top users by coin count."""
    res = supabase.table("users").select("first_name, coins").order("coins", desc=True).limit(limit).execute()
    return res.data if res.data else []

def get_top_chatters(limit: int = 10):
    """Fetches the top users by message count."""
    res = supabase.table("users").select("first_name, message_count").order("message_count", desc=True).limit(limit).execute()
    return res.data if res.data else []

def claim_daily(user_id: int):
    """Updates the user's coins and sets the last_daily_claim timestamp to now."""
    from datetime import datetime, timezone
    user = get_user(user_id)
    if not user: return False
    
    new_coins = user.get("coins", 0) + 10
    supabase.table("users").update({
        "coins": new_coins,
        "last_daily_claim": datetime.now(timezone.utc).isoformat()
    }).eq("user_id", user_id).execute()
    return True

def ban_user(user_id: int, minutes: int):
    """Increments violation count and sets ban_until timestamp."""
    from datetime import datetime, timedelta, timezone
    user = get_user(user_id)
    if not user: return None
    
    new_violations = user.get("violation_count", 0) + 1
    ban_time = datetime.now(timezone.utc) + timedelta(minutes=minutes)
    
    supabase.table("users").update({
        "violation_count": new_violations,
        "ban_until": ban_time.isoformat()
    }).eq("user_id", user_id).execute()
    
    return {"violations": new_violations, "ban_until": ban_time}

def unban_user(user_id: int):
    """Lifts the ban for a specific user and resets violation count."""
    supabase.table("users").update({
        "ban_until": None,
        "violation_count": 0
    }).eq("user_id", user_id).execute()
    return True

def admin_give_coins(user_id: int, amount: int):
    """Directly adds or subtracts coins from a user's account (Admin use)."""
    user = get_user(user_id)
    if not user:
        return None
    new_coins = max(0, user.get("coins", 0) + amount)
    res = supabase.table("users").update({"coins": new_coins}).eq("user_id", user_id).execute()
    return res.data[0] if res.data else None
