"""
Nail Telegram Bot
- Menu + 5 bước chọn option: hoạt động ngay, không cần OpenAI key
- Gen ảnh DALL-E 3 + GPT-4o Vision: bật tự động khi có OPENAI_API_KEY
"""

import os, logging, asyncio, base64, httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TOKEN      = os.environ["TELEGRAM_BOT_TOKEN"]
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

AI = None
if OPENAI_KEY:
    from openai import OpenAI
    AI = OpenAI(api_key=OPENAI_KEY)
    log.info("OpenAI ready — image generation enabled")
else:
    log.info("No OpenAI key — image generation disabled")

# ── session ───────────────────────────────────────────────────────────────────
SESSIONS: dict[int, dict] = {}

def sess(uid: int) -> dict:
    if uid not in SESSIONS:
        SESSIONS[uid] = {"step": 0, "theme": None, "shape": None, "style": None, "last_prompt": None}
    return SESSIONS[uid]

def reset(uid: int):
    SESSIONS[uid] = {"step": 0, "theme": None, "shape": None, "style": None, "last_prompt": None}

# ── keyboards ─────────────────────────────────────────────────────────────────
START_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("📸 Gửi ảnh nail mẫu",     callback_data="flow_photo")],
    [InlineKeyboardButton("✍️ Tạo từ lựa chọn",      callback_data="flow_text")],
])

STEP1_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎨 Chọn tông màu",         callback_data="tab_color")],
    [InlineKeyboardButton("🎉 Chọn theo ngày lễ Mỹ",  callback_data="tab_holiday")],
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

SHAPE_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🌙 Almond",   callback_data="shape_almond"),
     InlineKeyboardButton("⬛ Square",   callback_data="shape_square"),
     InlineKeyboardButton("💎 Coffin",   callback_data="shape_coffin")],
    [InlineKeyboardButton("🥚 Oval",     callback_data="shape_oval"),
     InlineKeyboardButton("📌 Stiletto", callback_data="shape_stiletto"),
     InlineKeyboardButton("◻️ Round",    callback_data="shape_round")],
])

STYLE_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🕊 Minimalist",  callback_data="style_minimalist elegant"),
     InlineKeyboardButton("🌸 Floral",      callback_data="style_floral botanical"),
     InlineKeyboardButton("💠 Abstract",    callback_data="style_abstract modern art")],
    [InlineKeyboardButton("🌟 3D Đắp nổi", callback_data="style_3D sculpted embossed"),
     InlineKeyboardButton("🤍 French",      callback_data="style_French manicure classic"),
     InlineKeyboardButton("🌀 Marble",      callback_data="style_marble stone swirl")],
    [InlineKeyboardButton("🧸 Kawaii",      callback_data="style_kawaii cute pastel"),
     InlineKeyboardButton("🖤 Dark/Gothic", callback_data="style_dark gothic edgy")],
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

SOON_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🏠 Tạo mẫu mới", callback_data="new")],
])

# ── helpers ───────────────────────────────────────────────────────────────────
def progress(step: int) -> str:
    return "".join(["▓" if i < step else "░" for i in range(5)]) + f" Bước {step}/5\n\n"

def soon_msg() -> str:
    return (
        "⏳ *Tính năng gen ảnh sắp ra mắt!*\n\n"
        "Chức năng tạo ảnh AI đang được cấu hình.\n"
        "Vui lòng quay lại sau nhé 💕"
    )

def build_prompt(theme: str, shape: str, style: str) -> str:
    return (
        f"Professional nail art photography, macro close-up, "
        f"{theme}, {shape} nail shape, {style} style, "
        f"gel finish, studio lighting, white background, 8k ultra detail, pinterest aesthetic"
    )

def gen_image(prompt: str) -> str:
    resp = AI.images.generate(
        model="dall-e-3", prompt=prompt,
        size="1024x1024", quality="standard", n=1,
    )
    return resp.data[0].url

