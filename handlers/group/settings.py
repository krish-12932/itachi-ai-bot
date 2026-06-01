import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database.group_models import get_group_settings, init_group_settings, update_group_setting

logger = logging.getLogger(__name__)

async def get_settings_keyboard(group_id: int):
    settings = get_group_settings(group_id)
    if not settings:
        return None

    punishment = settings.get("punishment_mode", "ban")
    punishment_label = "🔨 Ban" if punishment == "ban" else "🔇 Mute"

    kb = [
        [InlineKeyboardButton(f"👋 Welcome Message: {'✅ ON' if settings.get('welcome_enabled', True) else '❌ OFF'}", callback_data=f"gset_welon_{group_id}")],
        [InlineKeyboardButton(f"🗑 Auto-Delete Welcome: {'✅ ON' if settings.get('auto_delete_welcome') else '❌ OFF'}", callback_data=f"gset_delwel_{group_id}")],
        [InlineKeyboardButton(f"🛡 Anti-Spam: {'✅ ON' if settings['anti_spam'] else '❌ OFF'}", callback_data=f"gset_spam_{group_id}")],
        [InlineKeyboardButton(f"🔗 Anti-Link (Warn): {'✅ ON' if settings['anti_link'] else '❌ OFF'}", callback_data=f"gset_link_{group_id}")],
        [InlineKeyboardButton(f"🔇 Anti-Link (Silent): {'✅ ON' if settings.get('anti_link_silent') else '❌ OFF'}", callback_data=f"gset_linksilent_{group_id}")],
        [InlineKeyboardButton(f"🖼 Anti-Media: {'✅ ON' if settings.get('anti_media') else '❌ OFF'}", callback_data=f"gset_media_{group_id}")],
        [InlineKeyboardButton(f"📨 Anti-Forward: {'✅ ON' if settings.get('anti_forward') else '❌ OFF'}", callback_data=f"gset_fwd_{group_id}")],
        [InlineKeyboardButton(f"🤖 AI Help: {'✅ ON' if settings['ai_help'] else '❌ OFF'}", callback_data=f"gset_ai_{group_id}")],
        [InlineKeyboardButton(f"🗣 Proactive AI: {'✅ ON' if settings['proactive_ai'] else '❌ OFF'}", callback_data=f"gset_proai_{group_id}")],
        [InlineKeyboardButton(f"⚖️ Punishment: {punishment_label}", callback_data=f"gset_punish_{group_id}")],
        [InlineKeyboardButton("✖️ Close Menu", callback_data="gset_close")]
    ]
    return InlineKeyboardMarkup(kb)

