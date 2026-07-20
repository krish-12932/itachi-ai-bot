import logging
import asyncio
import aiohttp
import json
import random
from collections import deque
from telegram import Update
from telegram.ext import ContextTypes

from config import GOOGLE_API_KEYS, OPENROUTER_API_KEY
from prompts.itachi_prompts import ITACHI_PERSONA_PROMPT
from database.group_models import get_group_settings, save_group_ai_message

OPENROUTER_MODEL = "google/gemini-2.0-flash-lite-preview-02-05:free"

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────
# Group Chat History Buffer
# Stores last 15 messages per group for context
# Format: {chat_id: deque([(sender_name, text, is_bot), ...])}
# ─────────────────────────────────────────
GROUP_HISTORY: dict[int, deque] = {}
MAX_HISTORY = 15  # How many messages to remember per group

def _add_to_history(chat_id: int, sender_name: str, text: str, is_bot: bool = False):
    """Add a message to the group's chat history."""
    if chat_id not in GROUP_HISTORY:
        GROUP_HISTORY[chat_id] = deque(maxlen=MAX_HISTORY)
    GROUP_HISTORY[chat_id].append((sender_name, text, is_bot))

def _build_history_prompt(chat_id: int, current_msg: str) -> str:
    """
    Builds a single robust text prompt containing the chat history.
    This avoids Gemini's strict multi-turn role rules which cause 400 Bad Request errors.
    """
    history = list(GROUP_HISTORY.get(chat_id, []))
    
    if not history:
        return current_msg
        
    prompt_lines = ["--- RECENT CHAT HISTORY ---"]
    for sender_name, text, is_bot in history:
        prompt_lines.append(f"[{sender_name}]: {text}")
    
    prompt_lines.append("--- END HISTORY ---")
    prompt_lines.append(f"\n[CURRENT MESSAGE to reply to]: {current_msg}")
    
    return "\n".join(prompt_lines)


async def group_message_logger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Silently logs every group text message into the chat history buffer.
    This runs on ALL group messages (registered in main.py at group=-1).
    """
    if not update.message or not update.message.text or not update.effective_chat:
        return
    if update.effective_chat.type == "private":
        return
    
    chat = update.effective_chat
    user = update.effective_user
    
    if not user:
        return
    
    sender_name = user.first_name or user.username or "User"
    is_bot = user.is_bot
    
    _add_to_history(chat.id, sender_name, update.message.text, is_bot=is_bot)


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
    bot_name = context.bot.first_name or "Itachi"
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
        return  # No AI action needed

    # Clean the message text from tags
    clean_msg = msg_text.replace(f"@{bot_username}", "").strip()
    sender_name = user.first_name if user else "User"

    # Need at least one AI provider
    if not GOOGLE_API_KEYS and not OPENROUTER_API_KEY:
        return
    
    # Build system prompt
    system_prompt = ITACHI_PERSONA_PROMPT
    system_prompt += (
        "\n\n[GROUP CHAT CONTEXT]: You are in a group chat. "
        "The conversation history is provided with each message labeled [Name]: text. "
        "Use this context to give relevant, connected answers. "
        "Do NOT repeat usernames in your response. Just reply naturally."
    )
    
    # Add group topic as context if set
    group_topic = settings.get("group_topic")
    if group_topic:
        system_prompt += f"\n\n[GROUP TOPIC]: This group is about \"{group_topic}\". Keep responses relevant to this topic."
    
    if context_type == "smart_help":
        system_prompt += "\n\n[TASK]: Help the user who has a question or problem. Be helpful but maintain your persona."
    elif context_type == "proactive":
        system_prompt += "\n\n[TASK]: Make a brief, witty, or observational comment to keep the conversation going."

    # Build conversation history as a single robust prompt string
    history_prompt = _build_history_prompt(chat.id, clean_msg)
    full_response = ""
    thinking_msg = None
    
    try:
        # Send a "thinking" placeholder message
        thinking_msg = await update.message.reply_text("🤔 _Thinking..._", parse_mode="Markdown")
        
        # Keep sending typing action every 4 seconds while AI processes
        async def keep_typing():
            while True:
                try:
                    await context.bot.send_chat_action(chat_id=chat.id, action="typing")
                except Exception:
                    pass
                await asyncio.sleep(4)
        
        typing_task = asyncio.create_task(keep_typing())
        
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            
            # === PRIMARY: z.ai GLM-4.5 via OpenRouter (Free & Fast) ===
            if OPENROUTER_API_KEY:
                try:
                    or_url = "https://openrouter.ai/api/v1/chat/completions"
                    or_headers = {
                        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://itachi-bot.onrender.com",
                        "X-Title": "Itachi AI Bot"
                    }
                    or_messages = [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": history_prompt}
                    ]
                    or_payload = {
                        "model": OPENROUTER_MODEL,
                        "messages": or_messages,
                        "max_tokens": 600
                    }
                    async with session.post(or_url, headers=or_headers, json=or_payload) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text = data["choices"][0]["message"]["content"].strip()
                            if text:
                                full_response = text
                                logger.info("OpenRouter GLM-4.5 replied successfully!")
                        else:
                            err = await resp.text()
                            logger.error(f"OpenRouter error ({resp.status}): {err}")
                except Exception as e:
                    logger.error(f"OpenRouter exception: {e}")
            
            # === FALLBACK: Gemini Models ===
            if not full_response and GOOGLE_API_KEYS:
                gemini_models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-flash-8b"]
                for api_key in GOOGLE_API_KEYS:
                    if full_response: break
                    for model_name in gemini_models:
                        gemini_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
                        gemini_payload = {
                            "contents": [{"role": "user", "parts": [{"text": history_prompt}]}],
                            "system_instruction": {"parts": [{"text": system_prompt}]}
                        }
                        try:
                            async with session.post(gemini_url, headers={"Content-Type": "application/json"}, json=gemini_payload) as resp:
                                if resp.status == 200:
                                    data = await resp.json()
                                    if 'candidates' in data and data['candidates']:
                                        full_response = data['candidates'][0]['content']['parts'][0]['text'].strip()
                                        if full_response: break
                                elif resp.status == 429:
                                    logger.warning(f"Gemini {model_name} rate limited, trying next...")
                                    continue
                                else:
                                    err_text = await resp.text()
                                    logger.error(f"Gemini API Error {resp.status}: {err_text}")
                        except Exception as e:
                            logger.error(f"Group AI error {model_name}: {e}")
                            continue
        
        # Stop the typing loop
        typing_task.cancel()
        
    except Exception as e:
        logger.error(f"Error in group AI session: {e}")
        if thinking_msg:
            try:
                await thinking_msg.delete()
            except Exception:
                pass
        return

    if full_response:
        try:
            # Add bot's own response to history too
            _add_to_history(chat.id, bot_name, full_response, is_bot=True)
            
            # Edit the placeholder with the real response
            try:
                await thinking_msg.edit_text(full_response, parse_mode="Markdown")
            except Exception:
                try:
                    await thinking_msg.edit_text(full_response)
                except Exception:
                    await update.message.reply_text(full_response)
            
            # Save to dataset
            save_group_ai_message(
                group_id=chat.id, 
                user_id=user.id if user else 0, 
                user_message=clean_msg, 
                bot_response=full_response, 
                context_type=context_type
            )
        except Exception as e:
            logger.error(f"Error sending group AI response: {e}")
    else:
        # If AI failed, delete the thinking message silently
        try:
            await thinking_msg.delete()
        except Exception:
            pass
