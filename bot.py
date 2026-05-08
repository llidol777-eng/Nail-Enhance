import os
import io
import logging
import asyncio
import httpx
import base64
import requests
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TOKEN       = os.environ["TELEGRAM_BOT_TOKEN"]
HF_TOKEN    = os.environ.get("HF_TOKEN", "")
GLM_KEY     = os.environ.get("GLM_API_KEY", "")
OPENAI_KEY  = os.environ.get("OPENAI_API_KEY", "")

# ── AI clients ────────────────────────────────────────────────────────────────
GLM_CLIENT    = OpenAI(api_key=GLM_KEY,    base_url="https://open.bigmodel.cn/api/paas/v4/") if GLM_KEY else None
OPENAI_CLIENT = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# ── data maps ─────────────────────────────────────────────────────────────────
HOLIDAYS = {
    "h01": ("❄️ New Year's Day",    "silver glitter, countdown, midnight sparkle"),
    "h02": ("💝 Valentine's Day",   "red pink hearts, roses, romantic love"),
    "h03": ("🐣 Easter",            "pastel egg colors, bunny, spring flowers"),
    "h04": ("🌸 St. Patrick's Day", "lucky clover, shamrock green, gold"),
    "h05": ("💐 Mother's Day",      "soft floral bouquet, pink white, elegant"),
    "h06": ("🎖️ Memorial Day",      "patriotic red white blue, stars stripes"),
    "h07": ("🎓 Graduation",        "gold cap diploma, black gold, achievement"),
    "h08": ("🏳️‍🌈 Pride Month",      "rainbow gradient, colorful bold, celebration"),
    "h09": ("🎆 4th of July",       "red white blue fireworks, patriotic sparkle"),
    "h10": ("🎒 Back to School",    "apple pencil books, plaid tartan, fresh start"),
    "h11": ("🎃 Halloween",         "pumpkin ghost spider web, black orange purple"),
    "h12": ("🦃 Thanksgiving",      "harvest gold brown, fall foliage, warm tones"),
    "h13": ("🛍️ Black Friday",      "bold black gold accent, glamorous dark luxe"),
    "h14": ("🎄 Christmas",         "red green festive, snowflake, candy cane"),
    "h15": ("🥂 New Year's Eve",    "champagne gold silver glitter, glam party"),
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
            "last_prompt": None, "model": "gptimage2",
            "pending_prompt": None, "editing_prompt": False,
        }
    return SESSIONS[uid]

def reset(uid: int):
    model = sess(uid).get("model", "gptimage2")
    SESSIONS[uid] = {
        "step": 0, "theme": None, "shape": None, "style": None,
        "last_prompt": None, "model": model,
        "pending_prompt": None, "editing_prompt": False,
    }

def progress(step: int) -> str:
    return "".join(["▓" if i < step else "░" for i in range(5)]) + f" Bước {step}/5\n\n"

def model_label(model: str) -> str:
    if model == "gptimage2":
        return "⭐ GPT Image 2"
    return "🆓 FLUX.1"

