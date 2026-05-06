import os
import io
import logging
import asyncio
import httpx
import base64
import json
import re
from huggingface_hub import InferenceClient
from groq import Groq
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

TOKEN      = os.environ["TELEGRAM_BOT_TOKEN"]
HF_TOKEN   = os.environ.get("HF_TOKEN", "")
GROQ_KEY   = os.environ.get("GROQ_API_KEY", "")
OPENAI_KEY = os.environ.get("OPENAI_API_KEY", "")

HF_CLIENT   = InferenceClient(provider="hf-inference", api_key=HF_TOKEN)
GROQ_CLIENT = Groq(api_key=GROQ_KEY) if GROQ_KEY else None
OPENAI      = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None

# ── Pinterest scraper ─────────────────────────────────────────────────────────
PINTEREST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.pinterest.com/",
}

def search_pinterest_images(query: str, count: int = 5) -> list[str]:
    """Scrape Pinterest search results, return list of image URLs"""
    search_query = f"{query} nail art"
    url = f"https://www.pinterest.com/search/pins/?q={search_query.replace(' ', '%20')}&rs=typed"
    try:
        r = httpx.get(url, headers=PINTEREST_HEADERS, timeout=15, follow_redirects=True)
        # tìm image URLs từ HTML
        img_urls = re.findall(r'https://i\.pinimg\.com/[^"\'\\s]+\.jpg', r.text)
        # lọc ảnh 564x (medium size) hoặc 736x (large)
        filtered = [u for u in img_urls if "/564x/" in u or "/736x/" in u]
        # dedup
        seen = set()
        unique = []
        for u in filtered:
            if u not in seen:
                seen.add(u)
                unique.append(u)
        return unique[:count]
    except Exception as e:
        log.warning(f"Pinterest scrape failed: {e}")
        return []

def download_image(url: str) -> bytes | None:
    try:
        r = httpx.get(url, headers=PINTEREST_HEADERS, timeout=10)
        if r.status_code == 200:
            return r.content
        return None
    except Exception:
        return None

def groq_analyze_pinterest_images(image_bytes_list: list[bytes], theme: str) -> str:
    """Dùng Groq Vision phân tích nhiều ảnh Pinterest → tổng hợp prompt"""
    if not GROQ_CLIENT or not image_bytes_list:
        return f"beautiful woman's hand with {theme} nail art, gel nails, elegant pose, studio lighting, white background, high quality, 4k"

    # phân tích từng ảnh
    analyses = []
    for i, img_bytes in enumerate(image_bytes_list[:3]):  # max 3 ảnh
        try:
            b64 = base64.b64encode(img_bytes).decode()
            resp = GROQ_CLIENT.chat.completions.create(
                model="meta-llama/llama-4-scout-17b-16e-instruct",
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                        {"type": "text", "text": (
                            "Analyze this nail art image briefly. Describe: "
                            "1) Colors and color combinations "
                            "2) Nail shape "
                            "3) Decorative elements/patterns "
                            "4) Finish type (matte/glossy/chrome) "
                            "Keep it under 40 words."
                        )}
                    ]
                }],
                max_tokens=80,
            )
            analyses.append(resp.choices[0].message.content.strip())
        except Exception as e:
            log.warning(f"Image {i} analysis failed: {e}")
            continue

    if not analyses:
        return f"beautiful woman's hand with {theme} nail art, gel nails, elegant studio lighting"

    # tổng hợp tất cả phân tích → viết 1 prompt đẹp
    combined = "\n".join([f"- {a}" for a in analyses])
    resp = GROQ_CLIENT.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{
            "role": "user",
            "content": (
                f"Based on these Pinterest nail art analyses for theme '{theme}':\n{combined}\n\n"
                f"Write ONE detailed image generation prompt combining the best elements. "
                f"Must include: beautiful woman's hand, gel nails, elegant pose, "
                f"studio lighting, white background, photorealistic, high quality, 4k. "
                f"Max 70 words, English only, no quotes, no explanation."
            )
        }],
        max_tokens=150,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()

