from telegram import Update
from telegram.ext import ContextTypes
from database.models import get_user
from config import ADMIN_IDS
from utils.messages import PROFILE_MSG, FORCE_JOIN_MSG
from keyboards.inline import get_join_keyboard
from handlers.start import check_force_join, check_ban

async def profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Ban Check
    if await check_ban(update, context):
        return
        
    user_id = update.effective_user.id
    
    # Force Join Check
    if not await check_force_join(update, context):
        await update.message.reply_text(
            FORCE_JOIN_MSG, 
            reply_markup=get_join_keyboard(),
            parse_mode="HTML"
        )
        return
        
    db_user = get_user(user_id)
    
    if not db_user:
        await update.message.reply_text("Error: User profile not found.")
        return
        
    # Admin check for display
    is_admin = str(user_id) in ADMIN_IDS
    
    raw_personality = db_user.get("personality_summary") or "None yet"
    clean_personality = raw_personality.replace("<br>", "\n").replace("<br/>", "\n").replace("<b>User Profile</b>", "").strip()
    
    profile_text = PROFILE_MSG.format(
        user_id=user_id,
        coins="♾️ Unlimited" if is_admin else db_user.get("coins", 0),
        unlimited="✅ Yes (Admin)" if is_admin else ("✅ Yes" if db_user.get("unlimited_chat") else "❌ No"),
        personality=clean_personality
    )
    
    try:
        await update.message.reply_text(profile_text, parse_mode="HTML")
    except Exception:
        # Fallback to plain text if Markdown parsing fails
        await update.message.reply_text(profile_text)
