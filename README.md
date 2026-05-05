# 💅 Nail Telegram Bot

Bot Telegram tạo ảnh nail bằng AI — chạy miễn phí trên GitHub Actions.

**GPT-4o Vision** phân tích ảnh + **DALL-E 3** tạo ảnh thật.

---

## Tính năng

| | |
|---|---|
| 📸 Gửi ảnh | GPT-4o đọc ảnh → tạo mẫu tương tự |
| ✍️ Mô tả 6 bước | Tông màu/Ngày lễ → Dịp → Hình móng → Phong cách → Kích thước → Gen |
| 🔄 Biến tấu | Gen lại ảnh mới cùng phong cách |
| 🎨 Đổi màu/hình | Thay đổi và gen lại ngay |
| 📐 3 kích thước | 1024×1024 / 1792×1024 / 1024×1792 |

---

## Setup (5 phút)

### 1. Fork repo
Nhấn **Fork** góc trên phải.

### 2. Tạo Telegram Bot
Nhắn `@BotFather` → `/newbot` → lấy token.

### 3. Lấy OpenAI API Key
Vào [platform.openai.com](https://platform.openai.com) → API Keys → Create.  
Nạp tối thiểu **$5** vào Billing. Mỗi ảnh tốn ~$0.04–0.06.

### 4. Thêm Secrets vào GitHub
**Settings → Secrets and variables → Actions → New repository secret**

| Secret | Giá trị |
|--------|---------|
| `TELEGRAM_BOT_TOKEN` | Token từ BotFather |
| `OPENAI_API_KEY` | Key từ OpenAI |

### 5. Bật Actions
Tab **Actions** → **Enable workflows** → **Run workflow** để test ngay.

### 6. Test
Nhắn `/start` cho bot — bot trả lời trong vòng 5 phút!

---

## Chi phí ước tính

| Dịch vụ | Giá/lần |
|---------|---------|
| GPT-4o Vision (phân tích ảnh) | ~$0.01 |
| DALL-E 3 (tạo ảnh 1024×1024) | ~$0.04 |
| DALL-E 3 (tạo ảnh 1792×1024 hoặc 1024×1792) | ~$0.08 |

$5 dùng được khoảng **50–100 lần** tạo ảnh.

---

## Tuỳ chỉnh

**Đổi tên bot:** Tìm `Nail Bot` trong `bot.py` → thay tên tiệm.

**Thêm ngày lễ:** Tìm dict `HOLIDAYS` trong `bot.py` → thêm dòng mới.

**Thêm phong cách:** Tìm dict `STYLES` → thêm tùy chọn.
