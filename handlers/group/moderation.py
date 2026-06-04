import logging
import re
import asyncio
from datetime import datetime
from telegram import Update, ChatPermissions
from telegram.ext import ContextTypes
import aiohttp
from config import GOOGLE_API_KEYS

from database.group_models import (
    get_group_settings, add_warning, get_user_warning, reset_warnings, add_ban
)

logger = logging.getLogger(__name__)

# Temporary in-memory store for rate limiting: {group_id: {user_id: [timestamp1, timestamp2, ...]}}
RATE_LIMITS = {}

# Regex for detecting promotional links and other bot tags (@...bot)
LINK_REGEX = re.compile(r'(https?://[^\s]+|t\.me/[^\s]+|@\w+bot\b|join my channel|subscribe to)', re.IGNORECASE)

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
    """Helper: returns True if user is creator or admin."""
    try:
        member = await chat.get_member(user_id)
        return member.status in ["creator", "administrator"]
    except Exception:
        return False

async def _silent_delete(update: Update, reason: str):
    """Silently delete a message and log it."""
    try:
        await update.message.delete()
        logger.info(f"Silent delete ({reason}): user={update.effective_user.id} in chat={update.effective_chat.id}")
    except Exception as e:
        logger.error(f"Failed to delete message ({reason}): {e}")

async def is_ai_promotion(text: str) -> bool:
    """Uses Gemini AI to detect promotions/spam with JSON response."""
    if len(text) < 20:
        return False

    if not GOOGLE_API_KEYS:
        return False

    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    prompt = f"""You are a group moderation AI.
Analyze this message and respond in JSON only, nothing else:

{{
  'is_promotion': true/false,
  'confidence': 0-100
}}

Promotion means:
- Advertising any product/service
- Bot/channel promotion
- Referral or earning links
- Selling anything
- Any @username or link promotion

Message: {text}"""

    payload = {
        "contents": [{"role": "user", "parts": [{"text": prompt}]}]
    }

    try:
        timeout = aiohttp.ClientTimeout(total=10)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for api_key in GOOGLE_API_KEYS:
                for model_name in models:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                    try:
                        async with session.post(url, headers={"Content-Type": "application/json"}, json=payload) as resp:
                            if resp.status == 200:
                                data = await resp.json()
                                if 'candidates' in data and data['candidates']:
                                    reply = data['candidates'][0]['content']['parts'][0]['text'].strip()
                                    try:
                                        import json as json_lib
                                        result = json_lib.loads(reply.replace("'", '"'))
                                        if result.get('is_promotion') and result.get('confidence', 0) >= 60:
                                            return True
                                    except Exception:
                                        if "true" in reply.lower() and "false" not in reply.lower():
                                            return True
                    except Exception:
                        continue
    except Exception as e:
        logger.error(f"AI Promo check error: {e}")

    return False

async def moderate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Core moderation function called on every group TEXT message"""
    if not update.message or not update.effective_chat or update.effective_chat.type == "private":
        return
        
    chat = update.effective_chat
    user = update.effective_user
    msg_text = update.message.text or update.message.caption or ""
    
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
                await chat.ban_member(user.id)
                add_ban(chat.id, user.id, ban_db_reason)
                await context.bot.send_message(
                    chat.id,
                    f"🚫 *{user.first_name} has been Banned!*\n\n"
                    f"📋 Reason: {reason}\n"
                    f"To unban yourself, message @{context.bot.username} and send:\n"
                    f"`/myunban {chat.id}`",
                    parse_mode="Markdown"
                )
                reset_warnings(chat.id, user.id)
            except Exception as e:
                logger.error(f"Error banning user: {e}")
        else:  # mute
            try:
                await chat.restrict_member(
                    user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=int(datetime.now().timestamp()) + 300  # 5 min mute
                )
                await context.bot.send_message(
                    chat.id,
                    f"🔇 *{user.first_name} has been Muted for 5 minutes!*\n\n📋 Reason: {reason}",
                    parse_mode="Markdown"
                )
                reset_warnings(chat.id, user.id)
            except Exception as e:
                logger.error(f"Error muting user: {e}")

    # 0. Anti-Forward (Silent Delete — no warning, no ban)
    if settings.get("anti_forward") and update.message.forward_origin:
        await _silent_delete(update, "forwarded message")
        return

    # 1. Anti-Link / Anti-Promotion
    bot_username = context.bot.username
    clean_msg_for_link_check = msg_text.replace(f"@{bot_username}", "")

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
            if warning_count == 1:
                await context.bot.send_message(chat.id, f"⚠️ *First Warning* for {user.first_name}!\nLinks/Promotions are not allowed here.", parse_mode="Markdown")
            elif warning_count == 2:
                action_text = "BANNED" if punishment_mode == "ban" else "MUTED"
                await context.bot.send_message(chat.id, f"⚠️ *Second Warning* for {user.first_name}!\nOne more link and you will be {action_text}.", parse_mode="Markdown")
            elif warning_count >= 3:
                await apply_punishment("3 Warnings for sending Links/Promotions.", "promotion")
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
            if warning_count == 1:
                await context.bot.send_message(chat.id, f"⚠️ *First Warning* for {user.first_name}!\nPlease don't spam.", parse_mode="Markdown")
            elif warning_count == 2:
                action_text = "BANNED" if punishment_mode == "ban" else "MUTED"
                await context.bot.send_message(chat.id, f"⚠️ *Second Warning* for {user.first_name}!\nOne more = {action_text}.", parse_mode="Markdown")
            elif warning_count >= 3:
                await apply_punishment("3 Spam Warnings.", "spam")
            return


async def media_moderate_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Silent delete handler for photos, videos, GIFs, stickers, documents in groups."""
    if not update.message or not update.effective_chat or update.effective_chat.type == "private":
        return

    chat = update.effective_chat
    user = update.effective_user

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
