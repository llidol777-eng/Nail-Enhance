import os
import io
import logging
import asyncio
import httpx
import base64
from huggingface_hub import InferenceClient
import google.generativeai as genai
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TOKEN        = os.environ["TELEGRAM_BOT_TOKEN"]
HF_TOKEN     = os.environ.get("HF_TOKEN", "")
GEMINI_KEY   = os.environ.get("GEMINI_API_KEY", "")
OPENAI_KEY   = os.environ.get("OPENAI_API_KEY", "")

# ── AI clients ────────────────────────────────────────────────────────────────
HF_CLIENT = InferenceClient(provider="hf-inference", api_key=HF_TOKEN)

if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)
    GEMINI = genai.GenerativeModel("gemini-1.5-flash")
else:
    GEMINI = None

OPENAI = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# ── holiday map ───────────────────────────────────────────────────────────────
HOLIDAYS = {
    "h01": ("❄️ New Year's Day",    "silver glitter, countdown, midnight sparkle, festive"),
    "h02": ("💝 Valentine's Day",   "red pink hearts, roses, romantic love, cute"),
    "h03": ("🐣 Easter",            "pastel egg colors, bunny, spring flowers, soft"),
    "h04": ("🌸 St. Patrick's Day", "lucky clover, shamrock green, gold, Irish"),
    "h05": ("💐 Mother's Day",      "soft floral bouquet, pink white, elegant, feminine"),
    "h06": ("🎖️ Memorial Day",      "patriotic red white blue, stars stripes, American"),
    "h07": ("🎓 Graduation",        "gold cap diploma, black gold, achievement, luxury"),
    "h08": ("🏳️‍🌈 Pride Month",      "rainbow gradient, colorful bold, celebration, vibrant"),
    "h09": ("🎆 4th of July",       "red white blue fireworks, patriotic sparkle, American"),
    "h10": ("🎒 Back to School",    "apple pencil books, plaid tartan, fresh start, preppy"),
    "h11": ("🎃 Halloween",         "pumpkin ghost spider web, black orange purple, spooky"),
    "h12": ("🦃 Thanksgiving",      "harvest gold brown, fall foliage, warm autumn tones"),
    "h13": ("🛍️ Black Friday",      "bold black gold accent, glamorous dark luxe, chic"),
    "h14": ("🎄 Christmas",         "red green festive, snowflake, candy cane, sparkle"),
    "h15": ("🥂 New Year's Eve",    "champagne gold silver glitter, glam party, luxe"),
}

COLOR_MAP = {
    "c_pastel":   "pastel soft pink",
    "c_nude":     "nude natural beige",
    "c_bold":     "bold dark color",
    "c_glitter":  "glitter sparkle",
    "c_ombre":    "ombre gradient",
    "c_burgundy": "burgundy red wine",
    "c_black":    "black glossy",
    "c_mix":      "colorful mix",
}

SHAPE_MAP = {
    "s_almond":   "almond",
    "s_square":   "square",
    "s_coffin":   "coffin",
    "s_oval":     "oval",
    "s_stiletto": "stiletto",
    "s_round":    "round",
}

STYLE_MAP = {
    "st_minimal":  "minimalist elegant",
    "st_floral":   "floral botanical",
    "st_abstract": "abstract modern art",
    "st_3d":       "3D sculpted embossed",
    "st_french":   "French manicure classic",
    "st_marble":   "marble stone swirl",
    "st_kawaii":   "kawaii cute pastel",
    "st_dark":     "dark gothic edgy",
}

TWEAK_MAP = {
    "tw_pastel":   "pastel soft pink",
    "tw_nude":     "nude natural beige",
    "tw_bold":     "bold dark color",
    "tw_glitter":  "glitter sparkle",
    "tw_ombre":    "ombre gradient",
    "tw_burgundy": "burgundy red wine",
    "tw_almond":   "almond nail shape",
    "tw_square":   "square nail shape",
    "tw_coffin":   "coffin nail shape",
}

# ── session ───────────────────────────────────────────────────────────────────
SESSIONS: dict[int, dict] = {}

def sess(uid: int) -> dict:
    if uid not in SESSIONS:
        SESSIONS[uid] = {
            "step": 0, "theme": None, "shape": None, "style": None,
            "last_prompt": None, "model": "flux",  # default model
        }
    return SESSIONS[uid]

def reset(uid: int):
    model = sess(uid).get("model", "flux")  # giữ model đã chọn
    SESSIONS[uid] = {
        "step": 0, "theme": None, "shape": None, "style": None,
        "last_prompt": None, "model": model,
    }

