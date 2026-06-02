import shortuuid 
from telegram import Update
from telegram.ext import ContextTypes
from config import WEB_DOMAIN
from database.models import create_ad_session
from utils.messages import PLAN_MSG
from keyboards.inline import get_plan_keyboard

async def plan_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Generate unique codes for this session
    coin_code = shortuuid.uuid()[:8]
    coin_20_code = shortuuid.uuid()[:8]
    unlimited_code = shortuuid.uuid()[:8]
    
    # Send message first to get message_id
    sent = await update.message.reply_text(
        PLAN_MSG,
        reply_markup=get_plan_keyboard(WEB_DOMAIN, coin_code, coin_20_code, unlimited_code),
        parse_mode="Markdown"
    )
    
    # Save sessions to DB
    create_ad_session(user_id, coin_code, sent.message_id, "10_coins")
    create_ad_session(user_id, coin_20_code, sent.message_id, "20_coins")
    create_ad_session(user_id, unlimited_code, sent.message_id, "unlimited")
