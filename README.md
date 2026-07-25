# NEBULA — เว็บแอปวิเคราะห์หุ้นมืออาชีพ 🛰️

เว็บแอปวิเคราะห์หุ้นไทย (.BK) และหุ้นสหรัฐแบบครบวงจร ธีมอวกาศ Neon Blue/Purple
รองรับ Desktop / Tablet / Mobile (Responsive) · Backend Python + Flask · Database SQLite

ข้อมูลหุ้นดึงจาก **Yahoo Finance** (ผ่าน `yfinance`), ข่าวจาก **Google News RSS + Yahoo**,
ปัจจัยมหภาคจาก Yahoo Finance (ทอง น้ำมัน ค่าเงิน บอนด์ ดัชนี)

---

## ✨ ฟีเจอร์หลัก 14 อย่าง

| # | ฟีเจอร์ | อยู่ที่เมนู |
|---|---------|-----------|
| 1 | **Stock Screener** คัดกรองตาม P/E, ROE, D/E, ปันผล | คัดกรอง |
| 2 | **Fundamental** งบ 5 ปี + เปรียบเทียบคู่แข่ง | วิเคราะห์ → พื้นฐาน |
| 3 | **Technical** กราฟ RSI, MACD, Bollinger, MA | วิเคราะห์ → เทคนิคัล |
| 4 | **Sentiment** ข่าว + Fear & Greed Index | วิเคราะห์ → ข่าว / หน้าแรก |
| 5 | **เงินสถาบัน / Insider** ผู้ถือหุ้นสถาบัน, insider trading | วิเคราะห์ → เงินสถาบัน |
| 6 | **ปัจจัยมหภาค** ดอกเบี้ย ทอง น้ำมัน ค่าเงิน | หน้าแรก |
| 7 | **Sector Rotation** เปรียบเทียบกลุ่มอุตสาหกรรม | เครื่องมือ → Sector |
| 8 | **รายงานประจำวัน** หุ้นน่าซื้อ + จุดเข้า/ตัดขาดทุน/เป้า | รายงานวันนี้ |
| 9 | **ติดตามพอร์ต** กำไร/ขาดทุน real-time | พอร์ต |
| 10 | **Backtesting** ทดสอบกลยุทธ์ + win rate | เครื่องมือ → Backtest |
| 11 | **แจ้งเตือน LINE** เมื่อถึงราคา/สัญญาณ | เครื่องมือ → แจ้งเตือน |
| 12 | **AI Advisory** ถามตอบหุ้น อธิบายเหตุผล | AI |
| 13 | **Risk Management** ความเสี่ยงพอร์ต + position sizing | พอร์ต / เครื่องมือ |
| 14 | **คะแนนรวม 0-100** ต่อหุ้น | วิเคราะห์ → ภาพรวม |
| 15 | **ลูกโลกข่าวโลก 3D** ข่าวทั่วโลกจาก GDELT ปักบนลูกโลก | ลูกโลกข่าว |
| 16 | **เครื่องเรียนรู้** หาความสัมพันธ์ ข่าวโลก ↔ ราคาหุ้น | เครื่องเรียนรู้ |

---

## 🌍 ฟีเจอร์ใหม่: ลูกโลกข่าวโลก + เครื่องเรียนรู้

### ลูกโลกข่าวโลก (เมนู "ลูกโลกข่าว")