# ── progress ──────────────────────────────────────────────────────────────────
def progress(step: int) -> str:
    return "".join(["▓" if i < step else "░" for i in range(5)]) + f" Bước {step}/5\n\n"

def model_label(model: str) -> str:
    if model == "dalle":
        return "⭐ DALL-E 3"
    return "🆓 FLUX.1"

# ── keyboards ─────────────────────────────────────────────────────────────────
def start_kb(model: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Gửi ảnh nail mẫu",    callback_data="flow_photo")],
        [InlineKeyboardButton("✍️ Tạo từ lựa chọn",     callback_data="flow_text")],
        [InlineKeyboardButton(f"⚙️ Model: {model_label(model)}", callback_data="choose_model")],
    ])

MODEL_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🆓 FLUX.1 — Miễn phí, ~30s",      callback_data="set_flux")],
    [InlineKeyboardButton("⭐ DALL-E 3 — Trả phí, ~10s, đẹp hơn", callback_data="set_dalle")],
    [InlineKeyboardButton("↩️ Quay lại",                       callback_data="menu_main")],
])

STEP1_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎨 Chọn tông màu",         callback_data="tab_color")],
    [InlineKeyboardButton("🎉 Chọn theo ngày lễ Mỹ",  callback_data="tab_holiday")],
    [InlineKeyboardButton("🏠 Menu chính",             callback_data="menu_main")],
])

COLOR_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🌸 Pastel",   callback_data="c_pastel"),
     InlineKeyboardButton("🤍 Nude",     callback_data="c_nude"),
     InlineKeyboardButton("💅 Đậm",      callback_data="c_bold")],
    [InlineKeyboardButton("✨ Glitter",  callback_data="c_glitter"),
     InlineKeyboardButton("🎨 Ombre",    callback_data="c_ombre"),
     InlineKeyboardButton("❤️ Đỏ rượu", callback_data="c_burgundy")],
    [InlineKeyboardButton("⬛ Đen",      callback_data="c_black"),
     InlineKeyboardButton("🌈 Mix màu",  callback_data="c_mix")],
    [InlineKeyboardButton("↩️ Quay lại", callback_data="back_step1")],
])

def holiday_kb() -> InlineKeyboardMarkup:
    rows = []
    keys = list(HOLIDAYS.keys())
    for i in range(0, len(keys), 2):
        row = []
        for k in keys[i:i+2]:
            label, _ = HOLIDAYS[k]
            row.append(InlineKeyboardButton(label, callback_data=f"hol_{k}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("↩️ Quay lại", callback_data="back_step1")])
    return InlineKeyboardMarkup(rows)

def shape_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🌙 Almond",   callback_data="s_almond"),
         InlineKeyboardButton("⬛ Square",   callback_data="s_square"),
         InlineKeyboardButton("💎 Coffin",   callback_data="s_coffin")],
        [InlineKeyboardButton("🥚 Oval",     callback_data="s_oval"),
         InlineKeyboardButton("📌 Stiletto", callback_data="s_stiletto"),
         InlineKeyboardButton("◻️ Round",    callback_data="s_round")],
        [InlineKeyboardButton("↩️ Quay lại", callback_data="back_step1")],
    ])

def style_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🕊 Minimalist",  callback_data="st_minimal"),
         InlineKeyboardButton("🌸 Floral",      callback_data="st_floral"),
         InlineKeyboardButton("💠 Abstract",    callback_data="st_abstract")],
        [InlineKeyboardButton("🌟 3D Đắp nổi", callback_data="st_3d"),
         InlineKeyboardButton("🤍 French",      callback_data="st_french"),
         InlineKeyboardButton("🌀 Marble",      callback_data="st_marble")],
        [InlineKeyboardButton("🧸 Kawaii",      callback_data="st_kawaii"),
         InlineKeyboardButton("🖤 Dark/Gothic", callback_data="st_dark")],
        [InlineKeyboardButton("↩️ Quay lại",    callback_data="back_step2")],
    ])

def confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Tạo ảnh ngay!",    callback_data="confirm_gen")],
        [InlineKeyboardButton("↩️ Quay lại",          callback_data="back_step3")],
        [InlineKeyboardButton("🔁 Chọn lại từ đầu",  callback_data="new")],
    ])

