from database.connection import supabase
from datetime import datetime, timezone

# --------------------------
# Group Settings
# --------------------------
def get_group_settings(group_id: int):
    res = supabase.table("group_settings").select("*").eq("group_id", group_id).execute()
    return res.data[0] if res.data else None

def init_group_settings(group_id: int, owner_id: int):
    settings = get_group_settings(group_id)
    if settings:
        return settings
    data = {
        "group_id": group_id,
        "owner_id": owner_id,
        "welcome_enabled": True,
        "welcome_message": "Welcome to the group, {name}! 👋",
        "anti_spam": True,
        "anti_link": True,
        "anti_media": False,
        "anti_forward": False,
        "anti_link_silent": False,
        "auto_delete_welcome": False,
        "ai_help": True,
        "proactive_ai": True,
        "punishment_mode": "ban",
        "group_topic": None,
        "ai_promo_detect": False
    }
    res = supabase.table("group_settings").insert(data).execute()
    return res.data[0] if res.data else None

def update_group_setting(group_id: int, key: str, value):
    supabase.table("group_settings").update({key: value}).eq("group_id", group_id).execute()

# --------------------------
# Warnings
# --------------------------
def get_user_warning(group_id: int, user_id: int):
    res = supabase.table("group_warnings").select("*").eq("group_id", group_id).eq("user_id", user_id).execute()
    return res.data[0] if res.data else None

def add_warning(group_id: int, user_id: int):
    warning = get_user_warning(group_id, user_id)
    if warning:
        new_count = warning["warning_count"] + 1
        supabase.table("group_warnings").update({
            "warning_count": new_count,
            "last_warning_time": datetime.now(timezone.utc).isoformat()
        }).eq("id", warning["id"]).execute()
        return new_count
    else:
        supabase.table("group_warnings").insert({
            "group_id": group_id,
            "user_id": user_id,
            "warning_count": 1
        }).execute()
        return 1

def reset_warnings(group_id: int, user_id: int):
    supabase.table("group_warnings").delete().eq("group_id", group_id).eq("user_id", user_id).execute()

# --------------------------
# Bans
# --------------------------
def add_ban(group_id: int, user_id: int, reason: str):
    res = supabase.table("group_bans").select("*").eq("group_id", group_id).eq("user_id", user_id).execute()
    if res.data:
        supabase.table("group_bans").update({"ban_reason": reason}).eq("id", res.data[0]["id"]).execute()
    else:
        supabase.table("group_bans").insert({
            "group_id": group_id,
            "user_id": user_id,
            "ban_reason": reason
        }).execute()

def remove_ban(group_id: int, user_id: int):
    supabase.table("group_bans").delete().eq("group_id", group_id).eq("user_id", user_id).execute()

def get_ban(group_id: int, user_id: int):
    res = supabase.table("group_bans").select("*").eq("group_id", group_id).eq("user_id", user_id).execute()
    return res.data[0] if res.data else None

# --------------------------
# AI Dataset
# --------------------------
def save_group_ai_message(group_id: int, user_id: int, user_message: str, bot_response: str, context_type: str = "tagged"):
    data = {
        "group_id": group_id,
        "user_id": user_id,
        "user_message": user_message,
        "bot_response": bot_response,
        "context_type": context_type
    }
    supabase.table("group_ai_dataset").insert(data).execute()