ดึงข่าวจาก **[GDELT Project](https://www.gdeltproject.org/)** — ฟรี **ไม่ต้องใช้ API key**
มอนิเตอร์ข่าวทั่วโลก **65 ภาษา** อัปเดตทุก 15 นาที

- ลูกโลก 3D หมุนได้ (globe.gl) ปักจุดข่าวตามพิกัดจริง — จุดใหญ่ = ข่าวเยอะ
- กรองได้ 8 ธีม: สงคราม · พลังงาน · เงินเฟ้อ · การค้า · เทคโนโลยี · ตลาดหุ้น · ภัยพิบัติ · ข่าวไทย
- คลิกจุดบนลูกโลกเพื่ออ่านข่าวของพื้นที่นั้น
- แผง **"อุณหภูมิข่าวโลก"** แสดง Tone (ค่าความบวก/ลบของข่าว) เทียบค่าเฉลี่ย 7 วัน

> ถ้าโหลด globe.gl ไม่ได้ (ออฟไลน์) จะแสดงเป็นรายการจุดข่าวแทนโดยอัตโนมัติ

### เครื่องเรียนรู้ (เมนู "เครื่องเรียนรู้")

เฝ้าดู **ข่าวทั่วโลก + ราคาหุ้น + ปัจจัยมหภาค** พร้อมกัน แล้วหาว่าอะไรสัมพันธ์กัน

**วิธีคิด**
- แปลงข่าวเป็น time series รายวัน (Tone) และราคาเป็นผลตอบแทนรายวัน %
- จับคู่ตามวันที่ แล้วหา correlation ที่ **lag** ต่าง ๆ
  - `lag = 0` → ข่าววันนี้สัมพันธ์กับราคาวันนี้ (เกิดพร้อมกัน)
  - `lag = 1+` → **ข่าววันนี้ "นำ" ราคาอีก N วัน** ← อันนี้แหละที่ใช้เทรดได้
- รายงาน `r` (ความแรง), `n` (จำนวนข้อมูล), `hit rate` (% ที่ทายถูก)

**ใช้ได้ตั้งแต่วันแรก** — GDELT ให้ timeline ย้อนหลังได้ถึง 1 ปี และ yfinance ให้ราคาย้อนหลังหลายปี
เครื่องจึงเรียนรู้จากอดีตได้ทันที ไม่ต้องรอสะสมข้อมูลเป็นเดือน

**ยิ่งเก็บยิ่งแม่น** — แอปเก็บ snapshot ของข่าว+ราคาลงตาราง `observations` อัตโนมัติทุกชั่วโมง
คลังข้อมูลจึงโตขึ้นเรื่อย ๆ (กดปุ่ม "เก็บข้อมูลเดี๋ยวนี้" เพื่อเก็บทันทีก็ได้)

```powershell
# ปิดการเก็บอัตโนมัติ / ปรับความถี่
$env:LEARN_AUTO = "0"          # ปิด (ค่าเริ่มต้น = 1)
$env:LEARN_INTERVAL = "3600"   # เก็บทุกกี่วินาที
$env:LEARN_WINDOW_DAYS = "180" # ช่วงข้อมูลที่ใช้วิเคราะห์
$env:LEARN_MIN_SAMPLES = "30"  # n ขั้นต่ำถึงจะเชื่อผล
```

> ⚠️ **ข้อควรระวังทางสถิติ** — correlation ไม่ใช่ causation
> ยิ่งทดสอบหลายคู่ ยิ่งเจอความสัมพันธ์ "บังเอิญ" (multiple comparisons)
> แอปจึงมีเกณฑ์ `n` ขั้นต่ำ + t-stat และแสดงคำเตือนทุกครั้ง — ใช้ประกอบการตัดสินใจเท่านั้น

### Sentiment แม่นขึ้น

`services/sentiment.py` เดิมนับ keyword ในพาดหัวข่าว ตอนนี้ผสม **GDELT Tone** เข้าไปด้วย
(น้ำหนัก GDELT 60% + keyword 40%) ถ้า GDELT ใช้ไม่ได้จะถอยกลับไปใช้ keyword อัตโนมัติ

---

## 🚀 ติดตั้งและรัน (Windows)

ต้องมี **Python 3.10+** ติดตั้งไว้แล้ว

```powershell
# 1) เข้าโฟลเดอร์โปรเจกต์
cd "D:\Claude code Project\stock project"

# 2) (แนะนำ) สร้าง virtual environment
python -m venv venv
.\venv\Scripts\Activate.ps1

# 3) ติดตั้ง dependencies
pip install -r requirements.txt

# 4) รันแอป
python app.py
```

จากนั้นเปิดเบราว์เซอร์ไปที่ **http://127.0.0.1:5000**

> หรือดับเบิลคลิกไฟล์ **`start.bat`** เพื่อรันได้เลย (จะสร้าง venv + ติดตั้ง + รันให้อัตโนมัติ)

---

## 🔔 ตั้งค่าแจ้งเตือน LINE (ไม่บังคับ)

LINE Notify ถูกปิดบริการแล้ว แอปนี้จึงใช้ **LINE Messaging API** แทน:

1. สร้าง Messaging API channel ที่ <https://developers.line.biz/console/>
2. เอา **Channel access token** และ **User ID** ของคุณ
3. ตั้งค่า environment variable ก่อนรัน:

```powershell
$env:LINE_CHANNEL_TOKEN = "ใส่ token ที่นี่"
$env:LINE_USER_ID = "ใส่ user id ที่นี่"
python app.py
```

(ถ้ายังมี LINE Notify token เดิม ใส่ `$env:LINE_NOTIFY_TOKEN` ได้เช่นกัน)

---

## 🤖 ตั้งค่า AI Advisory (ไม่บังคับ)

- **ไม่ใส่ key** → ใช้ rule-based engine ในเครื่อง (อธิบายจากคะแนน/อินดิเคเตอร์จริง) ทำงานได้ทันที
- **ใส่ key** → ใช้ LLM ตอบเชิงลึก:

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."   # หรือ
$env:OPENAI_API_KEY = "sk-..."
```

---

## 🗂️ โครงสร้างโปรเจกต์

```
stock project/
├── app.py                # Flask entry point
├── config.py             # ค่าตั้งทั้งหมด (อ่านจาก env ได้)
├── database.py           # SQLite + cache layer
├── requirements.txt
├── start.bat             # สคริปต์รันบน Windows
├── routes/
│   └── api.py            # REST API ทุก endpoint
├── services/             # business logic แยกตามฟีเจอร์ (แก้/เพิ่มง่าย)
│   ├── stock_data.py     #   ดึงราคา/งบ/ประวัติ (yfinance) + cache
│   ├── technical.py      #   อินดิเคเตอร์ (pandas)
│   ├── fundamental.py    #   วิเคราะห์พื้นฐาน + เทียบคู่แข่ง
│   ├── news.py           #   ข่าว + keyword sentiment
│   ├── sentiment.py      #   Fear & Greed + sentiment รายตัว
│   ├── macro.py          #   มหภาค + sector rotation
│   ├── scoring.py        #   คะแนนรวม 0-100 + แผนเทรด
│   ├── screener.py       #   คัดกรองหุ้น
│   ├── portfolio.py      #   พอร์ต
│   ├── risk.py           #   ความเสี่ยง + position sizing
│   ├── backtest.py       #   backtest กลยุทธ์
│   ├── institutional.py  #   สถาบัน/insider
│   ├── alerts.py         #   แจ้งเตือน + LINE
│   ├── daily_report.py   #   รายงานประจำวัน
│   ├── ai_advisory.py    #   AI ถามตอบ
│   ├── gdelt.py          #   ข่าวโลก GDELT (จุดบนลูกโลก + tone timeline)
│   └── correlation.py    #   เครื่องเรียนรู้ หาจุดเชื่อม ข่าว ↔ ราคา
├── templates/index.html  # หน้า SPA
├── static/css/style.css  # ธีมอวกาศ + responsive
├── static/js/app.js      # routing + ทุก view
├── static/js/charts.js   # ตัวช่วยกราฟ Chart.js
└── static/js/globe-view.js # ลูกโลก 3D + หน้าเครื่องเรียนรู้
```

### API ใหม่

| Endpoint | ทำอะไร |
|---|---|
| `GET /api/world/points?timespan=24h` | จุดข่าวพร้อมพิกัดสำหรับลูกโลก |
| `GET /api/world/themes` | รายชื่อธีมข่าวโลก + สี |
| `GET /api/world/signals` | Tone ล่าสุดของแต่ละธีม |
| `GET /api/world/news?theme=energy` | รายการข่าวตามธีม |
| `GET /api/world/tone?theme=energy&days=180` | timeline ของ tone |
| `GET /api/learn/status` | สถานะคลังข้อมูลสะสม |
| `POST /api/learn/snapshot` | เก็บ snapshot ข่าว+ราคาทันที |
| `GET /api/learn/analyze/<ticker>?days=180` | หาความสัมพันธ์ของหุ้นตัวนั้น |
| `GET /api/learn/links` | ความสัมพันธ์ที่เรียนรู้ไว้แล้ว |

## 🧩 การเพิ่มฟีเจอร์ใหม่

1. เขียน logic ใน `services/<ชื่อ>.py`
2. เพิ่ม endpoint ใน `routes/api.py`
3. เพิ่ม view/เมนูใน `static/js/app.js` (`routes.<id>` + `NAV`)

## ⚠️ หมายเหตุ

- ข้อมูลทั้งหมดเพื่อการศึกษา **ไม่ใช่คำแนะนำการลงทุน**
- Yahoo Finance เป็น API ไม่เป็นทางการ อาจมี rate limit — แอปมี cache (SQLite) ช่วยลดการเรียกซ้ำ
- หุ้นไทยต้องลงท้ายด้วย `.BK` เสมอ (เช่น `PTT.BK`)