def analyze_and_gen(b64: str, mime: str) -> tuple[str, str]:
    r = AI.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
            {"type": "text", "text": (
                "Analyze this nail art. Return ONLY a DALL-E prompt (max 50 words) "
                "to recreate similar style. Start with: "
                "'Professional nail art photography, macro close-up,'"
            )},
        ]}],
        max_tokens=120,
    )
    prompt = r.choices[0].message.content.strip()
    return prompt, gen_image(prompt)

async def get_photo_b64(photo, ctx) -> tuple[str, str]:
    file = await ctx.bot.get_file(photo[-1].file_id)
    async with httpx.AsyncClient() as c:
        r = await c.get(file.file_path)
    b64  = base64.standard_b64encode(r.content).decode()
    mime = "image/jpeg" if file.file_path.lower().endswith(".jpg") else "image/png"
    return b64, mime

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
    if not AI:
        await update.message.reply_text(soon_msg(), parse_mode="Markdown", reply_markup=SOON_KB)
        return
    msg = await update.message.reply_text("🔍 Đang phân tích ảnh...")
    try:
        b64, mime   = await get_photo_b64(update.message.photo, ctx)
        prompt, url = await asyncio.to_thread(analyze_and_gen, b64, mime)
        sess(update.effective_user.id)["last_prompt"] = prompt
        await ctx.bot.send_photo(
            chat_id=update.effective_chat.id, photo=url,
            caption="✨ Đây là mẫu nail tương tự ảnh bạn gửi!",
            reply_markup=RESULT_KB,
        )
        await msg.delete()
    except Exception as e:
        log.exception(e)
        await msg.edit_text("❌ Lỗi phân tích ảnh, thử lại nhé!")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    if sess(uid)["step"] > 0:
        await update.message.reply_text("Bạn hãy chọn một trong các nút bên trên nhé 👆")
        return
    if not AI:
        await update.message.reply_text(soon_msg(), parse_mode="Markdown", reply_markup=SOON_KB)
        return
    msg = await update.message.reply_text("✨ Đang tạo ảnh nail...")
    try:
        prompt = build_prompt(text, "almond", "elegant")
        url    = await asyncio.to_thread(gen_image, prompt)
        sess(uid)["last_prompt"] = prompt
        await ctx.bot.send_photo(
            chat_id=update.effective_chat.id, photo=url,
            caption=f"✨ Nail theo yêu cầu: _{text}_",
            parse_mode="Markdown", reply_markup=RESULT_KB,
        )
        await msg.delete()
    except Exception as e:
        log.exception(e)
        await msg.edit_text("❌ Lỗi tạo ảnh, thử lại nhé!")

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q, uid, d = update.callback_query, update.callback_query.from_user.id, update.callback_query.data
    await q.answer()
    s = sess(uid)

    if d == "flow_photo":
        if not AI:
            await q.edit_message_text(soon_msg(), parse_mode="Markdown", reply_markup=SOON_KB)
        else:
            await q.edit_message_text(
                "📸 Gửi ảnh nail bạn thích vào đây!\n"
                "_GPT-4o phân tích → DALL-E 3 tạo mẫu tương tự_ 🎨",
                parse_mode="Markdown",
            )

    elif d == "flow_text":
        s["step"] = 1
        await q.edit_message_text(progress(1) + "Bạn muốn chọn theo:", reply_markup=STEP1_KB)

    elif d == "tab_color":
        await q.edit_message_text(progress(1) + "Chọn tông màu bạn thích 🎨", reply_markup=COLOR_KB)

    elif d == "tab_holiday":
        await q.edit_message_text(progress(1) + "Chọn ngày lễ Mỹ 🎉", reply_markup=HOLIDAY_KB)

    elif d == "back_step1":
        await q.edit_message_text(progress(1) + "Bạn muốn chọn theo:", reply_markup=STEP1_KB)

    elif d.startswith("theme_"):
        s["theme"] = d[6:]
        s["step"]  = 2
        await q.edit_message_text(
            progress(2) + f"Đã chọn: *{s['theme'].split(' -')[0]}* ✅\n\nHình dạng móng?",
            parse_mode="Markdown", reply_markup=SHAPE_KB,
        )

    elif d.startswith("shape_"):
        s["shape"] = d[6:]
        s["step"]  = 3
        await q.edit_message_text(
            progress(3) + f"Hình: *{s['shape']}* ✅\n\nPhong cách nail?",
            parse_mode="Markdown", reply_markup=STYLE_KB,
        )

    elif d.startswith("style_"):
        s["style"] = d[6:]
        s["step"]  = 4
        theme_short = s["theme"].split(" -")[0] if s["theme"] else ""
        await q.edit_message_text(
            progress(5) +
            f"📋 *Tóm tắt lựa chọn:*\n\n"
            f"🎨 Chủ đề: *{theme_short}*\n"
            f"💅 Hình móng: *{s['shape']}*\n"
            f"✨ Phong cách: *{s['style']}*\n\n"
            "Tạo ảnh nail ngay không?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ Tạo ảnh ngay!", callback_data="confirm_gen")],
                [InlineKeyboardButton("🔁 Chọn lại từ đầu", callback_data="new")],
            ]),
        )

    elif d == "confirm_gen":
        if not AI:
            await q.edit_message_text(soon_msg(), parse_mode="Markdown", reply_markup=SOON_KB)
            return
        await q.edit_message_text("⏳ Đang tạo ảnh, chờ mình 20 giây nhé...")
        try:
            prompt = build_prompt(s.get("theme","elegant nail art"), s.get("shape","almond"), s.get("style","minimalist"))
            url    = await asyncio.to_thread(gen_image, prompt)
            s["last_prompt"] = prompt
            s["step"]        = 0
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id, photo=url,
                caption="✨ Đây là ảnh nail của bạn!", reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text("❌ Lỗi tạo ảnh, thử lại nhé!")

    elif d == "remix":
        if not AI:
            await q.edit_message_text(soon_msg(), parse_mode="Markdown", reply_markup=SOON_KB)
            return
        last = s.get("last_prompt")
        if not last:
            await q.edit_message_text("Hãy tạo mẫu mới nhé!", reply_markup=START_KB)
            return
        await q.edit_message_text("🔄 Đang tạo biến tấu mới...")
        try:
            url = await asyncio.to_thread(gen_image, last + ", creative variation")
            s["last_prompt"] = last + ", creative variation"
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id, photo=url,
                caption="🔄 Biến tấu mới đây!", reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text("❌ Lỗi, thử lại nhé!")

    elif d == "tweak":
        await q.edit_message_text("🎨 Chọn màu hoặc hình dạng móng muốn thay:", reply_markup=TWEAK_KB)

    elif d.startswith("tw_"):
        if not AI:
            await q.edit_message_text(soon_msg(), parse_mode="Markdown", reply_markup=SOON_KB)
            return
        tweak_val = d[3:]
        await q.edit_message_text(f"🎨 Đang tạo với *{tweak_val}*...", parse_mode="Markdown")
        try:
            new_prompt = f"Professional nail art photography, macro close-up, {tweak_val}, gel finish, studio lighting, white background, 8k ultra detail"
            url = await asyncio.to_thread(gen_image, new_prompt)
            s["last_prompt"] = new_prompt
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id, photo=url,
                caption=f"🎨 Đã đổi sang _{tweak_val}_!",
                parse_mode="Markdown", reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text("❌ Lỗi, thử lại nhé!")

    elif d == "back_result":
        await q.edit_message_text("Chọn bước tiếp theo:", reply_markup=RESULT_KB)

    elif d == "new":
        reset(uid)
        await q.edit_message_text(
            "💅 Tạo mẫu nail mới!\n\nBạn muốn tạo theo cách nào?",
            reply_markup=START_KB,
        )

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))
    log.info("🚀 Nail Bot started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
