import logging
import re
import asyncio
import html
from datetime import datetime
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
import aiohttp
from config import GOOGLE_API_KEYS, OPENROUTER_API_KEY
from database.group_models import (
    get_group_settings, add_warning, get_user_warning, reset_warnings, add_ban
)

logger = logging.getLogger(__name__)

# Temporary in-memory store for rate limiting: {group_id: {user_id: [timestamp1, timestamp2, ...]}}
RATE_LIMITS = {}

# In-memory cache for admin status to avoid Telegram API rate limits: {group_id: {user_id: timestamp}}
ADMIN_CACHE = {}

# Regex for spam/promo detection
# Catches: http links, t.me invite links, bot username promotions
LINK_REGEX = re.compile(
    r'(https?://[^\s]+|'              # Any http/https URL
    r't\.me/\+[^\s]+|'               # t.me/+invite_hash (join links)
    r't\.me/joinchat/[^\s]+|'        # t.me/joinchat/xxx
    r'@[a-zA-Z0-9_]*_bot\b|'         # @username_bot (underscore style)
    r'@[a-zA-Z0-9]{4,}bot\b|'        # @usernamebot (no underscore, min 4 chars before bot)
    r'join\s+my\s+(channel|group)|'  # "join my channel/group"
    r'subscribe\s+to\b)',             # "subscribe to"
    re.IGNORECASE
)
OPENROUTER_MODEL_MOD = "google/gemini-2.0-flash-lite-preview-02-05:free"

async def check_rate_limit(group_id: int, user_id: int) -> bool:
    """Returns True if the user is spamming (5 msgs / 10 sec)"""
    now = datetime.now().timestamp()
    
    if group_id not in RATE_LIMITS:
        RATE_LIMITS[group_id] = {}
    if user_id not in RATE_LIMITS[group_id]:
        RATE_LIMITS[group_id][user_id] = []
        
    # Add current message timestamp
    RATE_LIMITS[group_id][user_id].append(now)
    
    # Remove timestamps older than 10 seconds
    RATE_LIMITS[group_id][user_id] = [ts for ts in RATE_LIMITS[group_id][user_id] if now - ts <= 10]
    
    # If 5 or more messages in 10 seconds, it's spam
    if len(RATE_LIMITS[group_id][user_id]) >= 5:
        # Clear their history so they don't get double-warned immediately
        RATE_LIMITS[group_id][user_id] = []
        return True
        
    return False

async def _is_admin(chat, user_id: int) -> bool:
    """Helper: returns True if user is creator or admin. Uses 10 min cache to avoid rate limits."""
    group_id = chat.id
    now = datetime.now().timestamp()

    # Check cache first (valid for 10 minutes)
    if group_id in ADMIN_CACHE and user_id in ADMIN_CACHE[group_id]:
        if now - ADMIN_CACHE[group_id][user_id] < 600:
            return True

    try:
        member = await chat.get_member(user_id)
        if member.status in ["creator", "administrator"]:
            if group_id not in ADMIN_CACHE:
                ADMIN_CACHE[group_id] = {}
            ADMIN_CACHE[group_id][user_id] = now
            return True
        return False
    except Exception as e:
        logger.warning(f"Failed to check admin status for {user_id} in {group_id}: {e}")
        return False

async def _silent_delete(update: Update, reason: str):
    """Silently delete a message and log it."""
    try:
        await update.message.delete()
        logger.info(f"Silent delete ({reason}): user={update.effective_user.id} in chat={update.effective_chat.id}")
    except Exception as e:
        logger.error(f"Failed to delete message ({reason}): {e}")

import json as _json_mod
import re as _re_mod

# In-memory result cache to avoid repeated AI calls for the same text
_PROMO_CACHE: dict = {}
_PROMO_CACHE_MAX = 500

# Quick pre-filter: catch obvious spam patterns WITHOUT an AI call (much faster)
_QUICK_PROMO_RE = re.compile(
    r'(earn\s+\d+|per\s+day|daily\s+earn|free\s+money|make\s+money|instant\s+withdraw|'
    r'join\s+now|click\s+here|dm\s+me|message\s+me|check\s+my\s+(bio|profile|link)|'
    r'visit\s+my|promote\s+your|advertisement|sponsored|referral\s+code|invite\s+link|'
    r'airdrop|giveaway|crypto\s+signal|bitcoin|invest\s+now|passive\s+income|work\s+from\s+home)',
    re.IGNORECASE
)

def _extract_json_result(reply: str):
    """Robustly extract JSON even if model wraps in markdown or adds extra text."""
    reply = reply.strip().strip("`")
    if reply.lower().startswith("json"):
        reply = reply[4:].strip()
    # Try to find a JSON object with regex
    match = _re_mod.search(r'\{[^}]+\}', reply)
    if match:
        try:
            return _json_mod.loads(match.group().replace("'", '"'))
        except Exception:
            pass
    try:
        return _json_mod.loads(reply.replace("'", '"'))
    except Exception:
        return None

