"""
Nail Telegram Bot
- Menu + 5 bước chọn option với nút Back đầy đủ
- Gen ảnh miễn phí qua Hugging Face (Stable Diffusion XL)
- Phân tích ảnh qua Hugging Face Vision (miễn phí)
"""

import os, logging, asyncio, base64, httpx, io
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
HF_TOKEN = os.environ.get("HF_TOKEN", "")

HF_HEADERS = {"Authorization": f"Bearer {HF_TOKEN}"}

# model gen ảnh — SDXL miễn phí
HF_IMAGE_URL   = "https://api-inference.huggingface.coHF_IMAGE_URL   = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-dev"
models/stabilityai/stable-diffusion-2-1"
# model phân tích ảnh — BLIP miễn phí
HF_VISION_URL  = "https://api-inference.huggingface.co/models/Salesforce/blip-image-captioning-base"

# ── session ───────────────────────────────────────────────────────────────────
SESSIONS: dict[int, dict] = {}

def sess(uid: int) -> dict:
    if uid not in SESSIONS:
        SESSIONS[uid] = {"step": 0, "theme": None, "shape": None, "style": None, "last_prompt": None}
    return SESSIONS[uid]

def reset(uid: int):
    SESSIONS[uid] = {"step": 0, "theme": None, "shape": None, "style": None, "last_prompt": None}

# ── progress bar ──────────────────────────────────────────────────────────────
def progress(step: int) -> str:
    return "".join(["▓" if i < step else "░" for i in range(5)]) + f" Bước {step}/5\n\n"

# ── keyboards ─────────────────────────────────────────────────────────────────
START_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("📸 Gửi ảnh nail mẫu",     callback_data="flow_photo")],
    [InlineKeyboardButton("✍️ Tạo từ lựa chọn",      callback_data="flow_text")],
])

STEP1_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎨 Chọn tông màu",          callback_data="tab_color")],
    [InlineKeyboardButton("🎉 Chọn theo ngày lễ Mỹ",   callback_data="tab_holiday")],
    [InlineKeyboardButton("🏠 Menu chính",              callback_data="menu_main")],
])

COLOR_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🌸 Pastel",   callback_data="theme_Pastel nhẹ nhàng"),
     InlineKeyboardButton("🤍 Nude",     callback_data="theme_Nude tự nhiên"),
     InlineKeyboardButton("💅 Đậm",      callback_data="theme_Màu đậm bold")],
    [InlineKeyboardButton("✨ Glitter",  callback_data="theme_Glitter lấp lánh"),
     InlineKeyboardButton("🎨 Ombre",    callback_data="theme_Ombre gradient"),
     InlineKeyboardButton("❤️ Đỏ rượu", callback_data="theme_Đỏ rượu burgundy")],
    [InlineKeyboardButton("⬛ Đen",      callback_data="theme_Đen tuyền"),
     InlineKeyboardButton("🌈 Mix màu",  callback_data="theme_Nhiều màu rực rỡ")],
    [InlineKeyboardButton("↩️ Quay lại", callback_data="back_step1")],
])

HOLIDAY_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("❄️ New Year's Day",    callback_data="theme_New Year's Day - silver glitter, countdown, midnight sparkle"),
     InlineKeyboardButton("💝 Valentine's Day",   callback_data="theme_Valentine's Day - red pink hearts, roses, romantic love")],
    [InlineKeyboardButton("🐣 Easter",            callback_data="theme_Easter - pastel egg colors, bunny, spring flowers"),
     InlineKeyboardButton("🌸 St. Patrick's Day", callback_data="theme_St. Patrick's Day - lucky clover, shamrock green, gold")],
    [InlineKeyboardButton("💐 Mother's Day",      callback_data="theme_Mother's Day - soft floral bouquet, pink white, elegant"),
     InlineKeyboardButton("🎖️ Memorial Day",      callback_data="theme_Memorial Day - patriotic red white blue, stars stripes")],
    [InlineKeyboardButton("🎓 Graduation",        callback_data="theme_Graduation - gold cap diploma, black gold, achievement"),
     InlineKeyboardButton("🏳️‍🌈 Pride Month",      callback_data="theme_Pride Month - rainbow gradient, colorful bold, celebration")],
    [InlineKeyboardButton("🎆 4th of July",       callback_data="theme_4th of July - red white blue fireworks, patriotic sparkle"),
     InlineKeyboardButton("🎒 Back to School",    callback_data="theme_Back to School - apple pencil books, plaid, fresh start")],
    [InlineKeyboardButton("🎃 Halloween",         callback_data="theme_Halloween - pumpkin ghost spider web, black orange purple"),
     InlineKeyboardButton("🦃 Thanksgiving",      callback_data="theme_Thanksgiving - harvest gold brown, fall foliage, warm tones")],
    [InlineKeyboardButton("🛍️ Black Friday",      callback_data="theme_Black Friday - bold black gold accent, glamorous dark luxe"),
     InlineKeyboardButton("🎄 Christmas",         callback_data="theme_Christmas - red green festive, snowflake, candy cane, sparkle")],
    [InlineKeyboardButton("🥂 New Year's Eve",    callback_data="theme_New Year's Eve - champagne gold silver glitter, glam party")],
    [InlineKeyboardButton("↩️ Quay lại",          callback_data="back_step1")],
])

