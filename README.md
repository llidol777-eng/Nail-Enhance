# 💅 Nail Telegram Bot

Bot Telegram tạo ảnh nail bằng **GPT-4o Vision + DALL-E 3**.  
Chạy miễn phí trên **GitHub Actions** — không cần server.

---

## Tính năng

| | Tính năng |
|---|---|
| 📸 | Gửi ảnh nail → GPT-4o phân tích → DALL-E 3 tạo ảnh tương tự |
| ✍️ | Chọn 5 bước: Tông màu / Ngày lễ Mỹ → Hình móng → Phong cách → Gen ảnh |
| 🎉 | 14 ngày lễ Mỹ: Valentine's, Easter, Halloween, Christmas... |
| 🔄 | Nút Biến tấu khác — gen lại ảnh mới |
| 🎨 | Nút Đổi màu / hình móng — chọn và gen lại |

---

## Setup (5 phút)

### Bước 1 — Fork repo
Nhấn **Fork** góc trên phải trang GitHub này.

### Bước 2 — Tạo Telegram Bot
1. Nhắn `@BotFather` trên Telegram
2. Gõ `/newbot` → đặt tên → copy **token** (`123456:ABC-xxx`)

### Bước 3 — Lấy OpenAI API Key
1. Vào [platform.openai.com](https://platform.openai.com)
2. **API Keys** → **Create new secret key** → copy (`sk-proj-...`)
3. **Billing** → nạp tối thiểu $10  
   Chi phí mỗi lần dùng ~$0.08 (GPT-4o phân tích + DALL-E 3 gen ảnh)

### Bước 4 — Thêm Secrets vào GitHub
Repo → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**:

| Tên secret | Giá trị |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token từ BotFather |
| `OPENAI_API_KEY` | Key từ OpenAI |

### Bước 5 — Bật GitHub Actions
1. Tab **Actions** → **Enable workflows**
2. Nhấn **Run workflow** → **Run** để test ngay

### Bước 6 — Test
Nhắn `/start` cho bot trên Telegram!

> ⚠️ Bot chạy mỗi 5 phút nên có thể trả lời chậm tối đa 5 phút.

---

## Tuỳ chỉnh

**Đổi tên bot:** Tìm `Nail Bot` trong `bot.py` → sửa thành tên tiệm bạn.

**Thêm ngày lễ:** Tìm `HOLIDAY_KB` trong `bot.py` → thêm dòng mới theo format:
```python
InlineKeyboardButton("🎆 Tên lễ", callback_data="theme_Tên lễ - mô tả tiếng Anh"),
```

**Đổi chất lượng ảnh:** Tìm `quality="standard"` → đổi thành `quality="hd"` (đẹp hơn, tốn ~$0.12/ảnh).
