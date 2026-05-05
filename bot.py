"""
Nail Telegram Bot
Flow 6 bước: Chủ đề (màu/lễ) → Dịp → Hình móng → Phong cách → Kích thước → Gen ảnh
GPT-4o Vision phân tích ảnh + DALL-E 3 tạo ảnh
"""

import os, logging, asyncio, base64, httpx
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

AI    = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
RUN_SECONDS = int(os.environ.get("BOT_RUN_SECONDS", "180"))

# ── session ──────────────────────────────────────────────────────────────────
SESSIONS: dict[int, dict] = {}

def sess(uid):
    if uid not in SESSIONS:
        SESSIONS[uid] = {"step": "idle", "params": {}}
    return SESSIONS[uid]

def set_step(uid, step):   sess(uid)["step"] = step
def set_param(uid, k, v):  sess(uid)["params"][k] = v
def get_params(uid):       return sess(uid).get("params", {})
def reset(uid):            SESSIONS[uid] = {"step": "idle", "params": {}}

# ── data ─────────────────────────────────────────────────────────────────────
COLORS = {
    "🌸 Pastel":    "soft pastel pink lavender mint tones",
    "🤍 Nude":      "nude beige natural skin tones",
    "💅 Đậm/Bold":  "bold vibrant saturated colors",
    "✨ Glitter":   "glitter shimmer metallic sparkle",
    "🎨 Ombre":     "ombre gradient color fade",
    "❤️ Đỏ rượu":  "deep burgundy wine red",
    "⬛ Đen":       "black dark elegant",
    "🌈 Nhiều màu": "multicolor rainbow vibrant",
}

HOLIDAYS = {
    "❄️ New Year's Day":    "New Year celebration silver glitter midnight sparkle festive countdown",
    "💝 Valentine's Day":   "Valentine romantic red pink hearts roses love cupid sweetheart",
    "🐣 Easter":            "Easter pastel bunny spring flowers egg colors soft lavender pink yellow",
    "🍀 St. Patrick's Day": "St Patrick's Day shamrock clover green gold Irish lucky festival",
    "💐 Mother's Day":      "Mother's Day floral bouquet elegant pink white heartfelt delicate",
    "🎖️ Memorial Day":      "Memorial Day patriotic red white blue stars stripes American flag",
    "🎓 Graduation":        "graduation gold cap diploma achievement celebration black gold elegant",
    "🏳️‍🌈 Pride Month":      "Pride rainbow gradient colorful bold love inclusion celebration",
    "🎆 4th of July":       "Independence Day fireworks red white blue stars stripes patriotic glitter",
    "🎒 Back to School":    "back to school apple pencil books fresh start blue red preppy plaid",
    "🎃 Halloween":         "Halloween pumpkin ghost spider web black orange purple gothic glam spooky",
    "🦃 Thanksgiving":      "Thanksgiving harvest gold brown orange fall foliage pumpkin pie warm tones",
    "🛍️ Black Friday":      "Black Friday bold black gold accent glamorous dark luxe statement nails",
    "🎄 Christmas":         "Christmas red green snowflake reindeer candy cane holiday sparkle winter",
    "🥂 New Year's Eve":    "New Year's Eve champagne gold silver glitter midnight party luxe sparkle",
    "👨 Father's Day":      "Father's Day navy gold geometric sophisticated classic masculine elegant",
}

OCCASIONS = {
    "👩‍💼 Đi làm":     "office professional daily wear",
    "💒 Đám cưới":   "wedding formal elegant ceremony",
    "🎉 Sinh nhật":  "birthday party celebration fun",
    "💑 Hẹn hò":     "date night romantic",
    "✈️ Du lịch":    "travel vacation casual",
    "🎓 Tốt nghiệp": "graduation ceremony achievement",
    "🎊 Tiệc":       "party event night out",
    "🏠 Hàng ngày":  "everyday casual comfortable",
}

SHAPES = {
    "🌙 Almond":   "almond shaped nails",
    "⬛ Square":   "square shaped nails",
    "💎 Coffin":   "coffin ballerina shaped nails",
    "🥚 Oval":     "oval shaped nails",
    "📌 Stiletto": "stiletto sharp pointed nails",
    "◻️ Round":    "round short nails",
}

STYLES = {
    "🕊 Minimalist":    "minimalist clean simple elegant",
    "🌸 Floral":        "floral botanical flower petals nail art",
    "💠 Abstract":      "abstract artistic modern geometric",
    "🌟 3D / Nổi":      "3D sculpted raised nail art embellishments",
    "🤍 French":        "French manicure classic white tips",
    "🌀 Marble":        "marble stone swirl texture",
    "🧸 Kawaii":        "kawaii cute cartoon japanese aesthetic",
    "🖤 Dark/Gothic":   "dark gothic edgy dramatic",
    "❄️ Festive":       "festive holiday seasonal decorative",
    "✨ Glitter Glam":  "full glitter glamorous sparkle all-over",
}