def shape_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌙 Almond",   callback_data="shape_almond"),
         InlineKeyboardButton("⬛ Square",   callback_data="shape_square"),
         InlineKeyboardButton("💎 Coffin",   callback_data="shape_coffin")],
        [InlineKeyboardButton("🥚 Oval",     callback_data="shape_oval"),
         InlineKeyboardButton("📌 Stiletto", callback_data="shape_stiletto"),
         InlineKeyboardButton("◻️ Round",    callback_data="shape_round")],
        [InlineKeyboardButton("↩️ Quay lại", callback_data="back_step1")],
    ])

def style_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕊 Minimalist",  callback_data="style_minimalist elegant"),
         InlineKeyboardButton("🌸 Floral",      callback_data="style_floral botanical"),
         InlineKeyboardButton("💠 Abstract",    callback_data="style_abstract modern art")],
        [InlineKeyboardButton("🌟 3D Đắp nổi", callback_data="style_3D sculpted embossed"),
         InlineKeyboardButton("🤍 French",      callback_data="style_French manicure classic"),
         InlineKeyboardButton("🌀 Marble",      callback_data="style_marble stone swirl")],
        [InlineKeyboardButton("🧸 Kawaii",      callback_data="style_kawaii cute pastel"),
         InlineKeyboardButton("🖤 Dark/Gothic", callback_data="style_dark gothic edgy")],
        [InlineKeyboardButton("↩️ Quay lại",    callback_data="back_step2")],
    ])

def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tạo ảnh ngay!", callback_data="confirm_gen")],
        [InlineKeyboardButton("↩️ Quay lại",      callback_data="back_step3")],
        [InlineKeyboardButton("🔁 Chọn lại từ đầu", callback_data="new")],
    ])

RESULT_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔄 Biến tấu khác",       callback_data="remix")],
    [InlineKeyboardButton("🎨 Đổi màu / hình móng", callback_data="tweak")],
    [InlineKeyboardButton("🏠 Tạo mẫu mới",         callback_data="new")],
])

TWEAK_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🌸 Pastel",   callback_data="tw_Pastel nhẹ nhàng"),
     InlineKeyboardButton("🤍 Nude",     callback_data="tw_Nude tự nhiên"),
     InlineKeyboardButton("💅 Đậm",      callback_data="tw_Màu đậm bold")],
    [InlineKeyboardButton("✨ Glitter",  callback_data="tw_Glitter lấp lánh"),
     InlineKeyboardButton("🎨 Ombre",    callback_data="tw_Ombre gradient"),
     InlineKeyboardButton("❤️ Đỏ rượu", callback_data="tw_Đỏ rượu burgundy")],
    [InlineKeyboardButton("🌙 Almond",   callback_data="tw_almond shape"),
     InlineKeyboardButton("⬛ Square",   callback_data="tw_square shape"),
     InlineKeyboardButton("💎 Coffin",   callback_data="tw_coffin shape")],
    [InlineKeyboardButton("↩️ Quay lại", callback_data="back_result")],
])

# ── HuggingFace helpers ───────────────────────────────────────────────────────
def build_prompt(theme: str, shape: str, style: str) -> str:
    return (
        f"professional nail art photo, macro close-up, "
        f"{theme}, {shape} nail shape, {style} nail design, "
        f"gel nails, studio lighting, white background, "
        f"high quality, 4k, sharp focus, elegant"
    )

NEG_PROMPT = "blurry, low quality, ugly, deformed, hands, fingers visible, watermark, text"

