# FaceID Attendance

**Real-time face recognition attendance system** — webcam orqali talabalarni aniqlaydi, ismini ko'rsatadi va davomatni avtomatik yozadi.

Python · FastAPI · InsightFace · PostgreSQL · OpenCV

---

## Imkoniyatlar

| Funksiya | Tavsif |
|----------|--------|
| **Jonli tanish** | Veb-kamera orqali real vaqtda yuz aniqlash va talabani tanish |
| **Davomat yozish** | Tanilgan talaba uchun avtomatik davomat + cooldown himoyasi |
| **Talaba qo'shish** | 5 burchakdan yuz surati (kamera yoki fayl orqali) |
| **Embedding** | ArcFace modeli bilan 512-o'lchamli yuz vektori |
| **Dashboard** | Statistika, talabalar ro'yxati, davomat tarixi |
| **Mobil qo'llab-quvvatlash** | Telefondan Wi-Fi orqali kirish, responsive UI |
| **GPU / CPU** | NVIDIA GPU (CUDA) yoki CPU rejimi |

---

## Qanday ishlaydi

```
Veb-kamera kadr
      ↓
Yuz aniqlash (SCRFD)
      ↓
Yuzni tekislash (5 nuqta landmark)
      ↓
Embedding (ArcFace → 512 vektor)
      ↓
Cosine similarity solishtirish
      ↓
Natija: Talaba ismi yoki "Stranger"
```

---

## Texnologiyalar

| Qatlam | Texnologiya |
|--------|-------------|
| Backend | Python 3.11, FastAPI, Uvicorn |
| Frontend | HTML, CSS, JavaScript, Jinja2 |
| Ma'lumotlar bazasi | PostgreSQL 14+ |
| Yuz aniqlash | InsightFace SCRFD |
| Yuz tanish | InsightFace ArcFace (buffalo_l) |
| Inference | ONNX Runtime (CPU / GPU) |
| Tasvir ishlash | OpenCV, Pillow |
| ORM | SQLAlchemy 2.0 (async) + asyncpg |

> **Python 3.11.x** tavsiya etiladi. Python 3.12+ ba'zi CV kutubxonalari bilan muammo berishi mumkin.

---

## Tez boshlash (Windows)

### 1. Talablar

