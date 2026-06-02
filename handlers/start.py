from telegram import Update, ChatMemberUpdated, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from config import FORCE_JOIN_CHANNELS
from database.models import add_user, get_user
from datetime import datetime
from utils.messages import WELCOME_MSG, FORCE_JOIN_MSG
from keyboards.inline import get_join_keyboard

async def check_force_join(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    for channel in FORCE_JOIN_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel["id"], user_id=user_id)
            if member.status in ['left', 'kicked', 'restricted']:
                return False
        except Exception:
            return False
            
    return True

async def check_ban(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Checks if the user is currently banned. Returns True if banned."""
    user_id = update.effective_user.id
    db_user = get_user(user_id)
    
    if not db_user: return False
    
    from datetime import datetime, timezone
    ban_until = db_user.get("ban_until")
    if ban_until:
        ban_until_dt = datetime.fromisoformat(ban_until.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if now < ban_until_dt:
            remaining = ban_until_dt - now
            mins = remaining.seconds // 60
            secs = remaining.seconds % 60
            
            msg = (
                f"🛑 <b>Access Denied!</b>\n\n"
                f"You are still trapped in Izanami.\n"
                f"Time remaining: <b>{mins}m {secs}s</b>\n\n"
                "Wait for the cycle to end."
            )
            if update.message:
                await update.message.reply_text(msg, parse_mode="HTML")
            elif update.callback_query:
                await update.callback_query.answer(f"Banned! {mins}m {secs}s remaining.", show_alert=True)
            return True
    return False

async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # 1. Ban Check
    if await check_ban(update, context):
        return
        
    user = update.effective_user
    
    # 1. Check Force Join
    if not await check_force_join(update, context):
        await update.message.reply_text(
            FORCE_JOIN_MSG, 
            reply_markup=get_join_keyboard(), 
            parse_mode="HTML"
        )
        return

    # 2. Check Deep Links
    referrer_id = None
    if context.args:
        arg = context.args[0]
        if arg.startswith("setup_"):
            raw_chat_id = arg.replace("setup_", "").replace("M", "-")
            try:
                chat_id = int(raw_chat_id)
                chat = await context.bot.get_chat(chat_id)
                member = await context.bot.get_chat_member(chat_id=chat_id, user_id=user.id)
                
                if member.status in ["creator", "administrator"]:
                    from handlers.group.settings import get_settings_keyboard
                    from database.group_models import get_group_settings, init_group_settings
                    init_group_settings(chat_id, user.id)
                    
                    await update.message.reply_text(
                        f"⚙️ *Group Setup for {chat.title}*\n\n"
                        f"*What each setting does:*\n"
                        f"🛡 *Anti-Spam* — 5 messages in 10 sec = warning. 3 warnings = punishment.\n"
                        f"🔗 *Anti-Link* — Links/Bot promotions ka msg delete ho jaata hai.\n"
                        f"🤖 *AI Help* — Jab koi @{context.bot.username} ko tag kare.\n"
                        f"🗣 *Proactive AI* — Bot khud help karta hai.\n"
                        f"⚖️ *Punishment* — 3 warnings ke baad Ban ya Mute.\n\n"
                        f"_Buttons click karke toggle karein:_",
                        reply_markup=await get_settings_keyboard(chat_id),
                        parse_mode="Markdown"
                    )
                    return
                else:
                    await update.message.reply_text("🛑 Only Admins/Owners can configure group settings.")
                    return
            except Exception as e:
                import logging
                logging.error(f"Setup deep link error: {e}")
        else:
            try:
                ref_code = arg
                if ref_code.isdigit() and int(ref_code) != user.id:
                    referrer_id = int(ref_code)
            except Exception:
                pass

    # 3. Add/Get User
    db_user = add_user(user_id=user.id, first_name=user.first_name, username=user.username, referrer_id=referrer_id)
    
    welcome_text = WELCOME_MSG.format(
        name=user.first_name,
        coins=db_user.get("coins", 0)
    )
    msg = await update.message.reply_text(welcome_text, parse_mode="HTML")
    # Save ID to delete later when chat starts
    context.user_data["temp_welcome_msg"] = msg.message_id

async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    
    # 1. Ban Check
    if await check_ban(update, context):
        return

    # 2. Re-check Join Status
    if not await check_force_join(update, context):
        await query.answer("⚠️ You haven't joined all channels yet!", show_alert=True)
        return

    # 2. Status is OK, delete the force join message
    try:
        await query.message.delete()
    except:
        pass

    # 3. Add/Get User
    db_user = add_user(user_id=user.id, first_name=user.first_name, username=user.username)
    
    welcome_text = WELCOME_MSG.format(
        name=user.first_name,
        coins=db_user.get("coins", 0)
    )
    msg = await context.bot.send_message(chat_id=user.id, text=welcome_text, parse_mode="HTML")
    # Save ID to delete later when chat starts
    context.user_data["temp_welcome_msg"] = msg.message_id

async def chat_member_updated(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detects when a user joins or leaves a channel."""
    result = update.chat_member
    if not result:
        return

    user_id = result.from_user.id
    new_status = result.new_chat_member.status
    old_status = result.old_chat_member.status

    # If user left
    if new_status in ['left', 'kicked']:
        # Send force join message automatically
        try:
            msg = await context.bot.send_message(
                chat_id=user_id,
                text=f"⚠️ <b>It looks like you left our channel!</b>\n\nYou must stay in our channels to use the bot. Please join back to continue.",
                reply_markup=get_join_keyboard(),
                parse_mode="HTML"
            )
            # We could save this message ID to delete it later, but context.user_data is easier for now
            context.user_data[f"force_join_msg_{user_id}"] = msg.message_id
        except:
            pass

    # If user joined
    elif new_status == 'member' and old_status in ['left', 'kicked', 'restricted']:
        # Automatically delete the force join message if we have it
        msg_id = context.user_data.get(f"force_join_msg_{user_id}")
        if msg_id:
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=msg_id)
                del context.user_data[f"force_join_msg_{user_id}"]
            except:
                pass
        
        # Also check if they are fully joined in both, then send welcome
        if await check_force_join(update, context):
            db_user = add_user(user_id=user_id, first_name=result.from_user.first_name, username=result.from_user.username)
            welcome_text = WELCOME_MSG.format(
                name=result.from_user.first_name,
                coins=db_user.get("coins", 0)
            )
            await context.bot.send_message(chat_id=user_id, text=welcome_text, parse_mode="HTML")
