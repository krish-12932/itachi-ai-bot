itachi-telegram-bot/
├── main.py                 # Bot start + polling
├── config.py               # Token, Database URL, etc.
├── bot.py                  # Bot instance + dispatcher
├── handlers/               # Saare commands aur logic
│   ├── __init__.py
│   ├── start.py
│   ├── chat.py
│   ├── profile.py
│   ├── plan.py
│   ├── referral.py
│   └── admin.py            # (baad mein)
├── database/               # Database related
│   ├── __init__.py
│   ├── connection.py       # MongoDB / SQLite connection
│   └── models.py           # User schema / functions
├── utils/                  # Helper functions
│   ├── __init__.py
│   ├── coins.py            # chakra add/remove logic
│   ├── personality.py      # personality summary
│   └── messages.py         # All Itachi style messages
├── prompts/                # AI Prompts
│   ├── __init__.py
│   └── itachi_prompts.py
├── keyboards/              # Inline & Reply keyboards
│   ├── __init__.py
│   └── inline.py
├── requirements.txt
├── .env                    # Secret keys (TOKEN, MONGO_URL)
└── README.mds