from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import ContextTypes
from database.models import get_user, claim_daily, get_top_users, get_top_chatters
from handlers.start import check_force_join, check_ban
from keyboards.inline import get_join_keyboard
from utils.messages import FORCE_JOIN_MSG

async def daily_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.edited_message
    if not message:
        return
        
    # 1. Ban Check
    if await check_ban(update, context):
        return
        
    user_id = update.effective_user.id
    
    # Force Join Check
    if not await check_force_join(update, context):
        await message.reply_text(
            FORCE_JOIN_MSG, 
            reply_markup=get_join_keyboard(),
            parse_mode="HTML"
        )
        return

    db_user = get_user(user_id)
    if not db_user:
        return

    last_claim = db_user.get("last_daily_claim")
    can_claim = False
    
    if not last_claim:
        can_claim = True
    else:
        # Parse timestamp and check if 24 hours have passed
        last_claim_dt = datetime.fromisoformat(last_claim.replace("Z", "+00:00"))
        if datetime.now(last_claim_dt.tzinfo) - last_claim_dt > timedelta(days=1):
            can_claim = True

    if can_claim:
        claim_daily(user_id)
        await message.reply_text(
            "🎁 <b>Daily Reward Claimed!</b>\n\nYou received <b>10 Coins</b>. Come back tomorrow for more!",
            parse_mode="HTML"
        )
    else:
        # Calculate time remaining
        next_claim = last_claim_dt + timedelta(days=1)
        remaining = next_claim - datetime.now(last_claim_dt.tzinfo)
        hours, remainder = divmod(remaining.seconds, 3600)
        minutes, _ = divmod(remainder, 60)
        
        await message.reply_text(
            f"⏳ <b>Be Patient...</b>\n\nYou have already claimed your reward. You can claim again in <b>{hours}h {minutes}m</b>.",
            parse_mode="HTML"
        )

async def leaderboard_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.edited_message
    if not message:
        return
        
    # 1. Ban Check
    if await check_ban(update, context):
        return
        
    user_id = update.effective_user.id
    
    # Force Join Check
    if not await check_force_join(update, context):
        await message.reply_text(FORCE_JOIN_MSG, reply_markup=get_join_keyboard(), parse_mode="HTML")
        return

    top_users = get_top_chatters(10)
    
    text = "🏆 <b>Top Shinobi Chatters</b>\n<i>The most active members in the village</i>\n\n"
    
    for i, user in enumerate(top_users, 1):
        medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else "👤"
        chats = user.get('message_count', 0)
        text += f"{medal} {i}. <b>{user['first_name']}</b> — {chats} Chats\n"
    
    await message.reply_text(text, parse_mode="HTML")
