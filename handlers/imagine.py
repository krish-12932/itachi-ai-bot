import urllib.parse
from telegram import Update
from telegram.ext import ContextTypes
from database.models import get_user, update_user_coins

# Cost per image generation
IMAGINE_COST = 20

async def imagine_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Generates an image based on the prompt using pollinations.ai"""
    user_id = update.effective_user.id
    
    # Check if user provided a prompt
    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/imagine [your prompt]</code>\n\n"
            "Example: <code>/imagine Itachi Uchiha in cyberpunk city</code>\n\n"
            f"<i>Note: Each image generation costs {IMAGINE_COST} coins.</i>",
            parse_mode="HTML"
        )
        return

    prompt = " ".join(context.args)

    # Check user coins
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Please /start the bot first to register.")
        return

    unlimited = user.get("unlimited_chat", False)
    current_coins = user.get("coins", 0)

    if not unlimited and current_coins < IMAGINE_COST:
        await update.message.reply_text(
            f"❌ <b>Not enough coins!</b>\n\n"
            f"You need {IMAGINE_COST} coins to generate an image. You have {current_coins} coins.\n\n"
            "Use /daily to get free coins or /referral to invite friends!",
            parse_mode="HTML"
        )
        return

    # Deduct coins (if not unlimited)
    if not unlimited:
        update_user_coins(user_id, -IMAGINE_COST)
        new_balance = current_coins - IMAGINE_COST
    else:
        new_balance = "Unlimited"

    status_msg = await update.message.reply_text(
        "🎨 <b>Mangekyou Sharingan is visualizing your idea...</b>\n"
        "<i>Please wait a moment...</i>",
        parse_mode="HTML"
    )

    try:
        # Encode the prompt for the URL
        encoded_prompt = urllib.parse.quote(prompt)
        
        # Construct the Pollinations URL
        # Using model=flux and enhance=true for best quality as tested by user
        image_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?nologo=true&width=1024&height=1024&model=flux&enhance=true"
        
        caption = (
            f"✨ <b>Here is your creation!</b>\n\n"
            f"🗣️ <b>Prompt:</b> {prompt}\n"
            f"💰 <b>Coins Left:</b> {new_balance}"
        )

        # Send the photo directly via URL (Telegram will fetch it)
        await context.bot.send_photo(
            chat_id=user_id,
            photo=image_url,
            caption=caption,
            parse_mode="HTML"
        )
        
        # Delete the "Please wait" message
        await status_msg.delete()

    except Exception as e:
        # If generation fails, refund the coins
        if not unlimited:
            update_user_coins(user_id, IMAGINE_COST)
            
        await status_msg.edit_text(
            f"❌ <b>Failed to generate image.</b>\n"
            f"Error: {str(e)}\n\n"
            f"<i>Your {IMAGINE_COST} coins have been refunded.</i>",
            parse_mode="HTML"
        )
