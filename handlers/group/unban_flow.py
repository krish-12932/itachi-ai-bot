import logging
import shortuuid
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import ContextTypes

from database.group_models import get_ban
from database.models import create_ad_session
from config import WEB_DOMAIN

logger = logging.getLogger(__name__)

async def user_unban_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Command for users to unban themselves via Ads in DM.
    Usage: /myunban [GROUP_ID]
    """
    chat = update.effective_chat
    user = update.effective_user

    # Must be used in DM
    if chat.type != "private":
        await update.message.reply_text("❌ Please message me in private to use this command.")
        return

    # Check if they provided a group ID
    if not context.args:
        await update.message.reply_text(
            "⚠️ *How to unban yourself:*\n\n"
            "Use `/myunban GROUP_ID`\n\n"
            "_You can get the Group ID from the ban notification message sent in the group._",
            parse_mode="Markdown"
        )
        return

    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid Group ID. Please enter a valid number.")
        return

    ban_record = get_ban(group_id, user.id)
    if not ban_record:
        await update.message.reply_text(
            "✅ You are *not banned* in that group, or the ban has already been lifted.",
            parse_mode="Markdown"
        )
        return

    ban_reason = ban_record.get("ban_reason")

    if ban_reason == "admin":
        await update.message.reply_text(
            "🚫 *Admin Ban — Cannot Self-Unban*\n\n"
            "You were manually banned by a group admin.\n"
            "Please contact the group owner directly to get unbanned.",
            parse_mode="Markdown"
        )
        return

    keyboard = [[
        InlineKeyboardButton(
            f"🔓 Unban Me Now",
            callback_data=f"unbanme_{group_id}"
        )
    ]]

    await update.message.reply_text(
        f"🚨 *You are Banned from the Group!*\n\n"
        f"📋 Reason: *{ban_reason.title()}*\n\n"
        f"Click the button below to get unbanned instantly. ✅",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )

async def unbanme_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles the unban button click"""
    query = update.callback_query
    await query.answer()

    data = query.data
    if not data.startswith("unbanme_"):
        return

    try:
        group_id = int(data.split("_")[1])
        user_id = update.effective_user.id
        
        # Unban user
        await context.bot.unban_chat_member(chat_id=group_id, user_id=user_id, only_if_banned=True)
        
        # Remove from DB
        from database.group_models import remove_ban
        remove_ban(group_id, user_id)
        
        await query.edit_message_text(
            "🎉 *You have been Unbanned!*\n\n✅ You can now return to the group and send messages again. Welcome back!",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error in unbanme_callback: {e}")
        await query.edit_message_text("⚠️ There was an issue unbanning you. Please contact the group admin.")