# ── GLM-4 helpers ─────────────────────────────────────────────────────────────
def glm_write_prompt(theme: str, shape: str = "almond", style: str = "elegant") -> str:
    if not GLM_CLIENT:
        return (
            f"beautiful woman's hand with {style} nail art, {theme} color, "
            f"{shape} shaped nails, gel nails, elegant pose, studio lighting, "
            f"white background, high quality, 4k, photorealistic"
        )
    resp = GLM_CLIENT.chat.completions.create(
        model="glm-4-flash",
        messages=[{"role": "user", "content": (
            f"Write a detailed image generation prompt for nail art photography. "
            f"Theme/color: {theme}, nail shape: {shape}, style: {style}. "
            f"Must include: beautiful woman's hand, gel nails, elegant pose, "
            f"studio lighting, white background, photorealistic, high quality. "
            f"Return ONLY the prompt, max 70 words, English. No quotes."
        )}],
        max_tokens=150,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()

def glm_analyze_image(image_bytes: bytes) -> str:
    if not GLM_CLIENT:
        return "nail art design, beautiful woman's hand, gel nails, studio lighting"
    b64 = base64.b64encode(image_bytes).decode()
    resp = GLM_CLIENT.chat.completions.create(
        model="glm-4v-flash",
        messages=[{"role": "user", "content": [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
            {"type": "text", "text": (
                "Analyze this nail art image. Write a detailed image generation prompt "
                "to recreate similar nail art on a beautiful woman's hand. "
                "Include colors, patterns, nail shape, style, finish, elegant pose, "
                "studio lighting, white background, photorealistic. "
                "Return ONLY the prompt, max 70 words, English. No quotes."
            )}
        ]}],
        max_tokens=150,
    )
    return resp.choices[0].message.content.strip()

def glm_retouch_prompt(original_prompt: str) -> str:
    if not GLM_CLIENT:
        return original_prompt + ", perfect nails, flawless nail art, no distortion, realistic fingers"
    resp = GLM_CLIENT.chat.completions.create(
        model="glm-4-flash",
        messages=[{"role": "user", "content": (
            f"Improve this nail art prompt to fix AI issues (deformed fingers, unrealistic nails). "
            f"Add: perfect realistic fingers, flawless nail art, professional photography. "
            f"Original: {original_prompt}. "
            f"Return ONLY improved prompt, max 80 words, English. No quotes."
        )}],
        max_tokens=150, temperature=0.5,
    )
    return resp.choices[0].message.content.strip()

# ── image gen ─────────────────────────────────────────────────────────────────
def gen_gptimage2(prompt: str) -> bytes:
    if not OPENAI_CLIENT:
        raise Exception("Chưa có OpenAI API key!")
    resp = OPENAI_CLIENT.images.generate(
        model="gpt-image-1",
        prompt=prompt + ", perfect fingers, realistic hands, professional nail photography",
        size="1024x1024",
        quality="medium",
        n=1,
    )
    # gpt-image-1 trả về base64
    img_data = resp.data[0]
    if hasattr(img_data, 'b64_json') and img_data.b64_json:
        return base64.b64decode(img_data.b64_json)
    elif hasattr(img_data, 'url') and img_data.url:
        r = httpx.get(img_data.url)
        return r.content
    raise Exception("Không lấy được ảnh từ GPT Image 2")

def gen_flux(prompt: str) -> bytes:
    import time
    API_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-schnell"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": prompt + ", perfect fingers, realistic hands, no deformity"}
    for attempt in range(3):
        r = requests.post(API_URL, headers=headers, json=payload, timeout=120)
        if r.status_code == 200:
            return r.content
        log.warning(f"FLUX attempt {attempt+1}: {r.status_code}")
        time.sleep(15)
    raise Exception(f"FLUX error: {r.status_code}")

def gen_image(prompt: str, model: str) -> bytes:
    if model == "gptimage2":
        return gen_gptimage2(prompt)
    return gen_flux(prompt)

async def get_photo_bytes(photo, ctx) -> bytes:
    file = await ctx.bot.get_file(photo[-1].file_id)
    async with httpx.AsyncClient() as c:
        r = await c.get(file.file_path)
    return r.content

# ── keyboards ─────────────────────────────────────────────────────────────────
def start_kb(model: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📸 Gửi ảnh nail mẫu",             callback_data="flow_photo")],
        [InlineKeyboardButton("✍️ Tạo từ lựa chọn",              callback_data="flow_text")],
        [InlineKeyboardButton(f"⚙️ Model: {model_label(model)}", callback_data="choose_model")],
    ])

MODEL_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("⭐ GPT Image 2 — Đẹp nhất, ~10s",    callback_data="set_gptimage2")],
    [InlineKeyboardButton("🆓 FLUX.1 — Miễn phí, ~60s",         callback_data="set_flux")],
    [InlineKeyboardButton("↩️ Quay lại",                         callback_data="menu_main")],
])

def prompt_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Gen ảnh ngay!",     callback_data="prompt_go")],
        [InlineKeyboardButton("✏️ Chỉnh sửa prompt", callback_data="prompt_edit")],
        [InlineKeyboardButton("🔄 Viết lại prompt",   callback_data="prompt_regen")],
        [InlineKeyboardButton("🏠 Huỷ",               callback_data="new")],
    ])

