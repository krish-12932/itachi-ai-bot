import os
import asyncio
import logging
import shortuuid
from aiohttp import web
from telegram import Update, BotCommand, BotCommandScopeChat
from telegram.ext import CommandHandler, MessageHandler, CallbackQueryHandler, ChatMemberHandler, TypeHandler, filters

from config import PORT, TELEGRAM_BOT_TOKEN, ADMIN_IDS, WEB_DOMAIN
from bot import application, bot
from database.models import get_ad_session, delete_ad_session, update_user_coins, set_unlimited_chat

# Import handlers (to be created)
from handlers.start import start_handler, check_join_callback, chat_member_updated
from handlers.chat import chat_handler, endchat_handler, message_handler, photo_handler
from handlers.profile import profile_handler
from handlers.plan import plan_handler
from handlers.referral import referral_handler
from handlers.support import support_handler
from handlers.admin import broadcast_handler, reply_handler, ban_command_handler, unban_command_handler, give_coins_handler, stats_handler
from utils.scheduler import setup_scheduler
from handlers.rewards import daily_handler, leaderboard_handler
from handlers.game import game_handler
from handlers.imagine import imagine_handler

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
logger = logging.getLogger(__name__)

# ==========================================
# WEB SERVER LOGIC
# ==========================================

async def handle_index(request):
    """Serves the frontend web application (index.html)"""
    return web.FileResponse('index.html')