# ── Pinterest theme map ───────────────────────────────────────────────────────
PINTEREST_THEMES = {
    "pt_cherry":    "🌸 Cherry Blossom",
    "pt_marble":    "🌀 Marble",
    "pt_french":    "🤍 French Tip",
    "pt_glitter":   "✨ Glitter",
    "pt_ombre":     "🎨 Ombre",
    "pt_floral":    "🌺 Floral",
    "pt_minimal":   "🕊 Minimalist",
    "pt_chrome":    "💿 Chrome",
    "pt_3d":        "🌟 3D Nail",
    "pt_halloween": "🎃 Halloween",
    "pt_xmas":      "🎄 Christmas",
    "pt_valentine": "💝 Valentine",
    "pt_summer":    "☀️ Summer",
    "pt_pastel":    "🌷 Pastel",
    "pt_korean":    "🇰🇷 Korean Style",
    "pt_vintage":   "🕰 Vintage",
}

def pinterest_theme_kb() -> InlineKeyboardMarkup:
    rows = []
    keys = list(PINTEREST_THEMES.keys())
    for i in range(0, len(keys), 2):
        row = []
        for k in keys[i:i+2]:
            row.append(InlineKeyboardButton(PINTEREST_THEMES[k], callback_data=k))
        rows.append(row)
    rows.append([InlineKeyboardButton("↩️ Quay lại", callback_data="menu_main")])
    return InlineKeyboardMarkup(rows)

# ── holidays ──────────────────────────────────────────────────────────────────
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
            "last_prompt": None, "model": "flux",
            "pending_prompt": None, "editing_prompt": False,
        }
    return SESSIONS[uid]

def reset(uid: int):
    model = sess(uid).get("model", "flux")
    SESSIONS[uid] = {
        "step": 0, "theme": None, "shape": None, "style": None,
        "last_prompt": None, "model": model,
        "pending_prompt": None, "editing_prompt": False,
    }

def progress(step: int) -> str:
    return "".join(["▓" if i < step else "░" for i in range(5)]) + f" Bước {step}/5\n\n"

def model_label(model: str) -> str:
    return "⭐ DALL-E 3" if model == "dalle" else "🆓 FLUX.1"

# ── prompt confirm keyboard ───────────────────────────────────────────────────
def prompt_confirm_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Gen ảnh ngay!",     callback_data="prompt_go")],
        [InlineKeyboardButton("✏️ Chỉnh sửa prompt", callback_data="prompt_edit")],
        [InlineKeyboardButton("🔄 Viết lại prompt",   callback_data="prompt_regen")],
        [InlineKeyboardButton("🏠 Huỷ",               callback_data="new")],
    ])

# ── main keyboards ────────────────────────────────────────────────────────────
def start_kb(model: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📌 Tìm mẫu từ Pinterest",         callback_data="flow_pinterest")],
        [InlineKeyboardButton("📸 Gửi ảnh nail mẫu",             callback_data="flow_photo")],
        [InlineKeyboardButton("✍️ Tạo từ lựa chọn",              callback_data="flow_text")],
        [InlineKeyboardButton(f"⚙️ Model: {model_label(model)}", callback_data="choose_model")],
    ])

