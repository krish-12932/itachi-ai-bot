import aiohttp
import json
import logging
import asyncio
import time
import base64
import re
from telegram import Update
from telegram.ext import ContextTypes
from config import GOOGLE_API_KEY, GOOGLE_API_KEYS, ADMIN_IDS, TELEGRAM_BOT_TOKEN
from database.models import (
    get_user, set_chat_mode, update_user_coins, 
    increment_message_count, update_personality, 
    save_message, get_recent_messages, ban_user
)
from datetime import datetime
from prompts.itachi_prompts import ITACHI_PERSONA_PROMPT
from utils.messages import INSUFFICIENT_COINS_MSG, FORCE_JOIN_MSG
from keyboards.inline import get_join_keyboard
from handlers.start import check_force_join

# Auto-Moderation: Bad words list
BAD_WORDS = ["chutiya", "bhosdi", "madarchod", "mc", "bc", "behenchod", "fuck", "bitch", "asshole", "kutta", "kamina", "randi", "gandu", "laude", "lodu"] # Added common bad words



async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import logging
    logging.info(f"Received message_handler update: {update.message.text if update.message else 'No message'}")
    
    if not update.effective_user:
        logging.warning("No effective user in update")
        return

    user_id = update.effective_user.id

    # Handle AI Context (Topic) reply - check if this is a reply to the ForceReply topic prompt
    if (update.message and update.message.reply_to_message and
        update.message.reply_to_message.text and
        "🧠" in update.message.reply_to_message.text and
        "AI Context" in update.message.reply_to_message.text):
        group_id = context.user_data.pop('pending_topic_group_id', None)
        if group_id:
            topic_text = update.message.text.strip()
            if topic_text:
                from database.group_models import update_group_setting
                update_group_setting(group_id, "group_topic", topic_text)
                await update.message.reply_text(
                    f"✅ **AI Context (Topic) has been set!**\n\n"
                    f"**Topic:** _{topic_text}_\n\n"
                    f"The AI will now use this context when replying in your group.",
                    parse_mode="Markdown"
                )
                return
            else:
                await update.message.reply_text("❌ Topic cannot be empty.")
                return
        else:
            await update.message.reply_text("❌ Session expired. Please run /groupsetup again.")
            return

    # Force Join Check
    if not await check_force_join(update, context):
        await update.message.reply_text(
            FORCE_JOIN_MSG, 
            reply_markup=get_join_keyboard(),
            parse_mode="HTML"
        )
        return
        
    # Group filter: only reply if mentioned or if replying to bot's message
    # (Check this FIRST to avoid unnecessary DB calls for every group message)
    is_group = update.message.chat.type in ["group", "supergroup"]
    if is_group:
        bot_username = context.bot.username
        is_mentioned = f"@{bot_username}" in (update.message.text or "")
        is_reply_to_bot = (
            update.message.reply_to_message and
            update.message.reply_to_message.from_user and
            update.message.reply_to_message.from_user.id == context.bot.id
        )
        if not is_mentioned and not is_reply_to_bot:
            return

    db_user = get_user(user_id)
    
    # If user is not registered in the bot
    if not db_user:
        if is_group:
            # In groups, tell them to start the bot first
            bot_me = await context.bot.get_me()
            await update.message.reply_text(
                f"🔴 <b>Tum abhi meri nazaron me naye ho...</b>\n\n"
                f"Pehle mujhse privately baat karo aur apni pehchaan banao.\n\n"
                f"👉 <a href='https://t.me/{bot_me.username}?start=start'>Bot me /start karo</a>\n\n"
                f"<i>Uske baad tum yahan group me mujhse baat kar paoge.</i>",
                parse_mode="HTML",
                disable_web_page_preview=True
            )
            return
        else:
            # In private chat, auto-register
            from database.models import add_user
            db_user = add_user(user_id, update.effective_user.first_name, update.effective_user.username)
            if not db_user: return

    # 1. Global Ban Check
    from datetime import datetime, timezone
    ban_until = db_user.get("ban_until")
    if ban_until:
        ban_until_dt = datetime.fromisoformat(ban_until.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if now < ban_until_dt:
            remaining = ban_until_dt - now
            mins = remaining.seconds // 60
            secs = remaining.seconds % 60
            await update.message.reply_text(
                f"🛑 <b>You are currently BANNED!</b>\n\nReason: Using prohibited words.\nTime remaining: <b>{mins}m {secs}s</b>\n\nIzanami has trapped you. Learn from your mistakes.",
                parse_mode="HTML"
            )
            return

    is_admin = str(user_id) in ADMIN_IDS

    # 2. Auto-Moderation Check (Bad Words) - Skip for Admins
    if not is_admin:
        import re
        user_message = update.message.text
        if user_message:
            # Match whole words only to avoid false positives (like "branding" matching "randi", or "mcp" matching "mc")
            pattern = r'\b(' + '|'.join(map(re.escape, BAD_WORDS)) + r')\b'
            if re.search(pattern, user_message.lower()):
                # Calculate Ban: 1 min * (current violations + 1)
                violations = db_user.get("violation_count", 0) + 1
                ban_res = ban_user(user_id, violations) # 1 min, 2 min, 3 min...
                
                # Notify Admin
                admin_alert = (
                    "⚠️ <b>Izanami Alert: User Banned!</b>\n\n"
                    f"👤 <b>User:</b> {update.effective_user.full_name}\n"
                    f"🆔 <b>ID:</b> <code>{user_id}</code>\n"
                    f"🚫 <b>Violation #:</b> {violations}\n"
                    f"⏳ <b>Ban Duration:</b> {violations} minute(s)\n\n"
                    f"💬 <b>Message:</b>\n<i>{user_message}</i>"
                )
                try:
                    for admin_id in ADMIN_IDS:
                        await context.bot.send_message(chat_id=admin_id, text=admin_alert, parse_mode="HTML")
                except: pass

                # Reply to User
                await update.message.reply_text(
                    f"🌑 <b>Andhera tumhare dimaag par haavi ho raha hai...</b>\n\n"
                    f"Badtameezi ki wajah se tumhe <b>{violations} minute</b> ke liye ban kiya gaya hai.\n\n"
                    "Izanami tumhara intezar kar rahi hai. Apne lafzon ka sahi upyog karna seekho.",
                    parse_mode="HTML"
                )
                return

    # Admin Check (Unlimited Chat for Admin)

    # Check coins (unless unlimited or admin)
    if not is_admin and not db_user.get("unlimited_chat") and db_user.get("coins", 0) <= 0:
        await update.message.reply_text(INSUFFICIENT_COINS_MSG, parse_mode="Markdown")
        return

    # Deduct coin (only if not admin)
    if not is_admin:
        update_user_coins(user_id, -1)
    
    # Increment message count for personality summary
    count = increment_message_count(user_id)
    if count > 0 and count % 10 == 0:
        # Trigger personality summary update
        await summarize_personality(user_id)

    # Extract and save user message
    user_message = update.message.text
    save_message(user_id, "user", user_message)

    # Send typing action
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except Exception:
        pass

    # Send initial placeholder message
    try:
        placeholder_msg = await update.message.reply_text("Replying...")
    except Exception as e:
        logging.error(f"Failed to send placeholder: {e}")
        return
    
    full_response = ""
    system_prompt = ITACHI_PERSONA_PROMPT
    if db_user.get("personality_summary"):
        system_prompt += f"\n\nHistorical Context (Use for tone only): {db_user.get('personality_summary')}"
        
    
    # Use primary + fallback models (tries in order)
    models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
    
    # Structure contents for Gemini (History only)
    contents = []
    history = get_recent_messages(user_id, limit=6)
    for msg in reversed(history):
        role = "user" if msg['role'] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg['content']}]})
    
    # Add current message
    contents.append({"role": "user", "parts": [{"text": user_message}]})
    
    last_update_time = 0
    last_typing_time = time.time()
    
    for api_key in GOOGLE_API_KEYS:
        for model_name in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:streamGenerateContent?alt=sse&key={api_key}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": contents,
                "system_instruction": {"parts": [{"text": system_prompt}]},
                "tools": [{"google_search": {}}]
            }
            
            try:
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status == 429:
                            logging.warning(f"⚠️ Key {api_key[:8]}... rate limited (429) for {model_name}. Trying next model...")
                            continue # try fallback model on same key
                        
                        if resp.status == 503:
                            await asyncio.sleep(2)
                            continue
                        
                        if resp.status != 200:
                            err_body = await resp.text()
                            logging.error(f"❌ Gemini API Error ({model_name}) Status {resp.status}: {err_body}")
                            continue
                        
                        async for line in resp.content:
                            if not line: continue
                            line_str = line.decode('utf-8').strip()
                            if line_str.startswith("data: "):
                                data_content = line_str[6:]
                                if data_content == "[DONE]": break
                                
                                try:
                                    chunk = json.loads(data_content)
                                    if 'candidates' in chunk:
                                        content = chunk['candidates'][0]['content']['parts'][0].get('text', '')
                                        full_response += content
                                    
                                    if time.time() - last_update_time > 0.8 and full_response:
                                        # Send typing action every 4 seconds to keep the status alive
                                        if time.time() - last_typing_time > 4.0:
                                            try:
                                                await context.bot.send_chat_action(chat_id=user_id, action="typing")
                                                last_typing_time = time.time()
                                            except Exception:
                                                pass
                                                
                                        try:
                                            await context.bot.edit_message_text(
                                                chat_id=placeholder_msg.chat_id,
                                                message_id=placeholder_msg.message_id,
                                                text=full_response + " ▎",
                                                parse_mode="Markdown"
                                            )
                                            last_update_time = time.time()
                                        except Exception:
                                            pass # Ignore edit errors during streaming
                                except Exception:
                                    continue
    
                        # Final update
                        await context.bot.edit_message_text(
                            chat_id=placeholder_msg.chat_id,
                            message_id=placeholder_msg.message_id,
                            text=full_response or "🌑 Itachi remains silent...",
                            parse_mode="Markdown"
                        )
                        if full_response:
                            save_message(user_id, "bot", full_response)
                            return # SUCCESS! Exit the function
                                
            except Exception as e:
                logging.error(f"Error with model {model_name} on key {api_key[:8]}...: {e}")
                continue # Try next model or key
            
    # If all models fail
    await context.bot.edit_message_text(
        chat_id=placeholder_msg.chat_id,
        message_id=placeholder_msg.message_id,
        text="🌑 Itachi is meditating... (All models failed. Try again later.)"
    )

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
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
    
    # Admin Check
    is_admin = str(user_id) in ADMIN_IDS
    if not is_admin and not db_user.get("unlimited_chat") and db_user.get("coins", 0) <= 0:
        await update.message.reply_text(INSUFFICIENT_COINS_MSG, parse_mode="HTML")
        return

    # Deduct coin
    if not is_admin:
        update_user_coins(user_id, -1)

    # Send typing action
    try:
        await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
    except Exception:
        pass

    placeholder_msg = await update.message.reply_text("Analyzing image... 👁️🗨️")
    
    # Get the photo
    photo_file = await update.message.photo[-1].get_file()
    image_data = await photo_file.download_as_bytearray()
    base64_image = base64.b64encode(image_data).decode('utf-8')
    
    # Prepare prompt
    user_caption = update.message.caption or "What is in this image? Summarize it."
    save_message(user_id, "user", f"[Image] {user_caption}")

    system_prompt = ITACHI_PERSONA_PROMPT
    if db_user.get("personality_summary"):
        system_prompt += f"\n\nAdditional information about this person: {db_user.get('personality_summary')}"

    payload = {
        "contents": [
            {
                "parts": [
                    {"text": f"SYSTEM PROMPT: {system_prompt}\n\nUSER CAPTION: {user_caption}"},
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": base64_image
                        }
                    }
                ]
            }
        ]
    }

    full_response = ""
    models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]

    for api_key in GOOGLE_API_KEYS:
        for model_name in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            headers = {"Content-Type": "application/json"}
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status == 429:
                            logging.warning(f"Rate limited (429) for photo on {model_name} key {api_key[:8]}...")
                            continue
                        if resp.status == 200:
                            data = await resp.json()
                            if 'candidates' in data and data['candidates']:
                                full_response = data['candidates'][0]['content']['parts'][0]['text'].strip()
                                break
                        else:
                            err_body = await resp.text()
                            logging.error(f"Photo error ({model_name}) Status {resp.status}: {err_body}")
                if full_response:
                    break
            except Exception as e:
                logging.error(f"Photo analysis error on {model_name} key {api_key[:8]}: {e}")
                continue
        if full_response:
            break

    if full_response:
        await context.bot.edit_message_text(
            chat_id=placeholder_msg.chat_id,
            message_id=placeholder_msg.message_id,
            text=full_response,
            parse_mode="Markdown"
        )
        save_message(user_id, "bot", full_response)
    else:
        await context.bot.edit_message_text(
            chat_id=placeholder_msg.chat_id,
            message_id=placeholder_msg.message_id,
            text="🌑 Itachi remains silent... (Image analysis failed.)"
        )


