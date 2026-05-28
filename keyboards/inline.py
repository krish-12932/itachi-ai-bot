from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import FORCE_JOIN_CHANNELS

def get_join_keyboard():
    keyboard = []
    for channel in FORCE_JOIN_CHANNELS:
        keyboard.append([InlineKeyboardButton(f"Join Channel {channel['index']} 📢", url=channel['link'])])
        
    keyboard.append([InlineKeyboardButton("Joined ✅", callback_data="check_join")])
    return InlineKeyboardMarkup(keyboard)

def get_plan_keyboard(domain: str, coin_code: str, coin_20_code: str, unlimited_code: str):
    keyboard = [
        [InlineKeyboardButton("📺 Watch 1 Ad (10 Coins) - Fast", web_app=WebAppInfo(url=f"{domain}/?code={coin_code}&req=1"))],
        [InlineKeyboardButton("📺 Watch 2 Ads (20 Coins) - Bonus", web_app=WebAppInfo(url=f"{domain}/?code={coin_20_code}&req=2"))],
        [InlineKeyboardButton("📺 Watch 10 Ads (Unlimited)", web_app=WebAppInfo(url=f"{domain}/?code={unlimited_code}&req=10"))]
    ]
    return InlineKeyboardMarkup(keyboard)