async def handle_ad_completed(request):
    """API endpoint called by the web app when an ad finishes."""
    try:
        data = await request.json()
        code = data.get("code")

        if not code:
            return web.json_response({"status": "error", "message": "Missing code"}, status=400)

        session = get_ad_session(code)
        if not session:
            return web.json_response({"status": "error", "message": "Invalid or expired code"}, status=400)

        user_id = session["user_id"]
        message_id = session["message_id"]
        session_type = session["type"]

        # Reward the user
        if session_type == "10_coins":
            new_coins = update_user_coins(user_id, 10)
            reward_text = f"🎉 *Reward Unlocked!*\n\n✅ 10 Coins have been added to your balance.\n💰 **New Balance:** {new_coins}"
        elif session_type == "20_coins":
            new_coins = update_user_coins(user_id, 20)
            reward_text = f"🎉 *Double Reward Unlocked!*\n\n✅ 20 Coins have been added to your balance.\n💰 **New Balance:** {new_coins}"
        elif session_type == "unlimited":
            # For now, let's say 1 ad gives unlimited chat (as per user's 10 ads watch, we can track progress)
            # Simplification: If they watch the 'unlimited' ad type, they get it.
            # Realistically, you might want to track ad count.
            set_unlimited_chat(user_id, True)
            reward_text = "🎉 *Reward Unlocked!*\n\n✅ You now have **Unlimited Chat** mode!"
        
        # Delete session
        delete_ad_session(code)

        # Notify user on Telegram
        try:
            await bot.edit_message_text(
                chat_id=user_id,
                message_id=message_id,
                text=reward_text,
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Error editing message: {e}")
            await bot.send_message(chat_id=user_id, text=reward_text, parse_mode="Markdown")

        return web.json_response({"status": "success", "message": "Reward Sent!"})

    except Exception as e:
        logger.error(f"API Error: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)

async def handle_telegram_webhook(request):
    """Processes incoming Telegram updates via webhook."""
    try:
        data = await request.json()
        update = Update.de_json(data, application.bot)
        await application.update_queue.put(update)
        return web.Response(text="OK")
    except Exception as e:
        logger.error(f"Error handling Telegram webhook: {e}")
        return web.Response(status=500, text="Internal Error")

async def keep_alive_ping():
    """Background task to ping the bot's own web server every 10 minutes to keep it awake on Render."""
    import aiohttp
    
    # Wait 30 seconds initially for the server to boot up
    await asyncio.sleep(30)
    
    logger.info(f"🔄 Keep-alive pinging task started. Target: {WEB_DOMAIN}")
    
    while True:
        try:
            if "localhost" not in WEB_DOMAIN and "127.0.0.1" not in WEB_DOMAIN:
                async with aiohttp.ClientSession() as session:
                    async with session.get(WEB_DOMAIN) as resp:
                        logger.info(f"💓 Keep-alive ping sent to {WEB_DOMAIN}. Status: {resp.status}")
            else:
                logger.info(f"💓 Skipping keep-alive ping for local domain: {WEB_DOMAIN}")
        except Exception as e:
            logger.error(f"⚠️ Keep-alive ping failed: {e}")
        
        # Ping every 10 minutes (600 seconds)
        await asyncio.sleep(600)

async def start_web_server():
    app = web.Application()
    app.add_routes([
        web.get('/', handle_index),
        web.post('/ad-completed', handle_ad_completed),
        web.post(f'/{TELEGRAM_BOT_TOKEN}', handle_telegram_webhook),
    ])
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', PORT)
    await site.start()
    logger.info(f"🚀 Combined Web server + Webhook started on port {PORT}")

# ==========================================
# MAIN ENTRY POINT
# ==========================================

async def raw_update_logger(update: Update, context):
    logger.info(f"⚡ RAW UPDATE: {update}")
    api_kwargs = getattr(update, "api_kwargs", {}) or {}
    guest_msg = api_kwargs.get("guest_message")
    if guest_msg:
        logger.info("⚡ Intercepted Guest Message! Dispatching to handler...")
        from handlers.chat import handle_guest_message
        asyncio.create_task(handle_guest_message(guest_msg, context))

async def main():
    # Register raw update logger
    application.add_handler(TypeHandler(Update, raw_update_logger), group=-1)
    
    # Register handlers
    application.add_handler(CommandHandler("start", start_handler))
    application.add_handler(CommandHandler("chat", chat_handler))
    application.add_handler(CommandHandler("endchat", endchat_handler))
    application.add_handler(CommandHandler("profile", profile_handler))
    application.add_handler(CommandHandler("plan", plan_handler))
    application.add_handler(CommandHandler("referral", referral_handler))
    application.add_handler(CommandHandler("support", support_handler))
    application.add_handler(CommandHandler("broadcast", broadcast_handler))
    application.add_handler(CommandHandler("reply", reply_handler))
    application.add_handler(CommandHandler("ban", ban_command_handler))
    application.add_handler(CommandHandler("unban", unban_command_handler))
    application.add_handler(CommandHandler("givecoins", give_coins_handler))
    application.add_handler(CommandHandler("stats", stats_handler))
    application.add_handler(CommandHandler("daily", daily_handler))
    application.add_handler(CommandHandler("top", leaderboard_handler))
    application.add_handler(CommandHandler("game", game_handler))
    application.add_handler(CommandHandler("imagine", imagine_handler))
    
    # Callback query handler for Join Check
    application.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
    
    # Chat member handler to detect join/leave
    application.add_handler(ChatMemberHandler(chat_member_updated, ChatMemberHandler.CHAT_MEMBER))
    
    # Generic text handler for chat
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    # Photo handler for image analysis
    application.add_handler(MessageHandler(filters.PHOTO, photo_handler))
    
    # Business Message handler (Personal Assistant Mode)
    from handlers.chat import business_message_handler
    application.add_handler(MessageHandler(filters.UpdateType.BUSINESS_MESSAGE, business_message_handler))

    # Start bot
    async with application:
        await application.start()
        
        # Set menu commands
        commands = [
            BotCommand("start", "🚀 Start the bot"),
            BotCommand("chat", "🌑 Start Chatting"),
            BotCommand("endchat", "🛑 Stop Chatting"),
            BotCommand("profile", "👤 View Profile"),
            BotCommand("referral", "🎁 Earn Coins"),
            BotCommand("daily", "🎁 Claim Daily Coins"),
            BotCommand("top", "🏆 View Leaderboard"),
            BotCommand("game", "🎮 Play ninja games"),
            BotCommand("imagine", "🎨 Generate AI Images"),
            BotCommand("plan", "💎 Get Unlimited Chat"),
            BotCommand("support", "📩 Contact Admin"),
        ]
        await application.bot.set_my_commands(commands)
        
        # Admin commands (For all admins in ADMIN_IDS)
        if ADMIN_IDS:
            admin_commands = commands + [
                BotCommand("broadcast", "📢 Broadcast message to all users"),
                BotCommand("reply", "📩 Reply to a support ticket"),
                BotCommand("ban", "🚫 Ban a user"),
                BotCommand("unban", "✅ Unban a user"),
                BotCommand("givecoins", "🪙 Give/remove coins from a user"),
                BotCommand("stats", "📊 View bot statistics")
            ]
            for admin_id in ADMIN_IDS:
                try:
                    await application.bot.set_my_commands(
                        admin_commands, 
                        scope=BotCommandScopeChat(chat_id=int(admin_id))
                    )
                except Exception as e:
                    logger.error(f"Error setting commands for admin {admin_id}: {e}")
        
        # Setup Daily Greetings Scheduler
        setup_scheduler(application)
        
        # Start keep-alive ping task
        asyncio.create_task(keep_alive_ping())
        
        # Webhook vs Polling logic
        RENDER_EXTERNAL_URL = os.environ.get("RENDER_EXTERNAL_URL")
        
        if RENDER_EXTERNAL_URL:
            # Render Webhook Mode
            logger.info(f"🌐 Cloud environment detected! Starting Webhook at {RENDER_EXTERNAL_URL}")
            await start_web_server()
            webhook_url = f"{RENDER_EXTERNAL_URL}/{TELEGRAM_BOT_TOKEN}"
            await application.bot.set_webhook(url=webhook_url)
            logger.info(f"✅ Telegram Webhook set to {webhook_url}")
        else:
            # Local Polling Mode
            logger.info("🤖 Local environment detected! Starting Polling...")
            await start_web_server() # Start dummy server for local testing if needed
            await application.updater.start_polling(drop_pending_updates=True)
            
        # Keep running
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot stopped by user.")
