import io
import aiohttp
import urllib.parse
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from database.models import get_user, update_user_coins

# Cost per image generation
IMAGINE_COST = 5

# Aspect ratio presets: label → (width, height, description)
ASPECT_RATIOS = {
    "1:1":   (1024, 1024, "Square"),
    "16:9":  (1280, 720,  "Landscape (YouTube/PC)"),
    "9:16":  (720, 1280,  "Portrait (Stories/Reels)"),
    "4:3":   (1024, 768,  "Classic"),
    "3:4":   (768, 1024,  "Portrait Classic"),
    "21:9":  (1344, 576,  "Cinematic Ultra-Wide"),
}

def get_ratio_keyboard(prompt_key: str) -> InlineKeyboardMarkup:
    """Build inline keyboard with aspect ratio options."""
    buttons = []
    row = []
    for i, (ratio, (w, h, desc)) in enumerate(ASPECT_RATIOS.items()):
        row.append(InlineKeyboardButton(
            f"{ratio} {desc}",
            callback_data=f"img_ratio|{ratio}|{prompt_key}"
        ))
        if len(row) == 2 or i == len(ASPECT_RATIOS) - 1:
            buttons.append(row)
            row = []
    buttons.append([InlineKeyboardButton("❌ Cancel", callback_data="img_cancel")])
    return InlineKeyboardMarkup(buttons)


async def _download_image(prompt: str, width: int, height: int) -> bytes | None:
    """Download image from pollinations.ai and return raw bytes."""
    encoded_prompt = urllib.parse.quote(prompt)
    seed = random.randint(1, 99999)
    
    urls = [
        f"https://image.pollinations.ai/prompt/{encoded_prompt}?nologo=true&width={width}&height={height}&model=flux&enhance=true&seed={seed}",
        f"https://image.pollinations.ai/prompt/{encoded_prompt}?nologo=true&width={width}&height={height}&model=turbo&seed={seed}",
        f"https://image.pollinations.ai/prompt/{encoded_prompt}?nologo=true&width={width}&height={height}",
    ]
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
    }
    timeout = aiohttp.ClientTimeout(total=60)

    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        for url in urls:
            try:
                async with session.get(url, allow_redirects=True) as resp:
                    if resp.status == 200:
                        content_type = resp.headers.get("Content-Type", "")
                        if "image" in content_type:
                            data = await resp.read()
                            if len(data) > 1000:
                                return data
            except Exception:
                continue
    return None