RESULT_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🔄 Biến tấu khác",       callback_data="remix")],
    [InlineKeyboardButton("🎨 Đổi màu / hình móng", callback_data="tweak")],
    [InlineKeyboardButton("✨ Retouch nail",         callback_data="retouch")],
    [InlineKeyboardButton("🏠 Tạo mẫu mới",         callback_data="new")],
])

TWEAK_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🌸 Pastel",   callback_data="tw_pastel"),
     InlineKeyboardButton("🤍 Nude",     callback_data="tw_nude"),
     InlineKeyboardButton("💅 Đậm",      callback_data="tw_bold")],
    [InlineKeyboardButton("✨ Glitter",  callback_data="tw_glitter"),
     InlineKeyboardButton("🎨 Ombre",    callback_data="tw_ombre"),
     InlineKeyboardButton("❤️ Đỏ rượu", callback_data="tw_burgundy")],
    [InlineKeyboardButton("🌙 Almond",   callback_data="tw_almond"),
     InlineKeyboardButton("⬛ Square",   callback_data="tw_square"),
     InlineKeyboardButton("💎 Coffin",   callback_data="tw_coffin")],
    [InlineKeyboardButton("↩️ Quay lại", callback_data="back_result")],
])

# ── Gemini helpers ────────────────────────────────────────────────────────────
def gemini_write_prompt(theme: str, shape: str, style: str) -> str:
    if not GEMINI:
        return (
            f"beautiful woman's hand with {style} nail art, "
            f"{theme} color, {shape} shaped nails, "
            f"gel nails, elegant hand pose, soft studio lighting, "
            f"white background, high quality, 4k, sharp focus"
        )
    result = GEMINI.generate_content(
        f"Write a detailed image generation prompt for nail art. "
        f"Theme: {theme}, nail shape: {shape}, style: {style}. "
        f"Include: beautiful woman's hand, gel nails, elegant pose, studio lighting, white background. "
        f"Return ONLY the prompt, max 60 words, in English."
    )
    return result.text.strip()

def gemini_analyze_image(image_bytes: bytes) -> str:
    if not GEMINI:
        return "nail art design"
    img_part = {"mime_type": "image/jpeg", "data": base64.b64encode(image_bytes).decode()}
    result = GEMINI.generate_content([
        img_part,
        "Analyze this nail art image. Write a detailed image generation prompt to recreate "
        "similar nail art on a beautiful woman's hand. Include colors, patterns, nail shape, "
        "style, gel finish, elegant hand pose, studio lighting, white background. "
        "Return ONLY the prompt, max 60 words, in English."
    ])
    return result.text.strip()

def gemini_retouch_prompt(original_prompt: str) -> str:
    if not GEMINI:
        return original_prompt + ", perfect nails, flawless nail art, no distortion, realistic fingers"
    result = GEMINI.generate_content(
        f"Improve this nail art image prompt to fix common AI generation issues "
        f"(deformed fingers, unrealistic nails). Make nails look perfect and realistic. "
        f"Original: {original_prompt}. "
        f"Return ONLY the improved prompt, max 70 words, in English."
    )
    return result.text.strip()

# ── image gen ─────────────────────────────────────────────────────────────────
def gen_flux(prompt: str) -> bytes:
    image = HF_CLIENT.text_to_image(
        prompt + ", perfect fingers, realistic hands, no deformity",
        model="black-forest-labs/FLUX.1-schnell",
    )
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()

def gen_dalle(prompt: str) -> bytes:
    if not OPENAI:
        raise Exception("Chưa có OpenAI API key!")
    resp = OPENAI.images.generate(
        model="dall-e-3",
        prompt=prompt + ", perfect fingers, realistic hands, professional photography",
        size="1024x1024",
        quality="standard",
        n=1,
    )
    url = resp.data[0].url
    import httpx as hx
    r = hx.get(url)
    return r.content

def gen_image(prompt: str, model: str) -> bytes:
    if model == "dalle":
        return gen_dalle(prompt)
    return gen_flux(prompt)

async def get_photo_bytes(photo, ctx) -> bytes:
    file = await ctx.bot.get_file(photo[-1].file_id)
    async with httpx.AsyncClient() as c:
        r = await c.get(file.file_path)
    return r.content

# ── show steps ────────────────────────────────────────────────────────────────
async def show_menu(q, uid: int):
    s = sess(uid)
    await q.edit_message_text(
        "💅 Bạn muốn tạo mẫu nail theo cách nào?",
        reply_markup=start_kb(s["model"]),
    )