- [Python 3.11](https://www.python.org/downloads/release/python-3119/) — **"Add Python to PATH"** belgilang
- [PostgreSQL 14+](https://www.postgresql.org/download/windows/)
- Veb-kamera (laptop yoki USB)

### 2. Ma'lumotlar bazasini yaratish

PostgreSQL da:

```sql
CREATE DATABASE face_attendance;
```

### 3. Loyihani o'rnatish

```powershell
cd C:\path\to\FaceIdCursor

# Virtual muhit
python -m venv .venv
.venv\Scripts\Activate.ps1

# Agar xato chiqsa:
# Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

# Kutubxonalar
pip install -r requirements.txt

# Sozlamalar
copy .env.example .env
# .env faylini tahrirlang (DATABASE_URL, SECRET_KEY va boshqalar)
```

### 4. Serverni ishga tushirish

```powershell
.\run.ps1
```

Brauzerda oching: **http://localhost:8000**

---

## Telefondan kirish

1. Telefon va kompyuter **bir xil Wi-Fi** tarmog'ida bo'lsin
2. `.\run.ps1` ishga tushiring — terminalda telefon uchun IP ko'rsatiladi
3. Telefonda oching: `http://<PC-IP>:8000` (masalan `http://10.21.151.162:8000`)

Agar ulanmasa, Administrator sifatida:

```powershell
.\setup_firewall.ps1
```

> **Eslatma:** HTTP rejimida telefon ekranida **kompyuter veb-kamerasi** jonli videosi ko'rinadi — xuddi laptopdagi kabi. Odam kompyuter kamerasi oldida turishi kerak.

HTTPS rejimi (ixtiyoriy, telefonning o'z kamerasi uchun):

```powershell
.\run_https.ps1
```

---

## Loyiha tuzilmasi

```
FaceIdCursor/
├── app/
│   ├── api/routes/       # API va sahifa marshrutlari
│   ├── core/             # Sozlamalar, logging
│   ├── database/         # DB ulanish, migratsiyalar
│   ├── enrollment/       # Talaba ro'yxatdan o'tkazish
│   ├── models/           # SQLAlchemy modellari
│   ├── recognition/      # Kamera, detection, embedding, matching
│   ├── services/         # Biznes logika
│   ├── static/           # CSS, JavaScript
│   └── templates/        # HTML shablonlar
├── face_data/
│   ├── images/           # Yuz suratlari (gitignore)
│   └── embeddings/       # Embedding fayllari (gitignore)
├── logs/                 # Ilova loglari (gitignore)
├── scripts/              # SSL sertifikat va yordamchi skriptlar
├── certs/                # SSL sertifikatlar (gitignore)
├── .env.example          # Muhit o'zgaruvchilari namunasi
├── requirements.txt
├── run.ps1               # HTTP server
├── run_https.ps1         # HTTPS server
├── stop_servers.ps1      # Port 8000 ni tozalash
└── setup_firewall.ps1    # Windows Firewall qoidasi
```

---

## Sozlamalar (.env)

| O'zgaruvchi | Tavsif | Standart |
|-------------|--------|----------|
| `APP_HOST` | Server host | `0.0.0.0` (telefon uchun) |
| `APP_PORT` | Port | `8000` |
| `DATABASE_URL` | PostgreSQL ulanish | — |
| `RECOGNITION_THRESHOLD` | Tanish chegarasi (0–1) | `0.45` |
| `USE_GPU` | GPU yoqish | `False` |
| `ATTENDANCE_COOLDOWN_SECONDS` | Qayta yozish vaqti | `30` |

Birinchi ishga tushirishda InsightFace modellari avtomatik yuklanadi (~270 MB).

---

## GPU qo'llab-quvvatlash (ixtiyoriy)

NVIDIA GPU + CUDA 11.8 yoki 12.x bo'lsa:

```powershell
pip uninstall onnxruntime
pip install onnxruntime-gpu==1.18.0
```

`.env` da: `USE_GPU=True`

GPU bo'lmasa tizim avtomatik CPU rejimida ishlaydi (~15–20 FPS).

---

## API endpointlar

| Endpoint | Vazifa |
|----------|--------|
| `POST /api/stream/start` | Kamerani yoqish |
| `GET /api/stream/feed` | Jonli MJPEG video |
| `GET /api/stream/status` | FPS, tanish natijasi |
| `POST /api/stream/stop` | Kamerani o'chirish |
| `POST /api/enroll/student` | Yangi talaba yaratish |
| `POST /api/enroll/capture/{id}/{angle}` | Burchakdan surat olish |
| `GET /api/attendance/last` | Oxirgi davomat |

To'liq API hujjati: `http://localhost:8000/docs` (DEBUG=True bo'lganda)

---

## GitHub ga yuklash

Loyiha GitHub uchun tayyorlangan. Quyidagi buyruqlar:

```powershell
cd C:\path\to\FaceIdCursor

git init
git add .
git status          # .env va face_data yuklanmasligini tekshiring
git commit -m "Initial commit: FaceID Attendance System"

# GitHub da yangi repo yarating, keyin:
git remote add origin https://github.com/<username>/FaceIdCursor.git
git branch -M main
git push -u origin main
```

### Gitignore qoidalari

Quyidagilar **hech qachon** GitHub ga yuklanmaydi:

- `.env` — parollar va maxfiy kalitlar
- `.venv/` — virtual muhit
- `face_data/` — yuz suratlari va embeddinglar
- `logs/` — log fayllar
- `certs/*.pem` — SSL sertifikatlar

---

## Muammolarni hal qilish

| Muammo | Yechim |
|--------|--------|
| Port 8000 band | `.\stop_servers.ps1` ishga tushiring |
| Telefon ulanmaydi | Bir xil Wi-Fi, `setup_firewall.ps1`, to'g'ri IP |
| `ERR_SSL_PROTOCOL_ERROR` | Faqat bitta server ishlayotganini tekshiring |
| Kamera ochilmaydi | Boshqa dastur kamerani band qilmaganini tekshiring |
| Model yuklanmaydi | Internet ulanishi va ~270 MB bo'sh joy |

---

## Litsenziya

Shaxsiy / ta'lim loyihasi. Erkin foydalaning va o'zgartiring.

---

**FaceID Attendance** — yuz tanish orqali aqlli davomat tizimi.