async def imagine_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 1: User types prompt (optionally ending with a number) → Bot shows aspect ratio buttons."""
    user_id = update.effective_user.id

    if not context.args:
        await update.message.reply_text(
            "⚠️ <b>Usage:</b> <code>/imagine [your prompt] [count]</code>\n\n"
            "Examples:\n"
            "• <code>/imagine Itachi Uchiha in cyberpunk city</code>\n"
            "• <code>/imagine dragon breathing fire 3</code> — generates 3 images\n\n"
            f"<i>Note: Each image costs {IMAGINE_COST} coins. Max 4 images per request.</i>",
            parse_mode="HTML"
        )
        return

    # Detect count from last argument (if it's a number 1-4)
    args = context.args
    count = 1
    if args[-1].isdigit():
        count = min(max(int(args[-1]), 1), 4)  # Clamp between 1 and 4
        args = args[:-1]  # Remove count from prompt

    if not args:
        await update.message.reply_text("⚠️ Please provide a prompt!")
        return

    prompt = " ".join(args)
    total_cost = IMAGINE_COST * count

    # Check user coins
    user = get_user(user_id)
    if not user:
        await update.message.reply_text("❌ Please /start the bot first to register.")
        return

    unlimited = user.get("unlimited_chat", False)
    current_coins = user.get("coins", 0)

    if not unlimited and current_coins < total_cost:
        await update.message.reply_text(
            f"❌ <b>Not enough coins!</b>\n\n"
            f"Generating <b>{count} image(s)</b> costs <b>{total_cost} coins</b>. You have {current_coins} coins.\n\n"
            "Use /daily to get free coins!",
            parse_mode="HTML"
        )
        return

    # Save prompt + count in bot_data
    prompt_key = str(user_id)
    context.bot_data[f"imagine_prompt_{prompt_key}"] = prompt
    context.bot_data[f"imagine_count_{prompt_key}"] = count

    count_label = f" × {count}" if count > 1 else ""
    await update.message.reply_text(
        f"🎨 <b>Prompt:</b> <i>{prompt}</i>\n"
        f"🖼️ <b>Images:</b> {count}{count_label}\n"
        f"💰 <b>Cost:</b> {total_cost} coins\n\n"
        "📐 <b>Choose Aspect Ratio:</b>",
        parse_mode="HTML",
        reply_markup=get_ratio_keyboard(prompt_key)
    )


async def imagine_ratio_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Step 2: User picks aspect ratio → Generate image(s)."""
    query = update.callback_query
    await query.answer()

    if query.data == "img_cancel":
        await query.edit_message_text("❌ Image generation cancelled.")
        return

    parts = query.data.split("|")
    if len(parts) != 3 or parts[0] != "img_ratio":
        return

    _, ratio, prompt_key = parts
    user_id = query.from_user.id

    if prompt_key != str(user_id):
        await query.answer("❌ This is not your request!", show_alert=True)
        return

    prompt = context.bot_data.get(f"imagine_prompt_{prompt_key}")
    count = context.bot_data.get(f"imagine_count_{prompt_key}", 1)
    if not prompt:
        await query.edit_message_text("❌ Session expired. Please use /imagine again.")
        return

    # Clean up stored data
    context.bot_data.pop(f"imagine_prompt_{prompt_key}", None)
    context.bot_data.pop(f"imagine_count_{prompt_key}", None)

    width, height, ratio_desc = ASPECT_RATIOS[ratio]
    total_cost = IMAGINE_COST * count

    # Check coins again
    user = get_user(user_id)
    unlimited = user.get("unlimited_chat", False)
    current_coins = user.get("coins", 0)

    if not unlimited and current_coins < total_cost:
        await query.edit_message_text(
            f"❌ <b>Not enough coins!</b> You need {total_cost} coins.",
            parse_mode="HTML"
        )
        return

    # Deduct coins
    if not unlimited:
        update_user_coins(user_id, -total_cost)
        new_balance = current_coins - total_cost
    else:
        new_balance = "Unlimited"

    plural = "images" if count > 1 else "image"
    await query.edit_message_text(
        f"🎨 <b>Generating {count} {plural}...</b>\n"
        f"📐 <b>Ratio:</b> {ratio} ({ratio_desc})\n"
        f"🗣️ <b>Prompt:</b> <i>{prompt}</i>\n\n"
        "<i>Please wait, this may take a moment...</i>",
        parse_mode="HTML"
    )

    try:
        # Download all images concurrently
        import asyncio
        tasks = [_download_image(prompt, width, height) for _ in range(count)]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        valid_images = [r for r in results if isinstance(r, bytes) and r]

        if not valid_images:
            raise Exception("No valid images received from any source.")

        # Refund for any failed images
        failed = count - len(valid_images)
        if failed > 0 and not unlimited:
            refund = IMAGINE_COST * failed
            update_user_coins(user_id, refund)
            new_balance += refund

        caption_base = (
            f"✨ <b>Your Creation{'s' if len(valid_images) > 1 else ''}!</b>\n\n"
            f"🗣️ <b>Prompt:</b> {prompt}\n"
            f"📐 <b>Ratio:</b> {ratio} ({ratio_desc}) — {width}×{height}px\n"
            f"💰 <b>Coins Left:</b> {new_balance}"
        )

        if len(valid_images) == 1:
            # Single image → send as photo with caption
            image_file = io.BytesIO(valid_images[0])
            image_file.name = "Itachi_AI_Generation.jpg"
            await context.bot.send_photo(
                chat_id=query.message.chat_id,
                photo=image_file,
                caption=caption_base,
                parse_mode="HTML"
            )
        else:
            # Multiple images → send as album
            from telegram import InputMediaPhoto
            media_group = []
            for i, img_bytes in enumerate(valid_images):
                img_file = io.BytesIO(img_bytes)
                img_file.name = f"Itachi_AI_{i+1}.jpg"
                cap = caption_base if i == 0 else None
                media_group.append(InputMediaPhoto(
                    media=img_file,
                    caption=cap,
                    parse_mode="HTML" if cap else None
                ))
            await context.bot.send_media_group(
                chat_id=query.message.chat_id,
                media=media_group
            )

        await query.message.delete()

    except Exception as e:
        if not unlimited:
            update_user_coins(user_id, total_cost)
        await query.edit_message_text(
            f"❌ <b>Failed to generate image.</b>\n"
            f"<i>Error: {str(e)[:100]}</i>\n\n"
            f"<i>Your {total_cost} coins have been refunded.</i>",
            parse_mode="HTML"
        )
