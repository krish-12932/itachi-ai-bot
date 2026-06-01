import logging
import aiohttp
import json
import random
from telegram import Update
from telegram.ext import ContextTypes

from config import GOOGLE_API_KEYS
from prompts.itachi_prompts import ITACHI_PERSONA_PROMPT
from database.group_models import get_group_settings, save_group_ai_message

logger = logging.getLogger(__name__)

async def group_ai_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles AI logic for group chats (Tagged, Smart Help, Proactive)"""
    if not update.message or not update.message.text or not update.effective_chat:
        return
        
    chat = update.effective_chat
    user = update.effective_user
    msg_text = update.message.text
    
    settings = get_group_settings(chat.id)
    if not settings:
        return
        
    ai_help_on = settings.get("ai_help", False)
    proactive_on = settings.get("proactive_ai", False)
    
    bot_username = context.bot.username
    is_mentioned = f"@{bot_username}" in msg_text
    is_reply_to_bot = (
        update.message.reply_to_message and
        update.message.reply_to_message.from_user and
        update.message.reply_to_message.from_user.id == context.bot.id
    )
    
    context_type = None
    
    if is_mentioned or is_reply_to_bot:
        context_type = "tagged"
    elif ai_help_on:
        # Smart detection of problems/questions
        lower_msg = msg_text.lower()
        problem_keywords = ["help", "how to", "kaise", "kese", "error", "bug", "problem", "issue", "batao", "koi bata sakta"]
        if "?" in msg_text or any(k in lower_msg for k in problem_keywords):
            context_type = "smart_help"
            
    if not context_type and proactive_on:
        # Proactive: 2% chance to respond randomly to keep chat alive
        if random.random() < 0.02:
            context_type = "proactive"
            
    if not context_type:
        return # No AI action needed

    # Clean the message text from tags
    clean_msg = msg_text.replace(f"@{bot_username}", "").strip()

    # Generate response via Gemini
    if not GOOGLE_API_KEYS:
        return
        
    api_key = GOOGLE_API_KEYS[0]
    
    # Adjust prompt based on context
    system_prompt = ITACHI_PERSONA_PROMPT
    if context_type == "smart_help":
        system_prompt += "\n\n[CONTEXT]: You are jumping into a group conversation to help a user who seems to have a question or problem. Be helpful but maintain your persona."
    elif context_type == "proactive":
        system_prompt += "\n\n[CONTEXT]: You are proactively joining the group conversation. Make a brief, witty, or observational comment in character."

    payload = {
        "contents": [{"role": "user", "parts": [{"text": clean_msg}]}],
        "system_instruction": {"parts": [{"text": system_prompt}]}
    }

    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={api_key}"
    headers = {"Content-Type": "application/json"}
    
    try:
        await context.bot.send_chat_action(chat_id=chat.id, action="typing")
        
        async with aiohttp.ClientSession() as session:
            async with session.post(url, headers=headers, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    if 'candidates' in data and data['candidates']:
                        full_response = data['candidates'][0]['content']['parts'][0]['text'].strip()
                        
                        # Send the reply
                        await update.message.reply_text(full_response, parse_mode="Markdown")
                        
                        # Save to dataset
                        save_group_ai_message(
                            group_id=chat.id, 
                            user_id=user.id, 
                            user_message=clean_msg, 
                            bot_response=full_response, 
                            context_type=context_type
                        )
    except Exception as e:
        logger.error(f"Error in group AI response: {e}")
