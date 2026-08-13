from database.models import update_personality

def save_personality_summary(user_id: int, summary: str):
    update_personality(user_id, summary)