STEP1_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🎨 Chọn tông màu",        callback_data="tab_color")],
    [InlineKeyboardButton("🎉 Chọn theo ngày lễ Mỹ", callback_data="tab_holiday")],
    [InlineKeyboardButton("🏠 Menu chính",            callback_data="menu_main")],
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
        [InlineKeyboardButton("✅ Tạo ảnh ngay!",   callback_data="confirm_gen")],
        [InlineKeyboardButton("↩️ Quay lại",         callback_data="back_step3")],
        [InlineKeyboardButton("🔁 Chọn lại từ đầu", callback_data="new")],
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

# ── show prompt preview ───────────────────────────────────────────────────────
async def show_prompt_preview(chat_id, prompt: str, mdl: str, ctx, uid: int):
    sess(uid)["pending_prompt"] = prompt
    sess(uid)["editing_prompt"] = False
    await ctx.bot.send_message(
        chat_id=chat_id,
        text=(
            f"📝 *Prompt GLM-4 đã viết:*\n\n"
            f"`{prompt}`\n\n"
            f"🤖 Gen bằng: *{model_label(mdl)}*\n\n"
            f"Bạn muốn làm gì?"
        ),
        parse_mode="Markdown",
        reply_markup=prompt_confirm_kb(),
    )

# ── show steps ────────────────────────────────────────────────────────────────
async def show_menu(q, uid: int):
    await q.edit_message_text(
        "💅 Bạn muốn tạo mẫu nail theo cách nào?",
        reply_markup=start_kb(sess(uid)["model"]),
    )

async def show_step1(q):
    await q.edit_message_text(progress(1) + "Bạn muốn chọn theo:", reply_markup=STEP1_KB)

async def show_step2(q, s):
    theme_short = s["theme"].split(",")[0] if s["theme"] else ""
    await q.edit_message_text(
        progress(2) + f"Đã chọn: *{theme_short}* ✅\n\nHình dạng móng?",
        parse_mode="Markdown", reply_markup=shape_kb(),
    )

async def show_step3(q, s):
    await q.edit_message_text(
        progress(3) + f"Hình: *{s['shape']}* ✅\n\nPhong cách nail?",
        parse_mode="Markdown", reply_markup=style_kb(),
    )

async def show_step4(q, s):
    await q.edit_message_text(
        progress(5) +
        f"📋 *Tóm tắt:*\n\n"
        f"🎨 Chủ đề: *{s.get('theme','').split(',')[0]}*\n"
        f"💅 Hình móng: *{s.get('shape','')}*\n"
        f"✨ Phong cách: *{s.get('style','')}*\n"
        f"🤖 Model: *{model_label(s.get('model','gptimage2'))}*\n\n"
        "Tạo ảnh nail ngay không?",
        parse_mode="Markdown", reply_markup=confirm_kb(),
    )

# ── handlers ──────────────────────────────────────────────────────────────────
async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    name = update.effective_user.first_name or "bạn"
    reset(uid)
    await update.message.reply_text(
        f"Xin chào *{name}*! 💅\n\n"
        "Chào mừng bạn đến với *Nail Bot*!\n"
        "Bạn muốn tạo mẫu nail theo cách nào?",
        parse_mode="Markdown",
        reply_markup=start_kb(sess(uid)["model"]),
    )

async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    s   = sess(uid)
    mdl = s.get("model", "gptimage2")
    msg = await update.message.reply_text("🔍 GLM-4 đang phân tích ảnh...")
    try:
        img_bytes = await get_photo_bytes(update.message.photo, ctx)
        prompt    = await asyncio.to_thread(glm_analyze_image, img_bytes)
        await msg.delete()
        await show_prompt_preview(update.effective_chat.id, prompt, mdl, ctx, uid)
    except Exception as e:
        log.exception(e)
        await msg.edit_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid  = update.effective_user.id
    text = update.message.text.strip()
    if text.startswith("/"):
        return
    s   = sess(uid)
    mdl = s.get("model", "gptimage2")

    if s.get("editing_prompt"):
        s["pending_prompt"] = text
        s["editing_prompt"] = False
        await update.message.reply_text(
            f"📝 *Prompt mới:*\n\n`{text}`\n\n🤖 Gen bằng: *{model_label(mdl)}*\n\nXác nhận?",
            parse_mode="Markdown", reply_markup=prompt_confirm_kb(),
        )
        return

    if s["step"] > 0:
        await update.message.reply_text("Bạn hãy chọn một trong các nút bên trên nhé 👆")
        return

    msg = await update.message.reply_text("✨ GLM-4 đang viết prompt...")
    try:
        prompt = await asyncio.to_thread(glm_write_prompt, text)
        await msg.delete()
        await show_prompt_preview(update.effective_chat.id, prompt, mdl, ctx, uid)
    except Exception as e:
        log.exception(e)
        await msg.edit_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

