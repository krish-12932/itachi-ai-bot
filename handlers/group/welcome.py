import logging
import asyncio
from telegram import Update
from telegram.ext import ContextTypes

from database.group_models import get_group_settings, init_group_settings
from handlers.group.settings import get_settings_keyboard

logger = logging.getLogger(__name__)

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
            # Bot was just made an admin!
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

    # 2. Check if a normal USER joined the group (including unbanned users coming back)
    if new_status == "member" and old_status in ["left", "kicked", "restricted"]:
        if user.is_bot:
            return
            
        settings = get_group_settings(chat.id)
        if not settings or not settings.get("welcome_enabled", True) or not settings.get("welcome_message"):
            return
            
        try:
            welcome_msg = settings["welcome_message"].replace("{name}", user.first_name)
            sent_msg = await bot.send_message(
                chat_id=chat.id,
                text=f"👋 Hello {user.first_name}!\n\n{welcome_msg}",
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
                
                # Run the deletion in the background
                asyncio.create_task(delete_later())
                
        except Exception as e:
            logger.error(f"Error sending group welcome message via ChatMemberUpdate: {e}")

async def welcome_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fallback handler for service messages when someone joins via invite link."""
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
            
        try:
            welcome_msg = settings["welcome_message"].replace("{name}", user.first_name)
            sent_msg = await bot.send_message(
                chat_id=chat.id,
                text=f"👋 Hello {user.first_name}!\n\n{welcome_msg}",
                parse_mode="Markdown"
            )
            
            # Auto-Delete Welcome
            if settings.get("auto_delete_welcome"):
                async def delete_later_service():
                    await asyncio.sleep(120)  # 2 minutes
                    try:
                        await bot.delete_message(chat_id=chat.id, message_id=sent_msg.message_id)
                    except Exception as e:
                        logger.error(f"Failed to auto-delete welcome msg: {e}")
                
                asyncio.create_task(delete_later_service())
                
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")
