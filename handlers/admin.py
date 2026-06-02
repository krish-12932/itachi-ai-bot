import asyncio
from telegram import Update
from telegram.ext import ContextTypes
from config import ADMIN_IDS
from database.models import get_all_users, ban_user, unban_user

async def broadcast_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Security check: Only Admin
    if str(user_id) not in ADMIN_IDS:
        return

    # Check if message is provided
    if not context.args:
        await update.message.reply_text("⚠️ <b>Usage:</b> /broadcast Your message here")
        return

    broadcast_msg = " ".join(context.args)
    users = get_all_users()
    
    status_msg = await update.message.reply_text(f"🚀 <b>Starting Broadcast...</b>\nTotal Users: {len(users)}", parse_mode="HTML")
    
    success = 0
    failed = 0
    
    for user in users:
        target_id = user["user_id"]
        try:
            await context.bot.send_message(chat_id=target_id, text=broadcast_msg, parse_mode="HTML")
            success += 1
            # Sleep slightly to avoid Telegram flood limits
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
            
    await context.bot.edit_message_text(
        chat_id=user_id,
        message_id=status_msg.message_id,
        text=(
            "✅ <b>Broadcast Completed!</b>\n\n"
            f"🟢 <b>Success:</b> {success}\n"
            f"🔴 <b>Failed:</b> {failed}"
        ),
        parse_mode="HTML"
    )

async def reply_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Allows admin to reply to a specific user via ID."""
    user_id = update.effective_user.id
    
    # Security check: Only Admin
    if str(user_id) not in ADMIN_IDS:
        return

    # Check usage
    if len(context.args) < 2:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b>\n\n<code>/reply [User_ID] [Your Message]</code>",
            parse_mode="HTML"
        )
        return

    target_user_id = context.args[0]
    reply_msg = " ".join(context.args[1:])

    try:
        text_to_send = (
            "📩 <b>Reply from Support (Itachi)</b>\n\n"
            f"{reply_msg}"
        )
        await context.bot.send_message(chat_id=target_user_id, text=text_to_send, parse_mode="HTML")
        await update.message.reply_text(f"✅ <b>Message sent to user</b> <code>{target_user_id}</code>", parse_mode="HTML")
    except Exception as e:
        await update.message.reply_text(f"❌ <b>Failed to send message:</b> {str(e)}", parse_mode="HTML")

async def ban_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to manually ban a user."""
    user_id = update.effective_user.id
    if str(user_id) not in ADMIN_IDS: return

    if not context.args:
        await update.message.reply_text("⚠️ <b>Usage:</b> /ban [User_ID] [Minutes]")
        return

    target_id = context.args[0]
    mins = int(context.args[1]) if len(context.args) > 1 else 1440 # Default 24h
    
    try:
        ban_user(target_id, mins)
        await update.message.reply_text(f"✅ <b>User {target_id} has been banned for {mins} minutes.</b>")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def unban_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to manually unban a user."""
    user_id = update.effective_user.id
    if str(user_id) not in ADMIN_IDS: return

    if not context.args:
        await update.message.reply_text("⚠️ <b>Usage:</b> /unban [User_ID]")
        return

    target_id = context.args[0]
    
    try:
        unban_user(target_id)
        await update.message.reply_text(f"✅ <b>User {target_id} has been unbanned.</b>")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def give_coins_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to give/remove coins from a user."""
    user_id = update.effective_user.id
    if str(user_id) not in ADMIN_IDS:
        return

    target_user_id = None
    amount = 0

    # Case 1: Reply to a user message
    if update.message.reply_to_message:
        if not context.args:
            await update.message.reply_text("⚠️ <b>Usage:</b> Reply to user message with <code>/givecoins [Amount]</code>", parse_mode="HTML")
            return
        try:
            amount = int(context.args[0])
            target_user_id = update.message.reply_to_message.from_user.id
        except ValueError:
            await update.message.reply_text("❌ Amount must be a valid integer.")
            return
    # Case 2: Specific ID and Amount passed
    else:
        if len(context.args) < 2:
            await update.message.reply_text(
                "⚠️ <b>Usage:</b>\n\n"
                "- Reply to a user's message with <code>/givecoins [Amount]</code>\n"
                "- Or use <code>/givecoins [User_ID] [Amount]</code>",
                parse_mode="HTML"
            )
            return
        try:
            target_user_id = int(context.args[0])
            amount = int(context.args[1])
        except ValueError:
            await update.message.reply_text("❌ User ID and Amount must be valid integers.")
            return

    try:
        from database.models import admin_give_coins
        updated_user = admin_give_coins(target_user_id, amount)
        if not updated_user:
            await update.message.reply_text(f"❌ User <code>{target_user_id}</code> not found in database.", parse_mode="HTML")
            return

        new_balance = updated_user.get("coins", 0)
        action = "Added" if amount >= 0 else "Removed"
        abs_amount = abs(amount)

        await update.message.reply_text(
            f"✅ <b>Transaction Successful!</b>\n\n"
            f"👤 <b>User:</b> {updated_user.get('first_name')} (<code>{target_user_id}</code>)\n"
            f"🪙 <b>Action:</b> {action} {abs_amount} coins\n"
            f"💰 <b>New Balance:</b> {new_balance} coins",
            parse_mode="HTML"
        )
        
        # Optionally notify the target user
        try:
            await context.bot.send_message(
                chat_id=target_user_id,
                text=f"🪙 <b>Admin has updated your balance!</b>\n\nAction: {action} {abs_amount} coins\nNew Balance: <b>{new_balance} coins</b>",
                parse_mode="HTML"
            )
        except Exception:
            pass # User might have blocked the bot, ignore
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def stats_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin command to view bot statistics."""
    message = update.message or update.edited_message
    if not message:
        return
        
    user_id = update.effective_user.id
    if str(user_id) not in ADMIN_IDS:
        return

    try:
        users = get_all_users()
        total_users = len(users)
        
        text = (
            "📊 <b>Bot Statistics</b>\n\n"
            f"👥 <b>Total Users:</b> {total_users}"
        )
        await message.reply_text(text, parse_mode="HTML")
    except Exception as e:
        await message.reply_text(f"❌ Error fetching stats: {str(e)}")