async def handle_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query
    uid = q.from_user.id
    d   = q.data
    await q.answer()
    s   = sess(uid)
    mdl = s.get("model", "gptimage2")

    if d in ("menu_main", "new"):
        reset(uid)
        await show_menu(q, uid)

    elif d == "choose_model":
        await q.edit_message_text("🤖 Chọn model gen ảnh:", reply_markup=MODEL_KB)

    elif d == "set_gptimage2":
        if not OPENAI_CLIENT:
            await q.answer("⚠️ Chưa có OpenAI API key!", show_alert=True)
            return
        s["model"] = "gptimage2"
        await q.edit_message_text(
            "✅ Đã chọn *GPT Image 2*!\n\nBạn muốn tạo mẫu nail theo cách nào?",
            parse_mode="Markdown", reply_markup=start_kb("gptimage2"),
        )

    elif d == "set_flux":
        s["model"] = "flux"
        await q.edit_message_text(
            "✅ Đã chọn *FLUX.1* — miễn phí!\n\nBạn muốn tạo mẫu nail theo cách nào?",
            parse_mode="Markdown", reply_markup=start_kb("flux"),
        )

    elif d == "flow_photo":
        await q.edit_message_text(
            "📸 Gửi ảnh nail bạn thích vào đây!\n"
            f"_GLM-4 phân tích → {model_label(mdl)} gen ảnh_ 🎨",
            parse_mode="Markdown",
        )

    elif d == "flow_text":
        s["step"] = 1
        await show_step1(q)

    elif d == "tab_color":
        await q.edit_message_text(progress(1) + "Chọn tông màu 🎨", reply_markup=COLOR_KB)

    elif d == "tab_holiday":
        await q.edit_message_text(progress(1) + "Chọn ngày lễ Mỹ 🎉", reply_markup=holiday_kb())

    elif d == "back_step1":
        s["theme"] = None; s["step"] = 1
        await show_step1(q)

    elif d in COLOR_MAP:
        s["theme"] = COLOR_MAP[d]; s["step"] = 2
        await show_step2(q, s)

    elif d.startswith("hol_"):
        key = d[4:]
        if key in HOLIDAYS:
            label, desc = HOLIDAYS[key]
            s["theme"] = f"{label}, {desc}"; s["step"] = 2
            await show_step2(q, s)

    elif d == "back_step2":
        s["shape"] = None; s["step"] = 1
        await show_step1(q)

    elif d in SHAPE_MAP:
        s["shape"] = SHAPE_MAP[d]; s["step"] = 3
        await show_step3(q, s)

    elif d == "back_step3":
        s["style"] = None; s["step"] = 2
        await show_step2(q, s)

    elif d in STYLE_MAP:
        s["style"] = STYLE_MAP[d]; s["step"] = 4
        await show_step4(q, s)

    elif d == "confirm_gen":
        await q.edit_message_text("⏳ GLM-4 đang viết prompt...")
        try:
            prompt = await asyncio.to_thread(
                glm_write_prompt,
                s.get("theme", "elegant nail art"),
                s.get("shape", "almond"),
                s.get("style", "minimalist"),
            )
            s["step"] = 0; s["pending_prompt"] = prompt
            await q.edit_message_text(
                f"📝 *Prompt GLM-4 đã viết:*\n\n`{prompt}`\n\n🤖 Gen bằng: *{model_label(mdl)}*\n\nBạn muốn làm gì?",
                parse_mode="Markdown", reply_markup=prompt_confirm_kb(),
            )
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "prompt_go":
        prompt = s.get("pending_prompt")
        if not prompt:
            await show_menu(q, uid); return
        await q.edit_message_text(f"🎨 Đang gen ảnh bằng {model_label(mdl)}, chờ nhé...")
        try:
            img = await asyncio.to_thread(gen_image, prompt, mdl)
            s["last_prompt"] = prompt; s["pending_prompt"] = None
            caption = f"✨ Đây là ảnh nail!\n🤖 {model_label(mdl)}\n\n📝 *Prompt:*\n`{prompt[:200]}`"
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=io.BytesIO(img),
                caption=caption, parse_mode="Markdown",
                reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "prompt_edit":
        s["editing_prompt"] = True
        await q.edit_message_text(
            f"✏️ *Chỉnh sửa prompt:*\n\nHiện tại:\n`{s.get('pending_prompt','')}`\n\n"
            f"Nhắn prompt mới (tiếng Anh để kết quả tốt nhất):",
            parse_mode="Markdown",
        )

    elif d == "prompt_regen":
        await q.edit_message_text("🔄 GLM-4 đang viết lại prompt...")
        try:
            new_prompt = await asyncio.to_thread(
                glm_write_prompt,
                s.get("theme", "elegant nail art"),
                s.get("shape", "almond"),
                s.get("style", "minimalist"),
            )
            s["pending_prompt"] = new_prompt
            await q.edit_message_text(
                f"📝 *Prompt mới:*\n\n`{new_prompt}`\n\n🤖 Gen bằng: *{model_label(mdl)}*\n\nBạn muốn làm gì?",
                parse_mode="Markdown", reply_markup=prompt_confirm_kb(),
            )
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "remix":
        last = s.get("last_prompt")
        if not last:
            await show_menu(q, uid); return
        await q.edit_message_text(f"🔄 Đang tạo biến tấu bằng {model_label(mdl)}...")
        try:
            new_prompt = last + ", creative variation, different composition"
            img = await asyncio.to_thread(gen_image, new_prompt, mdl)
            s["last_prompt"] = new_prompt
            caption = f"🔄 Biến tấu mới!\n🤖 {model_label(mdl)}\n\n📝 *Prompt:*\n`{new_prompt[:200]}`"
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id, photo=io.BytesIO(img),
                caption=caption, parse_mode="Markdown", reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "retouch":
        last = s.get("last_prompt")
        if not last:
            await show_menu(q, uid); return
        await q.edit_message_text("✨ GLM-4 đang retouch prompt...")
        try:
            retouched = await asyncio.to_thread(glm_retouch_prompt, last)
            s["pending_prompt"] = retouched
            await q.edit_message_text(
                f"📝 *Prompt sau retouch:*\n\n`{retouched}`\n\n🤖 Gen bằng: *{model_label(mdl)}*\n\nBạn muốn làm gì?",
                parse_mode="Markdown", reply_markup=prompt_confirm_kb(),
            )
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "tweak":
        await q.edit_message_text("🎨 Chọn màu hoặc hình dạng móng:", reply_markup=TWEAK_KB)

    elif d in TWEAK_MAP:
        tweak_val = TWEAK_MAP[d]
        await q.edit_message_text(f"🎨 GLM-4 đang viết prompt cho *{tweak_val}*...", parse_mode="Markdown")
        try:
            prompt = await asyncio.to_thread(glm_write_prompt, tweak_val)
            s["pending_prompt"] = prompt
            await q.edit_message_text(
                f"📝 *Prompt cho {tweak_val}:*\n\n`{prompt}`\n\n🤖 Gen bằng: *{model_label(mdl)}*\n\nBạn muốn làm gì?",
                parse_mode="Markdown", reply_markup=prompt_confirm_kb(),
            )
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "back_result":
        await q.edit_message_text("Chọn bước tiếp theo:", reply_markup=RESULT_KB)

def main():
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    app.add_handler(CallbackQueryHandler(handle_callback))
    log.info("🚀 Nail Bot (GLM-4 + GPT Image 2) started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