async def is_ai_promotion(text: str) -> bool:
    """Uses AI to detect promotions/spam. OpenRouter primary, Gemini fallback.
    Features: quick-regex pre-filter, result caching, robust JSON parsing, few-shot prompt."""

    text = text.strip()

    # 1. Too short to be meaningful spam
    if len(text) < 20:
        return False

    # 2. Quick regex pre-filter (no API call needed for obvious patterns)
    if _QUICK_PROMO_RE.search(text):
        logger.info(f"Promo quick-detected (regex): {text[:60]}")
        return True

    # 3. Cache check: skip AI if we've seen this exact message recently
    cache_key = text.lower()[:200]
    if cache_key in _PROMO_CACHE:
        return _PROMO_CACHE[cache_key]

    def _cache(val: bool):
        if len(_PROMO_CACHE) >= _PROMO_CACHE_MAX:
            for k in list(_PROMO_CACHE.keys())[:_PROMO_CACHE_MAX // 2]:
                del _PROMO_CACHE[k]
        _PROMO_CACHE[cache_key] = val
        return val

    # 4. AI prompt with few-shot examples for better accuracy
    prompt = f"""You are a Telegram group spam/promotion detector.

Reply ONLY with raw JSON, no markdown, no explanation:
{{"is_promotion": true or false, "confidence": 0-100}}

SPAM/PROMOTION (true):
- "Join my channel for free signals @mychannel"
- "Earn $500/day,DM me now!"
- "I will promote your channel cheaply"
- "Check my bio for the referral link"
- "Airdrop live! Claim now"

NOT SPAM (false):
- "What time does the match start?"
- "I love this song!"
- "Can anyone help me with Python?"
- "Bhai kya scene hai aaj?"

Classify this message:
{text}"""

    # --- PRIMARY: OpenRouter ---
    if OPENROUTER_API_KEY:
        try:
            timeout = aiohttp.ClientTimeout(total=8)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                payload = {
                    "model": OPENROUTER_MODEL_MOD,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 60,
                    "temperature": 0.0
                }
                headers = {
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                    "Content-Type": "application/json",
                    "HTTP-Referer": "https://itachi-bot.onrender.com",
                    "X-Title": "Itachi Moderation"
                }
                async with session.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        reply = data["choices"][0]["message"]["content"]
                        parsed = _extract_json_result(reply)
                        if parsed is not None:
                            is_promo = bool(parsed.get("is_promotion")) and parsed.get("confidence", 0) >= 75
                            return _cache(is_promo)
                        # Fallback text parse
                        if "true" in reply.lower() and "false" not in reply.lower():
                            return _cache(True)
                        return _cache(False)
                    else:
                        body = await resp.text()
                        logger.warning(f"OpenRouter mod error ({resp.status}): {body[:150]}")
        except Exception as e:
            logger.error(f"OpenRouter promo check error: {e}")

    # --- FALLBACK: Gemini Direct API ---
    if not GOOGLE_API_KEYS:
        return False

    gemini_payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0, "maxOutputTokens": 60}
    }
    try:
        timeout = aiohttp.ClientTimeout(total=8)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for api_key in GOOGLE_API_KEYS:
                for model_name in ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                    try:
                        async with session.post(url, headers={"Content-Type": "application/json"}, json=gemini_payload) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if data.get('candidates'):
                                    reply = data['candidates'][0]['content']['parts'][0]['text']
                                    parsed = _extract_json_result(reply)
                                    if parsed is not None:
                                        is_promo = bool(parsed.get("is_promotion")) and parsed.get("confidence", 0) >= 75
                                        return _cache(is_promo)
                                    if "true" in reply.lower() and "false" not in reply.lower():
                                        return _cache(True)
                                    return _cache(False)
                            elif resp.status == 429:
                                continue
                    except Exception:
                        continue
    except Exception as e:
        logger.error(f"Gemini promo check error: {e}")

    return False