SIZES = {
    "📷 1024×1024 — Vuông (Instagram, Zalo)":    {"val": "1024x1024", "w": 1024, "h": 1024},
    "🖼 1792×1024 — Ngang (Banner, Facebook)":   {"val": "1792x1024", "w": 1792, "h": 1024},
    "📱 1024×1792 — Dọc (Story, TikTok)":        {"val": "1024x1792", "w": 1024, "h": 1792},
}

# ── keyboards ────────────────────────────────────────────────────────────────
def chunk(lst, n):
    return [lst[i:i+n] for i in range(0, len(lst), n)]

def make_kb(items, prefix, cols=2):
    rows = chunk(list(items.keys()), cols)
    return InlineKeyboardMarkup([
        [InlineKeyboardButton(label, callback_data=f"{prefix}{label}") for label in row]
        for row in rows
    ])

START_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("📸 Gửi ảnh → tạo mẫu tương tự", callback_data="flow_photo")],
    [InlineKeyboardButton("✍️  Mô tả để tạo mẫu",           callback_data="flow_text")],
])

STEP1_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎨 Chọn theo tông màu",   callback_data="s1_color")],
    [InlineKeyboardButton("🎉 Chọn theo ngày lễ Mỹ", callback_data="s1_holiday")],
])

def result_kb():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Biến tấu khác",       callback_data="remix")],
        [InlineKeyboardButton("🎨 Đổi màu / hình móng",  callback_data="tweak")],
        [InlineKeyboardButton("🏠 Tạo mẫu mới",          callback_data="new")],
    ])

TWEAK_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🌸 Pastel",    callback_data="tw_🌸 Pastel"),
     InlineKeyboardButton("🤍 Nude",      callback_data="tw_🤍 Nude"),
     InlineKeyboardButton("💅 Đậm",       callback_data="tw_💅 Đậm/Bold")],
    [InlineKeyboardButton("✨ Glitter",   callback_data="tw_✨ Glitter"),
     InlineKeyboardButton("❤️ Đỏ rượu",  callback_data="tw_❤️ Đỏ rượu"),
     InlineKeyboardButton("⬛ Đen",       callback_data="tw_⬛ Đen")],
    [InlineKeyboardButton("🌙 Almond",    callback_data="tws_🌙 Almond"),
     InlineKeyboardButton("⬛ Square",    callback_data="tws_⬛ Square"),
     InlineKeyboardButton("💎 Coffin",    callback_data="tws_💎 Coffin")],
    [InlineKeyboardButton("🥚 Oval",      callback_data="tws_🥚 Oval"),
     InlineKeyboardButton("📌 Stiletto",  callback_data="tws_📌 Stiletto"),
     InlineKeyboardButton("◻️ Round",     callback_data="tws_◻️ Round")],
    [InlineKeyboardButton("↩️ Quay lại", callback_data="back_result")],
])

# ── OpenAI helpers ────────────────────────────────────────────────────────────
def build_dalle_prompt(p: dict) -> str:
    parts = [
        "Professional nail art photography,",
        "close-up macro shot of beautiful nails,",
        p.get("theme", ""),
        p.get("shape", ""),
        p.get("style", ""),
        f"for {p.get('occasion', '')}," if p.get("occasion") else "",
        "studio lighting, white background, 8k ultra detail,",
        "glossy gel finish, perfect nail art, pinterest aesthetic,",
        "no hands visible, isolated nail photo",
    ]
    return " ".join(x for x in parts if x)

def build_neg_prompt() -> str:
    return "blurry, low quality, bad anatomy, distorted, ugly nails, dirty, broken nails, text, watermark"

async def generate_image(p: dict) -> str:
    """Gọi DALL-E 3, trả về URL ảnh"""
    prompt = build_dalle_prompt(p)
    size_val = p.get("size_val", "1024x1024")
    response = await asyncio.to_thread(
        lambda: AI.images.generate(
            model="dall-e-3",
            prompt=prompt,
            size=size_val,
            quality="standard",
            n=1,
        )
    )
    return response.data[0].url

async def analyze_photo(image_b64: str, mime: str) -> str:
    """GPT-4o Vision phân tích ảnh nail"""
    response = await asyncio.to_thread(
        lambda: AI.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {
                        "url": f"data:{mime};base64,{image_b64}"
                    }},
                    {"type": "text", "text": (
                        "Phân tích chi tiết mẫu nail trong ảnh. Mô tả: màu sắc chính xác, "
                        "phong cách, họa tiết, hình dạng móng, finish (matte/glossy). "
                        "Trả lời ngắn gọn bằng tiếng Việt, thân thiện như chuyên gia nail."
                    )}
                ]
            }],
            max_tokens=300,
        )
    )
    return response.choices[0].message.content