def gen_image_hf(prompt: str) -> bytes:
    from huggingface_hub import InferenceClient
    client = InferenceClient(provider="hf-inference", api_key=HF_TOKEN)
    image = client.text_to_image(prompt, model="black-forest-labs/FLUX.1-dev")
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
        }
    }
    # retry tối đa 3 lần (model có thể đang load)
    for attempt in range(3):
        resp = httpx.post(HF_IMAGE_URL, headers=HF_HEADERS, json=payload, timeout=60)
        if resp.status_code == 200:
            return resp.content
        elif resp.status_code == 503:
            log.info(f"Model loading, retry {attempt+1}/3...")
            time.sleep(20)
        else:
            raise Exception(f"HF API error {resp.status_code}: {resp.text[:200]}")
    raise Exception("Model vẫn đang load, thử lại sau nhé!")

def analyze_image_hf(image_bytes: bytes) -> str:
    """Dùng BLIP để caption ảnh nail"""
    resp = httpx.post(
        HF_VISION_URL,
        headers=HF_HEADERS,
        content=image_bytes,
        timeout=30,
    )
    if resp.status_code == 200:
        result = resp.json()
        if isinstance(result, list) and result:
            return result[0].get("generated_text", "nail art")
    return "nail art"

async def get_photo_bytes(photo, ctx) -> bytes:
    file = await ctx.bot.get_file(photo[-1].file_id)
    async with httpx.AsyncClient() as c:
        r = await c.get(file.file_path)
    return r.content

# ── show steps ────────────────────────────────────────────────────────────────
async def show_menu(q):
    await q.edit_message_text(
        "💅 Bạn muốn tạo mẫu nail theo cách nào?",
        reply_markup=START_KB,
    )

async def show_step1(q):
    await q.edit_message_text(
        progress(1) + "Bạn muốn chọn theo:",
        reply_markup=STEP1_KB,
    )

async def show_step2(q, s):
    theme_short = s["theme"].split(" -")[0] if s["theme"] else ""
    await q.edit_message_text(
        progress(2) + f"Đã chọn: *{theme_short}* ✅\n\nHình dạng móng?",
        parse_mode="Markdown",
        reply_markup=shape_kb(),
    )

async def show_step3(q, s):
    await q.edit_message_text(
        progress(3) + f"Hình: *{s['shape']}* ✅\n\nPhong cách nail?",
        parse_mode="Markdown",
        reply_markup=style_kb(),
    )

async def show_step4(q, s):
    theme_short = s["theme"].split(" -")[0] if s["theme"] else ""
    await q.edit_message_text(
        progress(5) +
        f"📋 *Tóm tắt lựa chọn:*\n\n"
        f"🎨 Chủ đề: *{theme_short}*\n"
        f"💅 Hình móng: *{s['shape']}*\n"
        f"✨ Phong cách: *{s['style']}*\n\n"
        "Tạo ảnh nail ngay không?",
        parse_mode="Markdown",
        reply_markup=confirm_kb(),
    )

