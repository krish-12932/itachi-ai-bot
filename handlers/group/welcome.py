import logging
import asyncio
import time
from telegram import Update
from telegram.ext import ContextTypes

from database.group_models import get_group_settings, init_group_settings

logger = logging.getLogger(__name__)

# Deduplication: track recently welcomed users to prevent double messages
# Format: {(chat_id, user_id): timestamp}
_recently_welcomed: dict = {}
_WELCOME_DEDUP_SECONDS = 10  # If welcomed within 10 seconds, skip duplicate

def _mark_welcomed(chat_id: int, user_id: int):
    """Mark a user as recently welcomed."""
    _recently_welcomed[(chat_id, user_id)] = time.time()

def _was_recently_welcomed(chat_id: int, user_id: int) -> bool:
    """Returns True if this user was already welcomed in the last 10 seconds."""
    key = (chat_id, user_id)
    last_time = _recently_welcomed.get(key)
    if last_time and (time.time() - last_time) < _WELCOME_DEDUP_SECONDS:
        return True
    return False

async def _send_welcome(bot, chat, user, settings):
    """Shared helper to send the actual welcome message."""
    try:
        mention = f"[{user.first_name}](tg://user?id={user.id})"
        welcome_msg = settings["welcome_message"].replace("{name}", mention)
        sent_msg = await bot.send_message(
            chat_id=chat.id,
            text=f"👋 Hello {mention}!\n\n{welcome_msg}",
            parse_mode="Markdown"
        )
        
        # Auto-Delete Welcome
        if settings.get("auto_delete_welcome"):
            async def delete_later():
                await asyncio.sleep(120)  # 2 minutes
                try:
                    await bot.delete_message(chat_id=chat.id, message_id=sent_msg.message_id)
                except Exception as e:
                    logger.error(f"Failed to auto-delete welcome msg: {e}")
            asyncio.create_task(delete_later())
            
    except Exception as e:
        logger.error(f"Error sending welcome message: {e}")

async def group_member_updated(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles chat member updates (new members joining, bot being promoted)."""
    result = update.chat_member
    if not result:
        return
        
    chat = result.chat
    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status
    user = result.new_chat_member.user
    bot = context.bot

    # 1. Check if the BOT was just added or promoted
    if user.id == bot.id:
        if new_status == "administrator" and old_status != "administrator":
            try:
                from telegram import InlineKeyboardButton, InlineKeyboardMarkup
                admins = await chat.get_administrators()
                owner = next((admin for admin in admins if admin.status == "creator"), None)
                if owner:
                    init_group_settings(chat.id, owner.user.id)
                
                safe_chat_id = str(chat.id).replace("-", "M")
                setup_link = f"https://t.me/{bot.username}?start=setup_{safe_chat_id}"
                keyboard = [[InlineKeyboardButton("⚙️ Configure Settings", url=setup_link)]]
                
                await bot.send_message(
                    chat_id=chat.id,
                    text=f"✅ **Thanks for making me Admin in {chat.title}!**\n\n"
                         f"Group Owner/Admins, click the button below to easily configure anti-spam, bans, and welcome messages.",
                    reply_markup=InlineKeyboardMarkup(keyboard),
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Error initializing group settings after promotion: {e}")
        return

    # 2. Check if a normal USER joined the group
    from telegram.constants import ChatMemberStatus
    was_member = old_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.RESTRICTED]
    is_member = new_status in [ChatMemberStatus.MEMBER, ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.RESTRICTED]
    
    if not was_member and is_member:
        if user.is_bot:
            return
            
        settings = get_group_settings(chat.id)
        if not settings or not settings.get("welcome_enabled", True) or not settings.get("welcome_message"):
            return
        
        # Mark as welcomed BEFORE sending (prevents backup handler from also firing)
        _mark_welcomed(chat.id, user.id)
        await _send_welcome(bot, chat, user, settings)

async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Backup: service message handler for NEW_CHAT_MEMBERS (some join types only send this)."""
    if not update.message or not update.message.new_chat_members:
        return
        
    chat = update.effective_chat
    bot = context.bot
    
    settings = get_group_settings(chat.id)
    if not settings or not settings.get("welcome_enabled", True) or not settings.get("welcome_message"):
        return
        
    for user in update.message.new_chat_members:
        if user.is_bot:
            continue
        
        # Skip if ChatMemberHandler already welcomed this user (deduplication!)
        if _was_recently_welcomed(chat.id, user.id):
            logger.info(f"Skipping duplicate welcome for {user.first_name} in {chat.title}")
            continue
        
        _mark_welcomed(chat.id, user.id)
        await _send_welcome(bot, chat, user, settings)