async def download_photo_b64(photo, context) -> tuple[str, str]:
    file = await context.bot.get_file(photo[-1].file_id)
    async with httpx.AsyncClient() as client:
        r = await client.get(file.file_path)
    b64 = base64.standard_b64encode(r.content).decode()
    mime = "image/jpeg"
    return b64, mime

# ── handlers ─────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    reset(update.effective_user.id)
    name = update.effective_user.first_name or "bạn"
    await update.message.reply_text(
        f"Xin chào *{name}*! 💅\n\nMình là *Nail Bot* — tạo mẫu nail bằng AI.\n\nChọn cách bạn muốn bắt đầu:",
        parse_mode="Markdown",
        reply_markup=START_KB,
    )

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    msg = await update.message.reply_text("🔍 Đang phân tích ảnh nail của bạn...")
    try:
        b64, mime = await download_photo_b64(update.message.photo, ctx)
        caption = update.message.caption or ""

        analysis = await analyze_photo(b64, mime)

        # Tự động set params từ phân tích ảnh
        set_param(uid, "theme", "analyzed from uploaded photo")
        set_param(uid, "analysis", analysis)
        set_param(uid, "source", "photo")
        set_step(uid, "photo_analyzed")

        await msg.edit_text(
            f"✅ *Phân tích xong!*\n\n{analysis}\n\n"
            "Bạn muốn tạo ảnh nail tương tự với kích thước nào?",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📷 1024×1024 — Vuông", callback_data="photosize_1024x1024")],
                [InlineKeyboardButton("🖼 1792×1024 — Ngang",  callback_data="photosize_1792x1024")],
                [InlineKeyboardButton("📱 1024×1792 — Dọc",    callback_data="photosize_1024x1792")],
            ])
        )
    except Exception as e:
        log.exception(e)
        await msg.edit_text("❌ Lỗi phân tích ảnh, thử lại nhé!")

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    d   = q.data
    await q.answer()

    # ── Start flow ──
    if d == "flow_photo":
        set_step(uid, "waiting_photo")
        await q.edit_message_text(
            "📸 Gửi ảnh nail bạn thích vào đây!\n\n"
            "_GPT-4o sẽ phân tích và tạo mẫu tương tự bằng DALL-E 3._",
            parse_mode="Markdown",
        )

    elif d == "flow_text":
        set_step(uid, "step1")
        await q.edit_message_text(
            "✍️ *Bước 1/6* — Bạn muốn chọn theo:",
            parse_mode="Markdown",
            reply_markup=STEP1_KB,
        )

    # ── Step 1 ──
    elif d == "s1_color":
        await q.edit_message_text(
            "🎨 *Bước 1/6* — Chọn tông màu:",
            parse_mode="Markdown",
            reply_markup=make_kb(COLORS, "color_", cols=3),
        )

    elif d == "s1_holiday":
        await q.edit_message_text(
            "🎉 *Bước 1/6* — Chọn ngày lễ Mỹ:",
            parse_mode="Markdown",
            reply_markup=make_kb(HOLIDAYS, "hol_", cols=2),
        )

    elif d.startswith("color_"):
        label = d[6:]
        if label in COLORS:
            set_param(uid, "theme", COLORS[label])
            set_param(uid, "theme_label", label)
            await q.edit_message_text(
                "📅 *Bước 2/6* — Làm cho dịp gì?",
                parse_mode="Markdown",
                reply_markup=make_kb(OCCASIONS, "occ_", cols=2),
            )

    elif d.startswith("hol_"):
        label = d[4:]
        if label in HOLIDAYS:
            set_param(uid, "theme", HOLIDAYS[label])
            set_param(uid, "theme_label", label)
            await q.edit_message_text(
                "📅 *Bước 2/6* — Làm cho dịp gì?",
                parse_mode="Markdown",
                reply_markup=make_kb(OCCASIONS, "occ_", cols=2),
            )

    # ── Step 2 ──
    elif d.startswith("occ_"):
        label = d[4:]
        if label in OCCASIONS:
            set_param(uid, "occasion", OCCASIONS[label])
            set_param(uid, "occasion_label", label)
            await q.edit_message_text(
                "💅 *Bước 3/6* — Hình dạng móng?",
                parse_mode="Markdown",
                reply_markup=make_kb(SHAPES, "shp_", cols=3),
            )

    # ── Step 3 ──
    elif d.startswith("shp_"):
        label = d[4:]
        if label in SHAPES:
            set_param(uid, "shape", SHAPES[label])
            set_param(uid, "shape_label", label)
            await q.edit_message_text(
                "✨ *Bước 4/6* — Phong cách nail?",
                parse_mode="Markdown",
                reply_markup=make_kb(STYLES, "sty_", cols=2),
            )

    # ── Step 4 ──
    elif d.startswith("sty_"):
        label = d[4:]
        if label in STYLES:
            set_param(uid, "style", STYLES[label])
            set_param(uid, "style_label", label)
            await q.edit_message_text(
                "📐 *Bước 5/6* — Kích thước ảnh đầu ra?",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton(k, callback_data=f"size_{k}")] for k in SIZES
                ]),
            )

    # ── Step 5 — size ──
    elif d.startswith("size_"):
        label = d[5:]
        if label in SIZES:
            info = SIZES[label]
            set_param(uid, "size_val", info["val"])
            set_param(uid, "size_label", label)
            p = get_params(uid)
            summary = (
                f"📋 *Tóm tắt yêu cầu:*\n\n"
                f"🎨 Chủ đề: {p.get('theme_label','')}\n"
                f"📅 Dịp: {p.get('occasion_label','')}\n"
                f"💅 Hình móng: {p.get('shape_label','')}\n"
                f"✨ Phong cách: {p.get('style_label','')}\n"
                f"📐 Kích thước: {info['val']}\n\n"
                "Tạo ảnh ngay không?"
            )
            await q.edit_message_text(
                summary,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✅ Tạo ảnh ngay!", callback_data="gen")],
                    [InlineKeyboardButton("🔁 Chọn lại từ đầu", callback_data="new")],
                ]),
            )

    # ── Photo size ──
    elif d.startswith("photosize_"):
        size_val = d[10:]
        set_param(uid, "size_val", size_val)
        set_param(uid, "source", "photo")
        await _do_gen(q, uid)

    # ── Gen ──
    elif d == "gen":
        await _do_gen(q, uid)

    # ── Remix ──
    elif d == "remix":
        p = get_params(uid)
        if not p.get("theme"):
            await q.edit_message_text("Hãy tạo mẫu mới trước nhé!", reply_markup=START_KB)
            return
        await _do_gen(q, uid)

    # ── Tweak ──
    elif d == "tweak":
        await q.edit_message_text(
            "🎨 Chọn thay đổi bạn muốn:",
            reply_markup=TWEAK_KB,
        )

    elif d.startswith("tw_"):
        label = d[3:]
        if label in COLORS:
            set_param(uid, "theme", COLORS[label])
            set_param(uid, "theme_label", label)
        await _do_gen(q, uid)

    elif d.startswith("tws_"):
        label = d[4:]
        if label in SHAPES:
            set_param(uid, "shape", SHAPES[label])
            set_param(uid, "shape_label", label)
        await _do_gen(q, uid)

    elif d == "back_result":
        await q.edit_message_text(
            "Chọn tiếp theo bạn muốn làm gì:",
            reply_markup=result_kb(),
        )

    elif d == "new":
        reset(uid)
        await q.edit_message_text(
            "💅 Tạo mẫu nail mới!\n\nChọn cách bắt đầu:",
            reply_markup=START_KB,
        )

