import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from database.group_models import get_group_settings, init_group_settings, update_group_setting

logger = logging.getLogger(__name__)

async def get_info_keyboard(group_id: int):
    """Page 1: Info/Description page with a button to go to toggles."""
    kb = [
        [InlineKeyboardButton("⚙️ Open Toggle Settings →", callback_data=f"gset_page2_{group_id}")],
        [InlineKeyboardButton("✖️ Close", callback_data="gset_close")]
    ]
    return InlineKeyboardMarkup(kb)

async def get_settings_keyboard(group_id: int):
    settings = get_group_settings(group_id)
    if not settings:
        return None

    punishment = settings.get("punishment_mode", "ban")
    punishment_label = "🔨 Ban" if punishment == "ban" else "🔇 Mute"
    
    # Conflict detection: if both Anti-Link modes are ON, show warning
    link_warn = settings.get("anti_link", False)
    link_silent = settings.get("anti_link_silent", False)
    link_warn_label = f"🔗 Anti-Link (Warn): {'✅ ON' if link_warn else '❌ OFF'}{' ⚠️' if link_warn and link_silent else ''}"
    link_silent_label = f"🔇 Anti-Link (Silent): {'✅ ON' if link_silent else '❌ OFF'}{' ⚠️' if link_warn and link_silent else ''}"

    topic_on = bool(settings.get("group_topic"))
    kb = [
        [InlineKeyboardButton(f"👋 Welcome Msg: {'✅ ON' if settings.get('welcome_enabled', True) else '❌ OFF'}", callback_data=f"gset_welon_{group_id}"),
         InlineKeyboardButton(f"🗑 Auto-Del: {'✅ ON' if settings.get('auto_delete_welcome') else '❌ OFF'}", callback_data=f"gset_delwel_{group_id}")],
        [InlineKeyboardButton(f"🛡 Anti-Spam: {'✅ ON' if settings['anti_spam'] else '❌ OFF'}", callback_data=f"gset_spam_{group_id}")],
        [InlineKeyboardButton(link_warn_label, callback_data=f"gset_link_{group_id}")],
        [InlineKeyboardButton(link_silent_label, callback_data=f"gset_linksilent_{group_id}")],
        [InlineKeyboardButton(f"🖼 Anti-Media: {'✅ ON' if settings.get('anti_media') else '❌ OFF'}", callback_data=f"gset_media_{group_id}"),
         InlineKeyboardButton(f"📨 Anti-Fwd: {'✅ ON' if settings.get('anti_forward') else '❌ OFF'}", callback_data=f"gset_fwd_{group_id}")],
        [InlineKeyboardButton(f"🤖 AI Help: {'✅ ON' if settings['ai_help'] else '❌ OFF'}", callback_data=f"gset_ai_{group_id}"),
         InlineKeyboardButton(f"🗣 Proactive AI: {'✅ ON' if settings['proactive_ai'] else '❌ OFF'}", callback_data=f"gset_proai_{group_id}")],
        [InlineKeyboardButton(f"🧠 AI Context (Topic): {'✅ ON' if topic_on else '❌ OFF'}", callback_data=f"gset_topic_{group_id}")],
        [InlineKeyboardButton(f"⚖️ Punishment: {punishment_label}", callback_data=f"gset_punish_{group_id}")],
        [InlineKeyboardButton("← Back to Info", callback_data=f"gset_page1_{group_id}"),
         InlineKeyboardButton("✖️ Close", callback_data="gset_close")]
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
    
    # Show PAGE 1: Info page first
    info_text = f"""⚙️ *Group Setup — {group_title}*

*📖 What each setting does:*
――――――――――――――――――――
👋 *Welcome Msg* — Sends a welcome message to new members.
🗑 *Auto-Delete Welcome* — Automatically deletes the welcome msg after 2 mins.
――――――――――――――――――――
🛡 *Anti-Spam* — 5 messages in 10 sec = warning. 3 warnings = punishment.
――――――――――――――――――――
🔗 *Anti-Link (Warn)* — Deletes links/promotions + issues a warning. 3 warnings = punishment.
🔇 *Anti-Link (Silent)* — Silently deletes links. No warnings, no bans.
⚠️ _Tip: Do not turn both ON — If Warn is ON, keep Silent OFF._
――――――――――――――――――――
🖼 *Anti-Media* — Silently deletes Photos, Videos, GIFs, Stickers, Emojis.
📨 *Anti-Forward* — Deletes any forwarded messages from other channels/groups.
――――――――――――――――――――
🤖 *AI Help* — Itachi replies when tagged or asked a question.
🗣 *Proactive AI* — Bot randomly speaks up when the group needs help.
🧠 *AI Context (Topic)* — Set a topic to guide AI responses in your group.
――――――――――――――――――――
⚖️ *Punishment* — Choose to Ban or Mute after 3 warnings."""

    info_keyboard = await get_info_keyboard(group_id)
    await update.message.reply_text(info_text, reply_markup=info_keyboard, parse_mode="Markdown")

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

    # Handle Page Navigation
    if data.startswith("gset_page1_"):
        group_id = int(data.split("_")[2])
        # Security check
        try:
            member = await context.bot.get_chat_member(chat_id=group_id, user_id=user.id)
            if member.status not in ["creator", "administrator"]:
                await query.answer("❌ Only admins can change settings!", show_alert=True)
                return
            group_chat = await context.bot.get_chat(chat_id=group_id)
            group_title = group_chat.title
        except Exception:
            await query.answer("❌ Error.", show_alert=True)
            return
            
        info_text = f"""⚙️ *Group Setup — {group_title}*

*📖 What each setting does:*
――――――――――――――――――――
👋 *Welcome Msg* — Sends a welcome message to new members.
🗑 *Auto-Delete Welcome* — Automatically deletes the welcome msg after 2 mins.
――――――――――――――――――――
🛡 *Anti-Spam* — 5 messages in 10 sec = warning. 3 warnings = punishment.
――――――――――――――――――――
🔗 *Anti-Link (Warn)* — Deletes links/promotions + issues a warning. 3 warnings = punishment.
🔇 *Anti-Link (Silent)* — Silently deletes links. No warnings, no bans.
⚠️ _Tip: Do not turn both ON — If Warn is ON, keep Silent OFF._
――――――――――――――――――――
🖼 *Anti-Media* — Silently deletes Photos, Videos, GIFs, Stickers, Emojis.
📨 *Anti-Forward* — Deletes any forwarded messages from other channels/groups.
――――――――――――――――――――
🤖 *AI Help* — Itachi replies when tagged or asked a question.
🗣 *Proactive AI* — Bot randomly speaks up when the group needs help.
――――――――――――――――――――
⚖️ *Punishment* — Choose to Ban or Mute after 3 warnings."""
        info_keyboard = await get_info_keyboard(group_id)
        await query.edit_message_text(info_text, reply_markup=info_keyboard, parse_mode="Markdown")
        return

    if data.startswith("gset_page2_"):
        group_id = int(data.split("_")[2])
        # Security check
        try:
            member = await context.bot.get_chat_member(chat_id=group_id, user_id=user.id)
            if member.status not in ["creator", "administrator"]:
                await query.answer("❌ Only admins can change settings!", show_alert=True)
                return
        except Exception:
            await query.answer("❌ Error.", show_alert=True)
            return
            
        keyboard = await get_settings_keyboard(group_id)
        await query.edit_message_text("⚙️ *Select toggles to enable/disable features:*", reply_markup=keyboard, parse_mode="Markdown")
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
        "proai": "proactive_ai",
        "promoai": "ai_promo_detect"
    }
    
    if setting_type in key_map:
        db_key = key_map[setting_type]
        new_val = not settings.get(db_key, False)
        update_group_setting(group_id, db_key, new_val)
        keyboard = await get_settings_keyboard(group_id)
        await query.edit_message_reply_markup(reply_markup=keyboard)
        
    elif setting_type == "topic":
        from telegram import ForceReply
        current = settings.get("group_topic")
        if current:
            # Turn OFF (clear topic)
            update_group_setting(group_id, "group_topic", None)
            await query.answer("🧠 AI Context cleared and disabled.", show_alert=True)
            keyboard = await get_settings_keyboard(group_id)
            await query.edit_message_reply_markup(reply_markup=keyboard)
        else:
            # Store group_id in user_data for the reply handler
            context.user_data['pending_topic_group_id'] = group_id
            # Turn ON (prompt for topic) - no parse_mode to keep backticks literal
            await query.message.reply_text(
                f"🧠 AI Context Setup\n\nPlease reply to this message with the topic or rules of your group.\n\nExample: This is a community for Naruto fans to discuss anime and manga.\n\nGroup ID: {group_id}",
                reply_markup=ForceReply(selective=True)
            )
            await query.answer("Please reply to the message sent.", show_alert=True)
    
    elif setting_type == "punish":
        # Toggle between ban and mute
        current = settings.get("punishment_mode", "ban")
        new_mode = "mute" if current == "ban" else "ban"
        update_group_setting(group_id, "punishment_mode", new_mode)
        await query.answer(f"⚖️ Punishment mode changed to {'🔨 Ban' if new_mode == 'ban' else '🔇 Mute'}!", show_alert=True)
        keyboard = await get_settings_keyboard(group_id)
        await query.edit_message_reply_markup(reply_markup=keyboard)

async def handle_topic_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles reply to the AI Context (Topic) prompt - saves topic to database."""
    if not update.message or not update.message.reply_to_message:
        return

    reply_to = update.message.reply_to_message
    if not reply_to.text:
        return

    if "🧠" not in reply_to.text or "AI Context" not in reply_to.text:
        return

    # Get group_id from user_data (stored when toggle was clicked)
    group_id = context.user_data.pop('pending_topic_group_id', None)
    if not group_id:
        await update.message.reply_text("❌ Session expired. Please run /groupsetup again.")
        return

    topic_text = update.message.text.strip()

    if not topic_text:
        await update.message.reply_text("❌ Topic cannot be empty.")
        return

    update_group_setting(group_id, "group_topic", topic_text)

    await update.message.reply_text(
        f"✅ **AI Context (Topic) has been set!**\n\n"
        f"**Topic:** _{topic_text}_\n\n"
        f"The AI will now use this context when replying in your group.",
        parse_mode="Markdown"
    )


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
