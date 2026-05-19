from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_IDS

async def support_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user_name = update.effective_user.full_name
    username = update.effective_user.username or "No Username"
    
    # Check if they provided a message
    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b>\n\n<code>/support Your issue or question here</code>\n\n"
            "Example: <i>/support I didn't get my coins after watching an ad.</i>",
            parse_mode="HTML"
        )
        return

    support_msg = " ".join(context.args)
    
    # Notify Admin
    admin_text = (
        "📩 <b>New Support Ticket!</b>\n\n"
        f"👤 <b>From:</b> {user_name}\n"
        f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
        f"🔗 <b>Username:</b> @{username}\n\n"
        f"💬 <b>Message:</b>\n{support_msg}"
    )
    
    try:
        for admin_id in ADMIN_IDS:
            await context.bot.send_message(chat_id=admin_id, text=admin_text, parse_mode="HTML")
            
        await update.message.reply_text(
            "✅ <b>Support ticket sent!</b>\n\nOur team (Itachi) will look into it soon. Thank you.",
            parse_mode="HTML"
        )
    except Exception as e:
        await update.message.reply_text(f"❌ Error sending support ticket: {str(e)}")