# ── handlers ──────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    name = update.effective_user.first_name or "bạn"
    reset(update.effective_user.id)
    await update.message.reply_text(
        f"Xin chào *{name}*! 💅\n\n"
        "Chào mừng bạn đến với *Nail Bot*!\n"
        "Bạn muốn tạo mẫu nail theo cách nào?",
        parse_mode="Markdown",
        reply_markup=START_KB,
    )

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    msg = await update.message.reply_text("🔍 Đang phân tích ảnh...")
    try:
        img_bytes = await get_photo_bytes(update.message.photo, ctx)
        # phân tích ảnh bằng BLIP
        caption   = await asyncio.to_thread(analyze_image_hf, img_bytes)
        prompt    = (
            f"professional nail art photo, macro close-up, {caption}, "
            f"gel nails, studio lighting, white background, high quality, 4k, sharp focus"
        )
        await msg.edit_text("🎨 Đang tạo ảnh nail tương tự, chờ ~30 giây nhé...")
        img_out   = await asyncio.to_thread(gen_image_hf, prompt)
        sess(update.effective_user.id)["last_prompt"] = prompt
        await ctx.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=io.BytesIO(img_out),
            caption="✨ Đây là mẫu nail tương tự ảnh bạn gửi!",
            reply_markup=RESULT_KB,
        )
        await msg.delete()
    except Exception as e:
        log.exception(e)
        await msg.edit_text(f"❌ Lỗi: {str(e)[:100]}\n\nThử lại nhé!")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    if sess(uid)["step"] > 0:
        await update.message.reply_text("Bạn hãy chọn một trong các nút bên trên nhé 👆")
        return
    msg = await update.message.reply_text("✨ Đang tạo ảnh nail, chờ ~30 giây nhé...")
    try:
        prompt = build_prompt(text, "almond", "elegant")
        img    = await asyncio.to_thread(gen_image_hf, prompt)
        sess(uid)["last_prompt"] = prompt
        await ctx.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=io.BytesIO(img),
            caption=f"✨ Nail theo yêu cầu: _{text}_",
            parse_mode="Markdown",
            reply_markup=RESULT_KB,
        )
        await msg.delete()
    except Exception as e:
        log.exception(e)
        await msg.edit_text(f"❌ Lỗi: {str(e)[:100]}\n\nThử lại nhé!")

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    d   = q.data
    await q.answer()
    s   = sess(uid)

    # ── menu ──────────────────────────────────────────────────────────────────
    if d in ("menu_main", "new"):
        reset(uid)
        await show_menu(q)

    elif d == "flow_photo":
        await q.edit_message_text(
            "📸 Gửi ảnh nail bạn thích vào đây!\n"
            "_Bot sẽ phân tích và tạo mẫu tương tự_ 🎨",
            parse_mode="Markdown",
        )

    elif d == "flow_text":
        s["step"] = 1
        await show_step1(q)

    # ── bước 1 ────────────────────────────────────────────────────────────────
    elif d == "tab_color":
        await q.edit_message_text(
            progress(1) + "Chọn tông màu bạn thích 🎨",
            reply_markup=COLOR_KB,
        )

    elif d == "tab_holiday":
        await q.edit_message_text(
            progress(1) + "Chọn ngày lễ Mỹ 🎉",
            reply_markup=HOLIDAY_KB,
        )

    elif d == "back_step1":
        s["theme"] = None
        s["step"]  = 1
        await show_step1(q)

    elif d.startswith("theme_"):
        s["theme"] = d[6:]
        s["step"]  = 2
        await show_step2(q, s)

    # ── bước 2 ────────────────────────────────────────────────────────────────
    elif d == "back_step2":
        s["shape"] = None
        s["step"]  = 1
        await show_step1(q)

    elif d.startswith("shape_"):
        s["shape"] = d[6:]
        s["step"]  = 3
        await show_step3(q, s)

    # ── bước 3 ────────────────────────────────────────────────────────────────
    elif d == "back_step3":
        s["style"] = None
        s["step"]  = 2
        await show_step2(q, s)

    elif d.startswith("style_"):
        s["style"] = d[6:]
        s["step"]  = 4
        await show_step4(q, s)

    # ── bước 4 — xác nhận ────────────────────────────────────────────────────
    elif d == "confirm_gen":
        await q.edit_message_text("⏳ Đang tạo ảnh nail, chờ ~30 giây nhé...")
        try:
            prompt = build_prompt(
                s.get("theme", "elegant nail art"),
                s.get("shape", "almond"),
                s.get("style", "minimalist"),
            )
            img = await asyncio.to_thread(gen_image_hf, prompt)
            s["last_prompt"] = prompt
            s["step"]        = 0
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=io.BytesIO(img),
                caption="✨ Đây là ảnh nail của bạn!",
                reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:100]}\n\nThử lại nhé!")

    # ── remix ─────────────────────────────────────────────────────────────────
    elif d == "remix":
        last = s.get("last_prompt")
        if not last:
            await show_menu(q)
            return
        await q.edit_message_text("🔄 Đang tạo biến tấu mới, chờ ~30 giây...")
        try:
            new_prompt = last + ", creative variation, different composition"
            img = await asyncio.to_thread(gen_image_hf, new_prompt)
            s["last_prompt"] = new_prompt
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=io.BytesIO(img),
                caption="🔄 Biến tấu mới đây!",
                reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:100]}\n\nThử lại nhé!")

    # ── tweak ─────────────────────────────────────────────────────────────────
    elif d == "tweak":
        await q.edit_message_text(
            "🎨 Chọn màu hoặc hình dạng móng muốn thay:",
            reply_markup=TWEAK_KB,
        )

    elif d.startswith("tw_"):
        tweak_val = d[3:]
        await q.edit_message_text(f"🎨 Đang tạo với *{tweak_val}*, chờ ~30 giây...", parse_mode="Markdown")
        try:
            new_prompt = (
                f"professional nail art photo, macro close-up, {tweak_val}, "
                f"gel nails, studio lighting, white background, high quality, 4k, sharp focus"
            )
            img = await asyncio.to_thread(gen_image_hf, new_prompt)
            s["last_prompt"] = new_prompt
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=io.BytesIO(img),
                caption=f"🎨 Đã đổi sang _{tweak_val}_!",
                parse_mode="Markdown",
                reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:100]}\n\nThử lại nhé!")

    elif d == "back_result":
        await q.edit_message_text("Chọn bước tiếp theo:", reply_markup=RESULT_KB)

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))
    log.info("🚀 Nail Bot (HuggingFace) started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