async def moderate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Core moderation function called on every group TEXT message"""
    if not update.message or not update.effective_chat or update.effective_chat.type == "private":
        return
        
    chat = update.effective_chat
    user = update.effective_user
    msg_text = update.message.text or update.message.caption or ""
    
    # Don't moderate anonymous admins (they post as the group/channel)
    # When sender_chat is set, the message is from an admin in anonymous mode
    if update.message.sender_chat:
        return
    
    # Don't moderate if user is None (safety check)
    if not user:
        return
    
    # Don't moderate admins
    if await _is_admin(chat, user.id):
        return

    settings = get_group_settings(chat.id)
    if not settings:
        return # Setup not done yet
    
    punishment_mode = settings.get("punishment_mode", "ban")  # 'ban' or 'mute'

    # Helper to apply punishment (Ban or Mute based on settings)
    async def apply_punishment(reason: str, ban_db_reason: str):
        if punishment_mode == "ban":
            try:
                safe_name = html.escape(user.first_name)
                await chat.ban_member(user.id)
                add_ban(chat.id, user.id, ban_db_reason)
                await context.bot.send_message(
                    chat.id,
                    f"🚫 <b>{safe_name} has been Banned!</b>\n\n"
                    f"📋 Reason: {reason}\n"
                    f"To unban yourself, message @{context.bot.username} and send:\n"
                    f"<code>/myunban {chat.id}</code>",
                    parse_mode="HTML"
                )
                reset_warnings(chat.id, user.id)
            except Exception as e:
                logger.error(f"Error banning user: {e}")
        else:  # mute
            try:
                safe_name = html.escape(user.first_name)
                await chat.restrict_member(
                    user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=int(datetime.now().timestamp()) + 300  # 5 min mute
                )
                await context.bot.send_message(
                    chat.id,
                    f"🔇 <b>{safe_name} has been Muted for 5 minutes!</b>\n\n📋 Reason: {reason}",
                    parse_mode="HTML"
                )
                reset_warnings(chat.id, user.id)
            except Exception as e:
                logger.error(f"Error muting user: {e}")

    # 0. Anti-Forward (Silent Delete — no warning, no ban)
    if settings.get("anti_forward") and update.message.forward_origin:
        await _silent_delete(update, "forwarded message")
        return

    # 1. Anti-Link / Anti-Promotion
    bot_username = context.bot.username or ""
    group_username = chat.username or ""
    
    # Remove our own bot's @mention AND group's own @username before checking
    # This prevents false positives when admin tags bot or group username
    clean_msg_for_link_check = msg_text
    if bot_username:
        clean_msg_for_link_check = clean_msg_for_link_check.replace(f"@{bot_username}", "")
    if group_username:
        clean_msg_for_link_check = clean_msg_for_link_check.replace(f"@{group_username}", "")

    is_promo = bool(LINK_REGEX.search(clean_msg_for_link_check))
    
    if not is_promo and (settings.get("anti_link") or settings.get("anti_link_silent")):
        is_promo = await is_ai_promotion(clean_msg_for_link_check)

    if is_promo:
        if settings.get("anti_link_silent"):
            # Silent mode: just delete, no warning
            await _silent_delete(update, "link (silent mode)")
            return
        elif settings.get("anti_link"):
            # Warning mode: delete + warn + punish on 3rd
            await _silent_delete(update, "link")
            warning_count = add_warning(chat.id, user.id)
            safe_name = html.escape(user.first_name)
            try:
                if warning_count == 1:
                    await context.bot.send_message(chat.id, f"⚠️ <b>First Warning</b> for {safe_name}!\nLinks/Promotions are not allowed here.", parse_mode="HTML")
                elif warning_count == 2:
                    action_text = "BANNED" if punishment_mode == "ban" else "MUTED"
                    await context.bot.send_message(chat.id, f"⚠️ <b>Second Warning</b> for {safe_name}!\nOne more link and you will be {action_text}.", parse_mode="HTML")
                elif warning_count >= 3:
                    await apply_punishment("3 Warnings for sending Links/Promotions.", "promotion")
            except Exception as e:
                logger.error(f"Error sending warning: {e}")
            return

    # 1.5 AI Promo Detect (separate toggle - silent delete only)
    if settings.get("ai_promo_detect") and not is_promo:
        is_ai_promo = await is_ai_promotion(clean_msg_for_link_check)
        if is_ai_promo:
            await _silent_delete(update, "AI detected promotion")
            return

    # 2. Rate Limiting (Anti-Spam Warnings)
    if settings.get("anti_spam"):
        is_spamming = await check_rate_limit(chat.id, user.id)
        if is_spamming:
            await _silent_delete(update, "spam")
            warning_count = add_warning(chat.id, user.id)
            safe_name = html.escape(user.first_name)
            try:
                if warning_count == 1:
                    await context.bot.send_message(chat.id, f"⚠️ <b>First Warning</b> for {safe_name}!\nPlease don't spam.", parse_mode="HTML")
                elif warning_count == 2:
                    action_text = "BANNED" if punishment_mode == "ban" else "MUTED"
                    await context.bot.send_message(chat.id, f"⚠️ <b>Second Warning</b> for {safe_name}!\nOne more = {action_text}.", parse_mode="HTML")
                elif warning_count >= 3:
                    await apply_punishment("3 Spam Warnings.", "spam")
            except Exception as e:
                logger.error(f"Error sending spam warning: {e}")
            return


async def media_moderate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Silent delete handler for photos, videos, GIFs, stickers, documents in groups."""
    if not update.message or not update.effective_chat or update.effective_chat.type == "private":
        return

    chat = update.effective_chat
    user = update.effective_user

    # Don't moderate anonymous admins (they post as the group/channel)
    if update.message.sender_chat:
        return

    # Don't moderate if user is None
    if not user:
        return

    # Don't moderate admins
    if await _is_admin(chat, user.id):
        return

    settings = get_group_settings(chat.id)
    if not settings:
        return

    # Anti-Forward check (forwarded media)
    if settings.get("anti_forward") and update.message.forward_origin:
        await _silent_delete(update, "forwarded media")
        return

    # Anti-Media check (photos, videos, GIFs, stickers, documents, animated emoji)
    if settings.get("anti_media"):
        has_media = (
            update.message.photo or
            update.message.video or
            update.message.animation or  # GIFs
            update.message.sticker or
            update.message.document or
            update.message.dice  # Animated emojis (🎲⚽🎯 etc.)
        )
        if has_media:
            await _silent_delete(update, "media not allowed")
            return
