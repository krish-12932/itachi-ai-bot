Create a new folder 'group' with these files:
group/__init__.py
group/moderation.py
group/welcome.py
group/settings.py

Features to add:

MODERATION:
- Auto delete spam/links/promotions
- Auto delete photos/videos/documents
- Rate limiting (max 5 msgs/10 seconds)
- Auto warn user (3 warnings = ban)
- Warning message show karo user ko

WARNING SYSTEM:
- Warning 1 = "⚠️ First warning!"
- Warning 2 = "⚠️ Second warning! One more = Ban"
- Warning 3 = Auto ban from group
- Ban message = 
  "🛑 You are banned! 
   Go to @Itachi_Gpt_bot 
   Watch ads to get unbanned!"

UNBAN SYSTEM:
- User bot mein jaye
- /unban command likhe
- Bot bole "Watch X ads to unban"
- User ads dekhe
- Automatically group mein unban ho jaye!

PROMOTION DETECTION:
- Agar message mein promotion detected ho
- Direct permanent ban (no warnings!)
- Ban message =
  "🚫 Promotion detected = Direct Ban!
   Go to @Itachi_Gpt_bot
   Watch ads to unban yourself!"

ADS UNBAN FLOW:
- 3 warnings ban = Watch 2 ads = Unban
- Promotion ban = Watch 5 ads = Unban
- Permanent ban (admin) = No unban option

WELCOME:
- Welcome new members
- Show group rules on join
- Owner can set custom welcome message

OWNER CONTROLS:
- /groupsetup command for owner
- Set group purpose/rules/welcome msg
- Enable/disable specific features

All features should work per group 
using group_id from database.
Existing code should NOT be modified.
Only add new imports in main.py.
Store warnings and ban data in Supabase.