async def groupsetup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    # Must be in private chat
    if chat.type != "private":
        await update.message.reply_text("❌ Please use this command in my private chat (DM).")
        return

    # Check for group ID argument
    if not context.args:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        bot_username = context.bot.username
        add_url = f"https://t.me/{bot_username}?startgroup=true&admin=change_info+delete_messages+restrict_members+invite_users+pin_messages+manage_video_chats+promote_members+anonymous"
        
        keyboard = [[InlineKeyboardButton("➕ Add Bot to your Group", url=add_url)]]
        
        await update.message.reply_text(
            "⚠️ **How to setup a Group:**\n\n"
            "1. First, add me to your group as an Admin using the button below.\n"
            "2. Once added, I will automatically set up the group and give you the Settings Menu!\n\n"
            "_Already added? Use:_ `/groupsetup [GROUP_ID]`",
            reply_markup=InlineKeyboardMarkup(keyboard),
            parse_mode="Markdown"
        )
        return

    try:
        group_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid Group ID.")
        return

    # Check if user is owner or admin in that group
    try:
        member = await context.bot.get_chat_member(chat_id=group_id, user_id=user.id)
    except Exception:
        # Sometimes users forget the -100 prefix for supergroups
        try:
            group_id = int(f"-100{abs(group_id)}")
            member = await context.bot.get_chat_member(chat_id=group_id, user_id=user.id)
        except Exception as e:
            logger.error(f"Error checking group admin status: {e}")
            await update.message.reply_text("❌ Could not find that group. Make sure I am added to the group and you entered the correct ID (including the -100 prefix).")
            return

    try:
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("❌ You are not an admin of that group.")
            return
            
        group_chat = await context.bot.get_chat(chat_id=group_id)
        group_title = group_chat.title
    except Exception as e:
        logger.error(f"Error fetching group info: {e}")
        await update.message.reply_text("❌ Could not fetch group info.")
        return

    # Initialize settings if they don't exist
    init_group_settings(group_id, user.id)
    
    keyboard = await get_settings_keyboard(group_id)
    await update.message.reply_text(
        f"⚙️ *Group Setup for {group_title}*\n\n"
        f"*What each setting does:*\n"
        f"🛡 *Anti-Spam* — 5 messages in 10 sec = warning. 3 warnings = punishment.\n"
        f"🔗 *Anti-Link (Warn)* — Links/Bot promotions delete ho jaate hain. 3 warnings = punishment.\n"
        f"🔇 *Anti-Link (Silent)* — Links silently delete ho jaate hain. Koi warning nahi, koi ban nahi.\n"
        f"🖼 *Anti-Media* — Photos, Videos, GIFs, Stickers silently delete. Koi warning nahi.\n"
        f"📨 *Anti-Forward* — Kisi bhi channel/group se forward hua message delete. Koi warning nahi.\n"
        f"🤖 *AI Help* — Jab koi @{context.bot.username} ko tag kare ya seedha puchhe.\n"
        f"🗣 *Proactive AI* — Bot khud bolta hai jab group me help ki zaroorat lage.\n"
        f"⚖️ *Punishment* — 3 warnings ke baad Ban karna hai ya sirf Mute.\n\n"
        f"_Buttons click karke toggle karein:_",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

async def group_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    user = update.effective_user
    chat = update.effective_chat
    
    # We only process if it starts with gset_
    if not data.startswith("gset_"):
        return
        
    await query.answer()

    if data == "gset_close":
        await query.edit_message_text("⚙️ Setup menu closed.")
        return

    # Extract setting type and group_id
    # Format: gset_{setting_type}_{group_id}
    parts = data.split("_")
    setting_type = parts[1]
    group_id = int(parts[2])
    
    # Security check: only admins can toggle
    try:
        member = await context.bot.get_chat_member(chat_id=group_id, user_id=user.id)
        if member.status not in ["creator", "administrator"]:
            await query.answer("❌ Only admins of that group can change settings!", show_alert=True)
            return
    except Exception as e:
        logger.error(f"Error checking admin status in callback: {e}")
        await query.answer("❌ Could not verify your admin status.", show_alert=True)
        return

    settings = get_group_settings(group_id)
    if not settings:
        return

    # Toggle logic for on/off settings
    key_map = {
        "spam": "anti_spam",
        "link": "anti_link",
        "linksilent": "anti_link_silent",
        "media": "anti_media",
        "fwd": "anti_forward",
        "delwel": "auto_delete_welcome",
        "welon": "welcome_enabled",
        "ai": "ai_help",
        "proai": "proactive_ai"
    }
    
    if setting_type in key_map:
        db_key = key_map[setting_type]
        new_val = not settings[db_key]
        update_group_setting(group_id, db_key, new_val)
        keyboard = await get_settings_keyboard(group_id)
        await query.edit_message_reply_markup(reply_markup=keyboard)
    
    elif setting_type == "punish":
        # Toggle between ban and mute
        current = settings.get("punishment_mode", "ban")
        new_mode = "mute" if current == "ban" else "ban"
        update_group_setting(group_id, "punishment_mode", new_mode)
        await query.answer(f"⚖️ Punishment mode changed to {'🔨 Ban' if new_mode == 'ban' else '🔇 Mute'}!", show_alert=True)
        keyboard = await get_settings_keyboard(group_id)
        await query.edit_message_reply_markup(reply_markup=keyboard)

async def setwelcome_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    user = update.effective_user
    
    group_id = None
    new_message = ""
    
    if chat.type == "private":
        if not context.args or len(context.args) < 2:
            await update.message.reply_text(
                "❌ **To set the welcome message in private chat:**\n\n"
                "You must provide the Group ID first.\n"
                "`/setwelcome -100XXXXX Your custom message here...`\n\n"
                "_(You can find your Group ID in the settings menu message)_", 
                parse_mode="Markdown"
            )
            return
            
        try:
            group_id = int(context.args[0])
            new_message = " ".join(context.args[1:])
        except ValueError:
            await update.message.reply_text("❌ Invalid Group ID. It must be a number starting with -100.")
            return
    else:
        group_id = chat.id
        if not context.args:
            await update.message.reply_text(
                "⚠️ **How to set a custom welcome message here:**\n\n"
                "`/setwelcome Welcome to the best group, {name}!`\n\n"
                "_(You can also do this in my private DM to avoid spamming the group)_",
                parse_mode="Markdown"
            )
            return
        new_message = " ".join(context.args)

    # Security check: must be admin
    try:
        member = await context.bot.get_chat_member(chat_id=group_id, user_id=user.id)
        if member.status not in ["creator", "administrator"]:
            await update.message.reply_text("❌ Only group admins can change the welcome message.")
            return
    except Exception as e:
        logger.error(f"Error checking admin status for setwelcome: {e}")
        await update.message.reply_text("❌ I couldn't verify your admin status. Make sure I am in that group and the ID is correct.")
        return

    # Update database
    from database.group_models import init_group_settings
    init_group_settings(group_id, user.id)
    
    update_group_setting(group_id, "welcome_message", new_message)
    
    await update.message.reply_text(
        "✅ **Custom Welcome Message Set!**\n\n"
        "Here is a preview of how it will look in the group:\n\n"
        f"👋 Hello Naruto!\n\n{new_message.replace('{name}', 'Naruto')}",
        parse_mode="Markdown"
    )