async def _do_gen(q, uid: int):
    """Gen ảnh DALL-E 3 và gửi cho user"""
    await q.edit_message_text("⏳ Đang tạo ảnh nail, chờ mình một chút...")
    p = get_params(uid)
    try:
        url = await generate_image(p)
        # Download ảnh rồi gửi qua Telegram
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.get(url)
        img_bytes = r.content

        caption = (
            f"✨ *Ảnh nail của bạn!*\n\n"
            f"🎨 {p.get('theme_label','')}\n"
            f"💅 {p.get('shape_label','')} · {p.get('style_label','')}\n"
            f"📐 {p.get('size_val','1024x1024')}"
        )
        await q.message.reply_photo(
            photo=img_bytes,
            caption=caption,
            parse_mode="Markdown",
            reply_markup=result_kb(),
        )
        await q.delete_message()

    except Exception as e:
        log.exception(e)
        await q.edit_message_text(
            "❌ Lỗi tạo ảnh. Thử lại nhé!",
            reply_markup=result_kb(),
        )

# ── main ─────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(CallbackQueryHandler(handle_callback))
    log.info(f"Bot started — polling {RUN_SECONDS}s ...")
    app.run_polling(
        drop_pending_updates=True,
        stop_signals=None,
        close_loop=False,
        timeout=RUN_SECONDS,
    )

if __name__ == "__main__":
    import signal, threading
    def _stop():
        import time; time.sleep(RUN_SECONDS)
        os.kill(os.getpid(), signal.SIGINT)
    threading.Thread(target=_stop, daemon=True).start()
    main()
