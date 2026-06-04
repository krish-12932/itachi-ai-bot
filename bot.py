import asyncio
import logging
from telegram.ext import ApplicationBuilder
from config import TELEGRAM_BOT_TOKEN

# Initialize Bot Application
application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).connect_timeout(60).read_timeout(60).write_timeout(60).pool_timeout(60).build()
bot = application.bot
