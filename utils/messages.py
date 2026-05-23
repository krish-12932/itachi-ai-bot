# Generic Neutral Messages

WELCOME_MSG = """
👋 Hello {name}, Welcome to your AI assistant!

I am Itachi Uchiha. You can chat with me, analyze images, and more.

💰 <b>Current Balance:</b> {coins} Coins
"""

FORCE_JOIN_MSG = """
🛑 <b>Access Denied!</b>

You must join our official channels to use this bot.
Please join all channels below and click <b>"Joined ✅"</b> to continue.
"""

CHAT_STARTED_MSG = """
✅ **Chat Mode ON**

I will now reply to your messages. 
(Deducts 1 coin per reply)

Type `/endchat` to stop.
"""

CHAT_ENDED_MSG = """
🛑 **Chat Mode OFF**

I will no longer reply to normal messages.
"""

INSUFFICIENT_COINS_MSG = """
⚠️ **Insufficient Coins!**

You don't have enough coins to chat. 
Watch an ad or refer friends to get more coins!
Check `/plan` for options.
"""

PROFILE_MSG = """
👤 <b>User Profile</b>

🆔 <b>ID:</b> {user_id}
💰 <b>Coins:</b> {coins}
🤖 <b>Unlimited Chat:</b> {unlimited}
🧠 <b>Personality Summary:</b>
{personality}
"""

PLAN_MSG = """
💎 **Earn Coins / Unlimited Chat**

Watch an ad to support us and earn rewards!

1. 📺 **Watch 1 Ad** → 10 Coins
2. 📺 **Watch 10 Ads** → Unlimited Chat

Click a button below to start:
"""

REFERRAL_MSG = """
🎁 <b>Referral System</b>

Share your link with friends. When they join, you get <b>30 Coins</b>!

Total referrals: {count}
"""