async def summarize_personality(user_id: int):
    recent_msgs = get_recent_messages(user_id, 10)
    if not recent_msgs:
        return
    
    db_user = get_user(user_id)
    current_personality = db_user.get("personality_summary", "")
    
    conversation_text = "\n".join([f"{m['role']}: {m['content']}" for m in recent_msgs])
    
    prompt = f"""
    Based on the following conversation snippets, update the user's personality and fact profile. 
    Keep it concise and focus on new facts (name, age, likes, dislikes, habits).
    
    STRICT RULES:
    1. Output ONLY the consolidated profile.
    2. Use HTML tags for formatting: <b>Bold Text</b> for categories.
    3. Do NOT use Markdown symbols like ** or *.
    4. Write it in a clean, professional, and easy-to-read way.
    
    Previous Profile: {current_personality}
    
    Recent Conversation:
    {conversation_text}
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }

    models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
    for api_key in GOOGLE_API_KEYS:
        for model_name in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            headers = {
                "Content-Type": "application/json"
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(url, headers=headers, json=payload) as resp:
                        if resp.status == 429:
                            logging.warning(f"⚠️ Key {api_key[:8]}... rate limited (429) for summary on {model_name}. Trying next...")
                            continue
                        if resp.status == 200:
                            data = await resp.json()
                            if 'candidates' in data and data['candidates']:
                                new_summary = data['candidates'][0]['content']['parts'][0]['text'].strip()
                                update_personality(user_id, new_summary)
                                return
                        else:
                            err_body = await resp.text()
                            logging.error(f"Summary error ({model_name}) Status {resp.status}: {err_body}")
            except Exception as e:
                logging.error(f"Personality summarization error on {model_name} key {api_key[:8]}: {e}")
                continue

async def answer_guest_query_http(guest_query_id: str, text: str, parse_mode="Markdown", reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerGuestQuery"
    result_obj = {
        "type": "article",
        "id": "1",
        "title": "Reply",
        "input_message_content": {
            "message_text": text[:4000],
            "parse_mode": parse_mode
        }
    }
    if reply_markup:
        result_obj["reply_markup"] = reply_markup
        
    payload = {
        "guest_query_id": guest_query_id,
        "result": result_obj
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            return await resp.json()

async def handle_guest_message(guest_msg: dict, context):
    user_data = guest_msg.get('from', {})
    user_id = user_data.get('id')
    if not user_id: return
    
    first_name = user_data.get('first_name', 'User')
    username = user_data.get('username', '')
    raw_text = guest_msg.get('text', '')
    guest_query_id = guest_msg.get('guest_query_id')
    
    if not guest_query_id:
        return
        
    # Clean text (remove @username mention)
    user_message = re.sub(r"^@\w+\s*", "", raw_text).strip()
    if not user_message:
        user_message = "Hello Itachi"
        
    # DB User check (No auto-registration in groups)
    db_user = get_user(user_id)
    if not db_user:
        reg_msg = (
            "🛑 <b>Access Denied!</b>\n\n"
            "You must start the bot in private chat to use this bot.\n"
            "Please click the button below to start."
        )
        reply_markup = {
            "inline_keyboard": [[{"text": "Start Bot 🤖", "url": "https://t.me/Itachi_Gpt_bot?start=1"}]]
        }
        await answer_guest_query_http(guest_query_id, reg_msg, parse_mode="HTML", reply_markup=reply_markup)
        return

    # Force Join Check
    from config import FORCE_JOIN_CHANNELS
    is_joined = True
    for channel in FORCE_JOIN_CHANNELS:
        try:
            member = await context.bot.get_chat_member(chat_id=channel["id"], user_id=user_id)
            if member.status in ['left', 'kicked', 'restricted']:
                is_joined = False
                break
        except Exception:
            is_joined = False
            break

    if not is_joined:
        join_msg = (
            "🛑 <b>Access Denied!</b>\n\n"
            "You must join our official channel to use this bot.\n"
            "Please join and then click /start again."
        )
        
        inline_keyboard = []
        for channel in FORCE_JOIN_CHANNELS:
            inline_keyboard.append([{"text": f"Join Channel {channel['index']} 📣", "url": channel['link']}])
            
        reply_markup = {"inline_keyboard": inline_keyboard} if inline_keyboard else None
        
        await answer_guest_query_http(guest_query_id, join_msg, parse_mode="HTML", reply_markup=reply_markup)
        return
        
    # Ban Check
    from datetime import datetime, timezone
    ban_until = db_user.get("ban_until")
    if ban_until:
        ban_until_dt = datetime.fromisoformat(ban_until.replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        if now < ban_until_dt:
            await answer_guest_query_http(guest_query_id, "🛑 You are currently BANNED from using Izanami AI.")
            return

    # Check Coins
    is_admin = str(user_id) in ADMIN_IDS
    if not is_admin and not db_user.get("unlimited_chat") and db_user.get("coins", 0) <= 0:
        await answer_guest_query_http(
            guest_query_id, 
            "⚠️ *Insufficient Coins!*\n\nYou don't have enough coins to chat. Check /plan in private chat for options.", 
            parse_mode="Markdown"
        )
        return

    # Deduct coin
    if not is_admin:
        update_user_coins(user_id, -1)
        
    # Save user message
    save_message(user_id, "user", user_message)

    # Generate response (Non-streaming for Guest Mode)
    full_response = ""
    system_prompt = ITACHI_PERSONA_PROMPT
    if db_user.get("personality_summary"):
        system_prompt += f"\n\nHistorical Context: {db_user.get('personality_summary')}"
        
    models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
    contents = []
    history = get_recent_messages(user_id, limit=6)
    for msg in reversed(history):
        role = "user" if msg['role'] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": msg['content']}]})
    contents.append({"role": "user", "parts": [{"text": user_message}]})
    
    for api_key in GOOGLE_API_KEYS:
        if full_response:
            break
        for model_name in models:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            payload = {
                "contents": contents,
                "system_instruction": {"parts": [{"text": system_prompt}]}
            }
            try:
                timeout = aiohttp.ClientTimeout(total=30)
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(url, headers={"Content-Type": "application/json"}, json=payload) as resp:
                        if resp.status == 429:
                            logging.warning(f"⚠️ Key {api_key[:8]}... rate limited (429) for guest {model_name}. Trying next key...")
                            break
                        if resp.status == 200:
                            data = await resp.json()
                            if "candidates" in data and data["candidates"]:
                                full_response = data["candidates"][0]["content"]["parts"][0].get("text", "")
                                break
            except Exception as e:
                logging.error(f"Guest AI error {model_name} on key {api_key[:8]}: {e}")
                continue
            
    if not full_response:
        full_response = "🌑 Andhera chha gaya hai... kripya thodi der baad prayaas karein."

    save_message(user_id, "bot", full_response)
    
    # Send Guest Reply via HTTP
    res = await answer_guest_query_http(guest_query_id, full_response, parse_mode="Markdown")
    print(f"Guest reply status: {res}")


async def business_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles messages received via Telegram Business (on behalf of the user)."""
    business_msg = update.business_message
    if not business_msg: return
    
    # We are acting on behalf of the business account owner, talking TO the sender.
    connection_id = business_msg.business_connection_id
    user_message = business_msg.text
    
    if not user_message:
        return
        
    # Send placeholder message
    try:
        placeholder_msg = await context.bot.send_message(
            chat_id=business_msg.chat.id,
            text="Replying...",
            business_connection_id=connection_id
        )
    except Exception as e:
        print(f"Failed to send business placeholder: {e}")
        return

    full_response = ""
    system_prompt = ITACHI_PERSONA_PROMPT + "\n\n[BUSINESS ASSISTANT MODE]: You are replying on behalf of a user's personal Telegram account. Maintain your Itachi persona, but act as their personal assistant. Reply directly to the user who messaged them."
    
    models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
    contents = [{"role": "user", "parts": [{"text": user_message}]}]
    
    last_update_time = 0
    
    for model_name in models:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:streamGenerateContent?alt=sse&key={GOOGLE_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": contents,
            "system_instruction": {"parts": [{"text": system_prompt}]}
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, json=payload) as resp:
                    if resp.status != 200: continue
                    
                    async for line in resp.content:
                        if not line: continue
                        line_str = line.decode('utf-8').strip()
                        if line_str.startswith("data: "):
                            data_content = line_str[6:]
                            if data_content == "[DONE]": break
                            
                            try:
                                chunk = json.loads(data_content)
                                if 'candidates' in chunk:
                                    content = chunk['candidates'][0]['content']['parts'][0].get('text', '')
                                    full_response += content
                                
                                if time.time() - last_update_time > 0.8 and full_response:
                                    try:
                                        await context.bot.edit_message_text(
                                            chat_id=business_msg.chat.id,
                                            message_id=placeholder_msg.message_id,
                                            text=full_response + " ▎",
                                            parse_mode="Markdown",
                                            business_connection_id=connection_id
                                        )
                                        last_update_time = time.time()
                                    except Exception:
                                        pass
                            except Exception:
                                continue

                    # Final update
                    await context.bot.edit_message_text(
                        chat_id=business_msg.chat.id,
                        message_id=placeholder_msg.message_id,
                        text=full_response or "🌑 Itachi remains silent...",
                        parse_mode="Markdown",
                        business_connection_id=connection_id
                    )
                    return # SUCCESS
                            
        except Exception as e:
            print(f"Error with model {model_name}: {e}")
            continue
            
    # If all models fail
    try:
        await context.bot.edit_message_text(
            chat_id=business_msg.chat.id,
            message_id=placeholder_msg.message_id,
            text="🌑 System disruption... I cannot answer right now.",
            business_connection_id=connection_id
        )
    except: pass
