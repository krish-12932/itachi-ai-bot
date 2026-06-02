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

async def send_daily_greeting(context: ContextTypes.DEFAULT_TYPE):
    """Sends personalized greetings to all users based on time of day."""
    job_data = context.job.data
    greeting_type = job_data.get("type")
    
    users = get_all_users()
    
    greetings = {
        "morning": "Ek nayi subah... haqeeqat ka samna karne ka waqt aa gaya hai. Shubh prabhat, {name}. 🌑🌅",
        "afternoon": "Sooraj ki garmi... shadows ko aur bhi gehra kar deti hai. {name}, apna rasta mat bhatakna. 👁️🗨️☀️",
        "evening": "Andhera gehra ho raha hai... {name}. Apni thakan ko qurbani mat banane dena. Shubh sandhya. 🌑🗡️"
    }
    
    text_template = greetings.get(greeting_type, "Namaste, {name}.")
    
    success = 0
    failed = 0
    
    for user in users:
        user_id = user["user_id"]
        name = user.get("first_name", "Shinobi")
        
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=text_template.format(name=name),
                parse_mode="HTML"
            )
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
