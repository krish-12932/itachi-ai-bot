from database.models import update_user_coins

def add_chakra(user_id: int, amount: int):
    return update_user_coins(user_id, amount)

def remove_chakra(user_id: int, amount: int):
    return update_user_coins(user_id, -abs(amount))