async def show_step1(q):
    await q.edit_message_text(
        progress(1) + "Bạn muốn chọn theo:",
        reply_markup=STEP1_KB,
    )

async def show_step2(q, s):
    theme_short = s["theme"].split(",")[0] if s["theme"] else ""
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
    await q.edit_message_text(
        progress(5) +
        f"📋 *Tóm tắt lựa chọn:*\n\n"
        f"🎨 Chủ đề: *{s.get('theme','').split(',')[0]}*\n"
        f"💅 Hình móng: *{s.get('shape','')}*\n"
        f"✨ Phong cách: *{s.get('style','')}*\n"
        f"🤖 Model: *{model_label(s.get('model','flux'))}*\n\n"
        "Tạo ảnh nail ngay không?",
        parse_mode="Markdown",
        reply_markup=confirm_kb(),
    )

# ── handlers ──────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.first_name or "bạn"
    reset(uid)
    s = sess(uid)
    await update.message.reply_text(
        f"Xin chào *{name}*! 💅\n\n"
        "Chào mừng bạn đến với *Nail Bot*!\n"
        "Bạn muốn tạo mẫu nail theo cách nào?",
        parse_mode="Markdown",
        reply_markup=start_kb(s["model"]),
    )

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s   = sess(uid)
    mdl = s.get("model", "flux")
    msg = await update.message.reply_text(
        f"🔍 Gemini đang phân tích ảnh...\n"
        f"🤖 Sẽ gen bằng {model_label(mdl)}, chờ nhé!"
    )
    try:
        img_bytes = await get_photo_bytes(update.message.photo, ctx)
        prompt    = await asyncio.to_thread(gemini_analyze_image, img_bytes)
        await msg.edit_text(f"🎨 Đang gen ảnh bằng {model_label(mdl)}...")
        img_out   = await asyncio.to_thread(gen_image, prompt, mdl)
        s["last_prompt"] = prompt
        await ctx.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=io.BytesIO(img_out),
            caption=f"✨ Mẫu nail tương tự ảnh bạn gửi!\n🤖 {model_label(mdl)}",
            reply_markup=RESULT_KB,
        )
        await msg.delete()
    except Exception as e:
        log.exception(e)
        await msg.edit_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    if sess(uid)["step"] > 0:
        await update.message.reply_text("Bạn hãy chọn một trong các nút bên trên nhé 👆")
        return
    s   = sess(uid)
    mdl = s.get("model", "flux")
    msg = await update.message.reply_text(
        f"✨ Gemini đang viết prompt...\n🤖 Gen bằng {model_label(mdl)}, chờ nhé!"
    )
    try:
        prompt  = await asyncio.to_thread(gemini_write_prompt, text, "almond", "elegant")
        img     = await asyncio.to_thread(gen_image, prompt, mdl)
        s["last_prompt"] = prompt
        await ctx.bot.send_photo(
            chat_id=update.effective_chat.id,
            photo=io.BytesIO(img),
            caption=f"✨ Nail theo yêu cầu: _{text}_\n🤖 {model_label(mdl)}",
            parse_mode="Markdown",
            reply_markup=RESULT_KB,
        )
        await msg.delete()
    except Exception as e:
        log.exception(e)
        await msg.edit_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    d   = q.data
    await q.answer()
    s   = sess(uid)
    mdl = s.get("model", "flux")

    if d in ("menu_main", "new"):
        reset(uid)
        await show_menu(q, uid)

    elif d == "choose_model":
        await q.edit_message_text(
            "🤖 Chọn model AI để gen ảnh nail:",
            reply_markup=MODEL_KB,
        )

    elif d == "set_flux":
        s["model"] = "flux"
        await q.edit_message_text(
            "✅ Đã chọn *FLUX.1* — miễn phí!\n\nBạn muốn tạo mẫu nail theo cách nào?",
            parse_mode="Markdown",
            reply_markup=start_kb("flux"),
        )

    elif d == "set_dalle":
        if not OPENAI:
            await q.answer("⚠️ Chưa có OpenAI API key!", show_alert=True)
            return
        s["model"] = "dalle"
        await q.edit_message_text(
            "✅ Đã chọn *DALL-E 3* — chất lượng cao!\n\nBạn muốn tạo mẫu nail theo cách nào?",
            parse_mode="Markdown",
            reply_markup=start_kb("dalle"),
        )

    elif d == "flow_photo":
        await q.edit_message_text(
            "📸 Gửi ảnh nail bạn thích vào đây!\n"
            f"_Gemini sẽ phân tích → {model_label(mdl)} gen ảnh_ 🎨",
            parse_mode="Markdown",
        )

    elif d == "flow_text":
        s["step"] = 1
        await show_step1(q)

    elif d == "tab_color":
        await q.edit_message_text(
            progress(1) + "Chọn tông màu bạn thích 🎨",
            reply_markup=COLOR_KB,
        )

    elif d == "tab_holiday":
        await q.edit_message_text(
            progress(1) + "Chọn ngày lễ Mỹ 🎉",
            reply_markup=holiday_kb(),
        )

    elif d == "back_step1":
        s["theme"] = None
        s["step"]  = 1
        await show_step1(q)

    elif d in COLOR_MAP:
        s["theme"] = COLOR_MAP[d]
        s["step"]  = 2
        await show_step2(q, s)

    elif d.startswith("hol_"):
        key = d[4:]
        if key in HOLIDAYS:
            label, desc = HOLIDAYS[key]
            s["theme"] = f"{label}, {desc}"
            s["step"]  = 2
            await show_step2(q, s)

    elif d == "back_step2":
        s["shape"] = None
        s["step"]  = 1
        await show_step1(q)

    elif d in SHAPE_MAP:
        s["shape"] = SHAPE_MAP[d]
        s["step"]  = 3
        await show_step3(q, s)

    elif d == "back_step3":
        s["style"] = None
        s["step"]  = 2
        await show_step2(q, s)

    elif d in STYLE_MAP:
        s["style"] = STYLE_MAP[d]
        s["step"]  = 4
        await show_step4(q, s)

    elif d == "confirm_gen":
        await q.edit_message_text(
            f"⏳ Gemini đang viết prompt...\n🤖 Gen bằng {model_label(mdl)}, chờ nhé!"
        )
        try:
            prompt = await asyncio.to_thread(
                gemini_write_prompt,
                s.get("theme", "elegant nail art"),
                s.get("shape", "almond"),
                s.get("style", "minimalist"),
            )
            img = await asyncio.to_thread(gen_image, prompt, mdl)
            s["last_prompt"] = prompt
            s["step"]        = 0
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=io.BytesIO(img),
                caption=f"✨ Đây là ảnh nail của bạn!\n🤖 {model_label(mdl)}",
                reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "remix":
        last = s.get("last_prompt")
        if not last:
            await show_menu(q, uid)
            return
        await q.edit_message_text(f"🔄 Đang tạo biến tấu, gen bằng {model_label(mdl)}...")
        try:
            new_prompt = last + ", creative variation, different composition"
            img = await asyncio.to_thread(gen_image, new_prompt, mdl)
            s["last_prompt"] = new_prompt
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=io.BytesIO(img),
                caption=f"🔄 Biến tấu mới!\n🤖 {model_label(mdl)}",
                reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "retouch":
        last = s.get("last_prompt")
        if not last:
            await show_menu(q, uid)
            return
        await q.edit_message_text(
            f"✨ Gemini đang retouch prompt...\n🤖 Gen lại bằng {model_label(mdl)}, chờ nhé!"
        )
        try:
            retouched = await asyncio.to_thread(gemini_retouch_prompt, last)
            img = await asyncio.to_thread(gen_image, retouched, mdl)
            s["last_prompt"] = retouched
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=io.BytesIO(img),
                caption=f"✨ Ảnh nail đã được retouch!\n🤖 {model_label(mdl)}",
                reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "tweak":
        await q.edit_message_text(
            "🎨 Chọn màu hoặc hình dạng móng muốn thay:",
            reply_markup=TWEAK_KB,
        )

    elif d in TWEAK_MAP:
        tweak_val = TWEAK_MAP[d]
        await q.edit_message_text(
            f"🎨 Gemini đang viết prompt cho *{tweak_val}*...",
            parse_mode="Markdown",
        )
        try:
            prompt = await asyncio.to_thread(
                gemini_write_prompt, tweak_val, "almond", "elegant"
            )
            img = await asyncio.to_thread(gen_image, prompt, mdl)
            s["last_prompt"] = prompt
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=io.BytesIO(img),
                caption=f"🎨 Đã đổi sang _{tweak_val}_!\n🤖 {model_label(mdl)}",
                parse_mode="Markdown",
                reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "back_result":
        await q.edit_message_text(
            "Chọn bước tiếp theo:",
            reply_markup=RESULT_KB,
        )

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))
    log.info("🚀 Nail Bot (Gemini + FLUX + DALL-E 3) started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
