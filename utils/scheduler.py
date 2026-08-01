import asyncio
import logging
from datetime import time
import pytz
from telegram.ext import ContextTypes
from database.models import get_all_users
from config import ADMIN_IDS

logger = logging.getLogger(__name__)

# IST Timezone
IST = pytz.timezone('Asia/Kolkata')

# Tracks the last greeting message sent to each user: {user_id: message_id}
LAST_GREETING_MSGS = {}

async def send_daily_greeting(context: ContextTypes.DEFAULT_TYPE):
    """Sends personalized greetings to all users based on time of day."""
    job_data = context.job.data
    greeting_type = job_data.get("type")
    
    users = get_all_users()
    
    greetings = {
        "morning": "Good Morning {name} 🌑🌅",
        "afternoon": "Good Afternoon {name} 👁️🗨️☀️",
        "evening": "Good Evening {name}. 🌑🗡️"
    }
    
    text_template = greetings.get(greeting_type, "Namaste, {name}.")
    
    success = 0
    failed = 0
    
    for user in users:
        user_id = user["user_id"]
        name = user.get("first_name", "Shinobi")
        
        try:
            # Delete the previous greeting message (Good Morning deleted when Good Afternoon arrives, etc.)
            prev_msg_id = LAST_GREETING_MSGS.get(user_id)
            if prev_msg_id:
                try:
                    await context.bot.delete_message(chat_id=user_id, message_id=prev_msg_id)
                except Exception:
                    pass  # Ignore if already deleted or message not found
            
            # Send the new greeting
            msg = await context.bot.send_message(
                chat_id=user_id,
                text=text_template.format(name=name),
                parse_mode="HTML"
            )
            # Store message id so the NEXT greeting can delete it
            LAST_GREETING_MSGS[user_id] = msg.message_id
            success += 1
            # Avoid hitting Telegram limits
            await asyncio.sleep(0.05)
        except Exception:
            failed += 1
            
    logger.info(f"Daily {greeting_type} greeting sent. Success: {success}, Failed: {failed}")

def setup_scheduler(application):
    """Initializes the scheduled jobs."""
    job_queue = application.job_queue
    
    # Morning Greeting - 08:30 AM IST
    job_queue.run_daily(
        send_daily_greeting,
        time=time(8, 30, tzinfo=IST),
        data={"type": "morning"}
    )
    
    # Afternoon Greeting - 01:30 PM IST
    job_queue.run_daily(
        send_daily_greeting,
        time=time(13, 30, tzinfo=IST),
        data={"type": "afternoon"}
    )
    
    # Evening Greeting - 07:30 PM IST
    job_queue.run_daily(
        send_daily_greeting,
        time=time(19, 30, tzinfo=IST),
        data={"type": "evening"}
    )
    
    logger.info("📅 Scheduler setup completed for Morning, Afternoon, and Evening.")