MODEL_KB = InlineKeyboardMarkup([
    [InlineKeyboardButton("🆓 FLUX.1 — Miễn phí, ~30s",           callback_data="set_flux")],
    [InlineKeyboardButton("⭐ DALL-E 3 — Trả phí, ~10s, đẹp hơn", callback_data="set_dalle")],
    [InlineKeyboardButton("↩️ Quay lại",                           callback_data="menu_main")],
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

# ── Groq helpers ──────────────────────────────────────────────────────────────
def groq_write_prompt(theme: str, shape: str, style: str) -> str:
    if not GROQ_CLIENT:
        return (
            f"beautiful woman's hand with {style} nail art, "
            f"{theme} color, {shape} shaped nails, gel nails, "
            f"elegant hand pose, soft studio lighting, white background, high quality, 4k"
        )
    resp = GROQ_CLIENT.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[{"role": "user", "content": (
            f"Write a detailed image generation prompt for nail art photography. "
            f"Theme/color: {theme}, nail shape: {shape}, style: {style}. "
            f"Must include: beautiful woman's hand, gel nails, elegant pose, "
            f"studio lighting, white background, photorealistic, high quality. "
            f"Return ONLY the prompt, max 70 words, English. No quotes."
        )}],
        max_tokens=150, temperature=0.7,
    )
    return resp.choices[0].message.content.strip()

def groq_analyze_image(image_bytes: bytes) -> str:
    if not GROQ_CLIENT:
        return "nail art design, beautiful woman's hand, gel nails, studio lighting"
    b64 = base64.b64encode(image_bytes).decode()
    resp = GROQ_CLIENT.chat.completions.create(
        model="meta-llama/llama-4-scout-17b-16e-instruct",
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

def groq_retouch_prompt(original_prompt: str) -> str:
    if not GROQ_CLIENT:
        return original_prompt + ", perfect nails, flawless nail art, no distortion, realistic fingers"
    resp = GROQ_CLIENT.chat.completions.create(
        model="llama-3.3-70b-versatile",
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
def gen_flux(prompt: str) -> bytes:
    import requests, time
    API_URL = "https://api-inference.huggingface.co/models/black-forest-labs/FLUX.1-dev"
    headers = {"Authorization": f"Bearer {HF_TOKEN}"}
    payload = {"inputs": prompt + ", perfect fingers, realistic hands, no deformity"}
    for attempt in range(3):
        r = requests.post(API_URL, headers=headers, json=payload, timeout=120)
        if r.status_code == 200:
            return r.content
        log.warning(f"FLUX attempt {attempt+1}: {r.status_code}")
        time.sleep(15)
    raise Exception(f"FLUX error after 3 attempts: {r.status_code}")

def gen_dalle(prompt: str) -> bytes:
    if not OPENAI:
        raise Exception("Chưa có OpenAI API key!")
    resp = OPENAI.images.generate(
        model="dall-e-3",
        prompt=prompt + ", perfect fingers, realistic hands, professional nail photography",
        size="1024x1024", quality="standard", n=1,
    )
    r = httpx.get(resp.data[0].url)
    return r.content

def gen_image(prompt: str, model: str) -> bytes:
    return gen_dalle(prompt) if model == "dalle" else gen_flux(prompt)

async def get_photo_bytes(photo, ctx) -> bytes:
    file = await ctx.bot.get_file(photo[-1].file_id)
    async with httpx.AsyncClient() as c:
        r = await c.get(file.file_path)
    return r.content

# ── show prompt preview ───────────────────────────────────────────────────────
async def show_prompt_preview(chat_id, prompt: str, mdl: str, ctx, uid: int, pinterest_imgs: list = None):
    sess(uid)["pending_prompt"] = prompt
    sess(uid)["editing_prompt"] = False

    # gửi ảnh Pinterest tham khảo trước (nếu có)
    if pinterest_imgs:
        media_sent = 0
        for img_url in pinterest_imgs[:3]:
            try:
                await ctx.bot.send_photo(
                    chat_id=chat_id,
                    photo=img_url,
                    caption=f"📌 Ảnh tham khảo từ Pinterest" if media_sent == 0 else None,
                )
                media_sent += 1
                await asyncio.sleep(0.3)
            except Exception:
                continue

    await ctx.bot.send_message(
        chat_id=chat_id,
        text=(
            f"📝 *Prompt Groq tổng hợp từ Pinterest:*\n\n"
            f"`{prompt}`\n\n"
            f"🤖 Gen bằng: *{model_label(mdl)}*\n\n"
            f"Bạn muốn làm gì?"
        ),
        parse_mode="Markdown",
        reply_markup=prompt_confirm_kb(),
    )

# ── show steps ────────────────────────────────────────────────────────────────
async def show_menu(q, uid: int):
    s = sess(uid)
    await q.edit_message_text(
        "💅 Bạn muốn tạo mẫu nail theo cách nào?",
        reply_markup=start_kb(s["model"]),
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
        f"🤖 Model: *{model_label(s.get('model','flux'))}*\n\n"
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
    mdl = s.get("model", "flux")
    msg = await update.message.reply_text("🔍 Groq đang phân tích ảnh...")
    try:
        img_bytes = await get_photo_bytes(update.message.photo, ctx)
        prompt    = await asyncio.to_thread(groq_analyze_image, img_bytes)
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
    s = sess(uid)

    # đang edit prompt
    if s.get("editing_prompt"):
        s["pending_prompt"] = text
        s["editing_prompt"] = False
        mdl = s.get("model", "flux")
        await update.message.reply_text(
            f"📝 *Prompt mới:*\n\n`{text}`\n\n🤖 Gen bằng: *{model_label(mdl)}*\n\nXác nhận?",
            parse_mode="Markdown", reply_markup=prompt_confirm_kb(),
        )
        return

    if s["step"] > 0:
        await update.message.reply_text("Bạn hãy chọn một trong các nút bên trên nhé 👆")
        return

    mdl = s.get("model", "flux")
    msg = await update.message.reply_text("✨ Groq đang viết prompt...")
    try:
        prompt = await asyncio.to_thread(groq_write_prompt, text, "almond", "elegant")
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
    mdl = s.get("model", "flux")

    # ── Pinterest flow ────────────────────────────────────────────────────────
    if d == "flow_pinterest":
        await q.edit_message_text(
            "📌 Chọn chủ đề nail để tìm trên Pinterest:",
            reply_markup=pinterest_theme_kb(),
        )

    elif d in PINTEREST_THEMES:
        theme_label = PINTEREST_THEMES[d]
        theme_key   = theme_label.split(" ", 1)[1]  # bỏ emoji
        await q.edit_message_text(
            f"🔍 Đang tìm ảnh *{theme_label}* trên Pinterest...",
            parse_mode="Markdown",
        )
        try:
            # scrape Pinterest
            img_urls = await asyncio.to_thread(search_pinterest_images, theme_key, 5)
            if not img_urls:
                await q.edit_message_text(
                    f"❌ Không tìm thấy ảnh trên Pinterest cho *{theme_label}*.\n"
                    f"Thử chủ đề khác nhé!",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[
                        InlineKeyboardButton("↩️ Chọn lại", callback_data="flow_pinterest")
                    ]]),
                )
                return

            await q.edit_message_text(
                f"📌 Tìm thấy {len(img_urls)} ảnh!\n🤖 Groq đang phân tích..."
            )

            # download và phân tích
            img_bytes_list = []
            for url in img_urls[:3]:
                b = await asyncio.to_thread(download_image, url)
                if b:
                    img_bytes_list.append(b)

            prompt = await asyncio.to_thread(
                groq_analyze_pinterest_images, img_bytes_list, theme_key
            )
            s["theme"] = theme_key

            await q.message.delete()
            await show_prompt_preview(
                q.message.chat_id, prompt, mdl, ctx, uid,
                pinterest_imgs=img_urls[:3]
            )

        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    # ── prompt actions ────────────────────────────────────────────────────────
    elif d == "prompt_go":
        prompt = s.get("pending_prompt")
        if not prompt:
            await show_menu(q, uid)
            return
        await q.edit_message_text(f"🎨 Đang gen ảnh bằng {model_label(mdl)}, chờ ~30 giây...")
        try:
            img = await asyncio.to_thread(gen_image, prompt, mdl)
            s["last_prompt"]    = prompt
            s["pending_prompt"] = None
            caption = f"✨ Đây là ảnh nail!\n🤖 {model_label(mdl)}\n\n📝 *Prompt:*\n`{prompt[:200]}`"
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=io.BytesIO(img),
                caption=caption,
                parse_mode="Markdown",
                reply_markup=RESULT_KB,
            )
            await q.message.delete()
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "prompt_edit":
        s["editing_prompt"] = True
        await q.edit_message_text(
            f"✏️ *Chỉnh sửa prompt:*\n\nPrompt hiện tại:\n`{s.get('pending_prompt','')}`\n\n"
            f"Nhắn prompt mới (tiếng Anh để kết quả tốt nhất):",
            parse_mode="Markdown",
        )

    elif d == "prompt_regen":
        s_theme = s.get("theme", "elegant nail art")
        s_shape = s.get("shape", "almond")
        s_style = s.get("style", "minimalist")
        await q.edit_message_text("🔄 Groq đang viết lại prompt mới...")
        try:
            new_prompt = await asyncio.to_thread(groq_write_prompt, s_theme, s_shape, s_style)
            s["pending_prompt"] = new_prompt
            await q.edit_message_text(
                f"📝 *Prompt mới:*\n\n`{new_prompt}`\n\n🤖 Gen bằng: *{model_label(mdl)}*\n\nBạn muốn làm gì?",
                parse_mode="Markdown", reply_markup=prompt_confirm_kb(),
            )
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    # ── menu ──────────────────────────────────────────────────────────────────
    elif d in ("menu_main", "new"):
        reset(uid)
        await show_menu(q, uid)

    elif d == "choose_model":
        await q.edit_message_text("🤖 Chọn model AI:", reply_markup=MODEL_KB)

    elif d == "set_flux":
        s["model"] = "flux"
        await q.edit_message_text(
            "✅ Đã chọn *FLUX.1* — miễn phí!\n\nBạn muốn tạo mẫu nail theo cách nào?",
            parse_mode="Markdown", reply_markup=start_kb("flux"),
        )

    elif d == "set_dalle":
        if not OPENAI:
            await q.answer("⚠️ Chưa có OpenAI API key!", show_alert=True)
            return
        s["model"] = "dalle"
        await q.edit_message_text(
            "✅ Đã chọn *DALL-E 3* — chất lượng cao!\n\nBạn muốn tạo mẫu nail theo cách nào?",
            parse_mode="Markdown", reply_markup=start_kb("dalle"),
        )

    elif d == "flow_photo":
        await q.edit_message_text(
            "📸 Gửi ảnh nail bạn thích vào đây!\n"
            f"_Groq sẽ phân tích → {model_label(mdl)} gen ảnh_ 🎨",
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
        await q.edit_message_text("⏳ Groq đang viết prompt...")
        try:
            prompt = await asyncio.to_thread(
                groq_write_prompt,
                s.get("theme", "elegant nail art"),
                s.get("shape", "almond"),
                s.get("style", "minimalist"),
            )
            s["step"] = 0
            s["pending_prompt"] = prompt
            await q.edit_message_text(
                f"📝 *Prompt Groq đã viết:*\n\n`{prompt}`\n\n🤖 Gen bằng: *{model_label(mdl)}*\n\nBạn muốn làm gì?",
                parse_mode="Markdown", reply_markup=prompt_confirm_kb(),
            )
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "remix":
        last = s.get("last_prompt")
        if not last:
            await show_menu(q, uid)
            return
        await q.edit_message_text(f"🔄 Đang tạo biến tấu bằng {model_label(mdl)}...")
        try:
            new_prompt = last + ", creative variation, different composition"
            img = await asyncio.to_thread(gen_image, new_prompt, mdl)
            s["last_prompt"] = new_prompt
            caption = f"🔄 Biến tấu mới!\n🤖 {model_label(mdl)}\n\n📝 *Prompt:*\n`{new_prompt[:200]}`"
            await ctx.bot.send_photo(
                chat_id=q.message.chat_id,
                photo=io.BytesIO(img),
                caption=caption,
                parse_mode="Markdown",
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
        await q.edit_message_text("✨ Groq đang retouch prompt...")
        try:
            retouched = await asyncio.to_thread(groq_retouch_prompt, last)
            s["pending_prompt"] = retouched
            await q.edit_message_text(
                f"📝 *Prompt sau retouch:*\n\n`{retouched}`\n\n🤖 Gen bằng: *{model_label(mdl)}*\n\nBạn muốn làm gì?",
                parse_mode="Markdown", reply_markup=prompt_confirm_kb(),
            )
        except Exception as e:
            log.exception(e)
            await q.edit_message_text(f"❌ Lỗi: {str(e)[:120]}\n\nThử lại nhé!")

    elif d == "tweak":
        await q.edit_message_text("🎨 Chọn màu hoặc hình dạng móng muốn thay:", reply_markup=TWEAK_KB)

    elif d in TWEAK_MAP:
        tweak_val = TWEAK_MAP[d]
        await q.edit_message_text(f"🎨 Groq đang viết prompt cho *{tweak_val}*...", parse_mode="Markdown")
        try:
            prompt = await asyncio.to_thread(groq_write_prompt, tweak_val, "almond", "elegant")
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
    log.info("🚀 Nail Bot (Pinterest + Groq + FLUX) started...")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
