from telegram import Update
from telegram.ext import ContextTypes
from database.connection import supabase
from utils.messages import REFERRAL_MSG, FORCE_JOIN_MSG
from keyboards.inline import get_join_keyboard
from handlers.start import check_force_join, check_ban

async def referral_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
        
    bot_username = (await context.bot.get_me()).username
    
    # Generate referral link
    referral_link = f"https://t.me/{bot_username}?start={user_id}"
    
    # Get total referrals count
    res = supabase.table("users").select("user_id").eq("referral_id", user_id).execute()
    count = len(res.data) if res.data else 0
    
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    # Telegram Share URL
    share_url = f"https://t.me/share/url?url={referral_link}&text=Hey! Check out this Itachi AI Bot. You can chat and analyze images with it! 🌑🗡️"
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📤 Share with Friends", url=share_url)]
    ])
    
    referral_text = REFERRAL_MSG.format(
        count=count
    )
    
    await update.message.reply_text(referral_text, reply_markup=keyboard, parse_mode="HTML")
