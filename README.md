# AI Smart Health Environment

AI Smart Health Environment เป็นโครงงาน **AI + IoT environmental health monitoring system** สำหรับติดตามสภาพแวดล้อมและให้คำแนะนำที่สัมพันธ์กับลักษณะที่ผู้ใช้เลือก โดยใช้ ESP32 และ SCD40 วัดค่า ส่งข้อมูลเข้า FastAPI และ PostgreSQL แล้วแสดงผลบนเว็บ Dashboard พร้อมการประเมินเฉพาะบุคคลผ่าน Groq

> การประเมินของ AI เป็นคำแนะนำด้านสภาพแวดล้อมจากข้อมูลที่วัดได้ **ไม่ใช่การวินิจฉัยทางการแพทย์**

## ภาพรวมและขอบเขตการวัด

ระบบวัด **CO₂ (ppm), อุณหภูมิ (°C) และความชื้นสัมพัทธ์ (%RH)** แบบต่อเนื่อง แสดงสถานะด้วย LED และให้ ESP32 สั่ง Relay/พัดลมอัตโนมัติตามเกณฑ์ที่กำหนดไว้ ข้อมูลถูกส่งผ่าน Wi-Fi เป็น HTTP/JSON ไปยัง Backend เพื่อบันทึกและแสดงค่าปัจจุบันกับประวัติบน Dashboard ผู้ใช้เลือกความไวต่อสภาพแวดล้อมชั่วคราวเพื่อรับคำอธิบายและข้อแนะนำภาษาไทยจาก AI

**CO₂ คือความเข้มข้นของก๊าซคาร์บอนไดออกไซด์ในอากาศ** ไม่ใช่ฝุ่น, PM2.5 หรือออกซิเจน อุปกรณ์ชุดนี้ **ไม่ได้วัด PM2.5, PM10, ฝุ่น, ละอองเกสร, O₂ หรือ VOC** จึงไม่ใช้ค่า CO₂ เป็นค่าฝุ่นหรืออนุมานระดับออกซิเจน

## Architecture

```mermaid
flowchart TD
    SCD40["SCD40: CO₂ / อุณหภูมิ / ความชื้น"] --> ESP32["ESP32"]
    ESP32 --> LED["LED แสดงสถานะ"]
    ESP32 --> FAN["Relay/พัดลม: ควบคุมตามเกณฑ์"]
    ESP32 -- "Wi-Fi · HTTP/JSON telemetry" --> API["FastAPI Backend"]
    API <--> DB["PostgreSQL"]
    API --> UI["React Dashboard"]
    UI -- "device_id + sensitivities" --> ASSESS["AI Assessment API ใน FastAPI"]
    ASSESS -- "อ่านค่าล่าสุดและข้อมูลย้อนหลัง" --> DB
    ASSESS <--> GROQ["Groq"]
    ASSESS -- "ผลประเมินภาษาไทย" --> UI
```

ESP32 ควบคุมพัดลมด้วยตรรกะที่กำหนดแน่นอนและทำงานได้แม้ไม่มี Internet ส่วน AI ใช้ตีความข้อมูลเพิ่มเติมสำหรับผู้ใช้ **AI ไม่ได้สั่ง Relay/พัดลม** หาก Groq ใช้งานไม่ได้ การรับและบันทึก telemetry ยังทำงานได้ และ AI endpoint มี deterministic fallback

## Hardware และการเชื่อมต่อขา

อุปกรณ์ในชุดทดสอบ: ESP32 Node32S / ESP32-WROOM-32, Sensirion SCD40, LED สีเขียว/เหลือง/แดง, ตัวต้านทานสำหรับ LED, 5V relay module, พัดลม 5V, breadboard และสาย jumper ไม่มี DHT11 หรือปุ่มกดเป็นอุปกรณ์ที่จำเป็นในชุดสุดท้าย

| อุปกรณ์ | ขาอุปกรณ์ | ESP32 / แหล่งจ่าย |
| --- | --- | --- |
| SCD40 | SDA | GPIO32 |
| SCD40 | SCL | GPIO33 |
| SCD40 | VCC | 3V3 |
| SCD40 | GND | GND |
| LED เขียว (ผ่านตัวต้านทาน) | Signal | GPIO23 |
| LED เหลือง (ผ่านตัวต้านทาน) | Signal | GPIO18 |
| LED แดง (ผ่านตัวต้านทาน) | Signal | GPIO19 |
| Relay module | Signal | GPIO26 |
| Relay module | VCC/+ | 5V/VIN |
| Relay module | GND/- | GND |

Relay ของชุดทดสอบนี้ใช้ **HIGH = ON, LOW = OFF** ข้อมูลขาและพฤติกรรมฮาร์ดแวร์ข้างต้นอ้างอิงชุดทดสอบจริงที่ใช้ในโครงงาน; **repository นี้ยังไม่มีไฟล์ ESP32/Arduino firmware** จึงไม่สามารถตรวจทานเลขขาและวงจรจาก sketch ใน Git ได้

### ข้อจำกัดการจ่ายไฟพัดลม

ตรรกะการสั่ง Relay ทำงาน แต่การจ่ายไฟให้พัดลม 5V ผ่านเส้นทางไฟของ ESP32/USB ระหว่างทดสอบทำให้เกิด `Brownout detector was triggered` ระบบกลับมาเสถียรเมื่อถอดโหลดพัดลมจริงออก ดังนั้นการใช้งานพัดลมจริงอย่างเสถียรควรใช้แหล่งจ่าย **5V ภายนอกที่เหมาะกับโหลดพัดลม** โดยให้ ESP32 ควบคุมด้านสัญญาณ Relay ต่อไป ห้ามจ่ายไฟพัดลมจากขา ESP32 3V3 ประเด็นนี้เป็นข้อจำกัดด้านกำลังไฟ ไม่ใช่ความล้มเหลวของ AI หรือ Backend

## เกณฑ์สถานะสภาพแวดล้อมและ Auto Fan

เกณฑ์ของโครงงานที่ตรวจสอบได้จาก Backend มีดังนี้:

| ค่าที่วัด | GOOD | MODERATE | HOT |
| --- | --- | --- | --- |
| CO₂ | < 1000 ppm | ≥ 1000 ppm | ≥ 1500 ppm |
| อุณหภูมิ | < 28°C | ≥ 28°C | ≥ 30°C |
| ความชื้นสัมพัทธ์ | < 70% | ≥ 70% | ≥ 85% |

สถานะรวมเป็น `HOT` เมื่อมีค่าใดถึงระดับ HOT; หากไม่มี HOT แต่มีค่าใดถึง MODERATE ให้เป็น `MODERATE`; นอกนั้นเป็น `GOOD` เกณฑ์เหล่านี้เป็น **ค่าที่โครงงานกำหนดสำหรับ prototype ไม่ใช่มาตรฐานการแพทย์สากล**

ESP32 ใช้สถานะ `HOT` เพื่อเปิดพัดลมอัตโนมัติและใช้ hysteresis เพื่อลดการสลับ ON/OFF ถี่เกินไป การควบคุมในอุปกรณ์ตอบสนองได้ทันที ทำงานได้เมื่อ Internet ขาด และคาดเดาพฤติกรรมได้ จึงไม่ให้ AI ควบคุมพัดลมโดยตรง เนื่องจาก sketch ไม่ได้อยู่ใน repository จึงยังไม่ระบุ **ค่าเกณฑ์ปิดพัดลมของ hysteresis** หรือช่วงเวลาส่ง telemetry เป็นตัวเลข

เมื่อรับข้อมูล Backend จะใช้ `status` ที่ ESP32 ส่งมาเป็นหลัก หากไม่มี `status` จึงคำนวณจากเกณฑ์ในตาราง (`co2` ที่เป็น `null` จะถูกข้าม) Backend ยังสร้าง `recommendation` แบบ deterministic จากค่าจริง โดยแยกกรณี CO₂ สูง อุณหภูมิสูง ความชื้นสูง หรือหลายปัจจัยพร้อมกัน ข้อความจาก Backend เป็น English และ Frontend แปลงข้อความที่รองรับเป็นภาษาไทยเพื่อแสดงผล

## ESP32 Telemetry

ESP32 ส่งข้อมูลผ่าน Wi-Fi ไปที่ `POST /api/v1/readings` ตัวอย่าง JSON ที่ตรงกับ schema ปัจจุบัน:

```json
{
  "device_id": "smart-room-01",
  "temperature": 26.8,
  "humidity": 86.5,
  "co2": 2266,
  "status": "HOT",
  "fan_on": true
}
```

`device_id` เป็นชื่ออุปกรณ์ที่ใช้เพื่อความเข้ากันได้ของระบบเดิม `status` และ `co2` เป็น optional ใน API เพื่อรองรับ payload รุ่นก่อน แต่ชุดฮาร์ดแวร์สุดท้ายใช้ SCD40 สำหรับ CO₂ ก่อนอัปโหลด firmware ให้ใส่ชื่อ Wi-Fi และรหัสผ่านของตนเองแทน `YOUR_WIFI_SSID` และ `YOUR_WIFI_PASSWORD` หาก sketch ใช้ backend URL แบบ IP ภายใน ให้ชี้ไปที่ `http://<BACKEND_LAN_IP>:8000/api/v1/readings` และปรับเมื่อ IP ของเครื่องที่รัน Backend หรือเครือข่ายเปลี่ยน

## Backend, PostgreSQL และ API

Backend ใช้ FastAPI, Pydantic ตรวจสอบ JSON, SQLAlchemy จัดการข้อมูล และ Alembic จัดการ schema ใน PostgreSQL ตาราง `sensor_readings` เก็บค่าที่วัด, `device_id`, `fan_on`, สถานะ, คำแนะนำ และเวลาที่บันทึก Migration สร้างตารางและ index สำหรับ `device_id` กับเวลา; แอปไม่ได้รัน migration อัตโนมัติเมื่อเริ่มทำงาน

| Method และ endpoint | การทำงาน |
| --- | --- |
| `GET /health` | ตรวจว่า API ทำงาน (`{"status":"ok"}`); ไม่ใช่การทดสอบการเชื่อมต่อฐานข้อมูล |
| `POST /api/v1/readings` | ตรวจสอบและบันทึก telemetry; ตอบ `success`, `status`, `recommendation`, `data` |
| `GET /api/v1/readings/latest` | อ่านรายการล่าสุดที่บันทึกไว้ |
| `GET /api/v1/readings?limit=50` | อ่านประวัติล่าสุดก่อน; `limit` ค่าเริ่มต้น 50, รับ 1–500 |
| `POST /api/v1/ai/assessment` | ประเมินสภาพแวดล้อมจากข้อมูลของ `device_id` และลักษณะที่เลือก |

`GET /api/v1/readings/latest` ส่ง 404 เมื่อยังไม่มีข้อมูล ส่วน AI endpoint ส่ง 404 หากไม่พบข้อมูลของอุปกรณ์นั้น คำขอ AI ที่ไม่มี `sensitivities` หรือใช้ ID ที่ไม่รองรับจะได้ 422 ดู schema แบบ interactive ได้ที่ `http://localhost:8000/docs`

## AI Assessment

AI ผสาน **ค่าล่าสุดและข้อมูลย้อนหลังที่บันทึกไว้จริง** กับความไวต่อสภาพแวดล้อมที่ผู้ใช้เลือก เพื่ออธิบายว่าขณะนี้สภาพแวดล้อมอาจเหมาะกับผู้ใช้อย่างไร พร้อมข้อแนะนำที่ปฏิบัติได้ ไม่มีระบบ login และ **ไม่บันทึกตัวเลือกด้านสุขภาพลง PostgreSQL** Frontend เก็บตัวเลือกชั่วคราวใน `sessionStorage` ของแท็บเบราว์เซอร์

| Sensitivity ID | ความหมายใน UI |
| --- | --- |
| `heat_sensitive` | ร้อนง่าย / ไวต่ออากาศร้อน |
| `cold_sensitive` | ขี้หนาว / ไวต่ออากาศเย็น |
| `high_humidity_sensitive` | ไวต่อความชื้นสูง |
| `dry_air_sensitive` | ไวต่ออากาศแห้ง |
| `poor_ventilation_sensitive` | ไวต่ออากาศอับหรือการระบายอากาศไม่ดี |
| `respiratory_sensitive` | ระบบทางเดินหายใจไวต่อสภาพแวดล้อม |

ไม่มีตัวเลือกแพ้ฝุ่น เพราะฮาร์ดแวร์ปัจจุบันไม่ได้วัดฝุ่นหรือ PM2.5

### ลำดับการประเมิน

1. Frontend ส่ง **เพียง** `device_id` และ `sensitivities`; ไม่ส่งค่าจากเซนเซอร์ในคำขอ AI

   ```json
   {
     "device_id": "smart-room-01",
     "sensitivities": ["high_humidity_sensitive", "poor_ventilation_sensitive"]
   }
   ```

2. Backend อ่านข้อมูลล่าสุด **สูงสุด 12 รายการของอุปกรณ์นั้น** จาก PostgreSQL แล้วคำนวณค่าล่าสุด ค่าเฉลี่ยย้อนหลัง แนวโน้ม สถานะและระดับของแต่ละปัจจัย ก่อนส่งบริบทสรุปพร้อมตัวเลือกผู้ใช้ให้ Groq
3. Groq ส่ง JSON ภาษาไทยกลับมา Backend ตรวจรูปแบบ ข้อความ และความสอดคล้องกับค่าที่วัดได้ หากไม่ผ่านหรือบริการใช้งานไม่ได้ จะใช้ deterministic fallback ด้วย response schema เดียวกัน

ตัวอย่าง **รูปแบบ response** (ข้อความประกอบเป็นตัวอย่าง):

```json
{
  "success": true,
  "source": "fallback",
  "device_id": "smart-room-01",
  "profile": ["high_humidity_sensitive", "poor_ventilation_sensitive"],
  "environment": {
    "temperature": 26.8,
    "humidity": 86.5,
    "co2": 2266,
    "status": "HOT"
  },
  "assessment": {
    "suitability": "NOT_SUITABLE",
    "title": "สภาพแวดล้อมตอนนี้อาจไม่เหมาะกับคุณ",
    "summary": "ค่า CO₂ และความชื้นค่อนข้างสูงเมื่อเทียบกับลักษณะที่คุณเลือก",
    "reasons": ["ค่า CO₂ 2,266 ppm สูง", "ความชื้น 86.5% สูง"],
    "recommendations": ["เพิ่มการถ่ายเทอากาศจากภายนอก", "ลดความชื้นส่วนเกินและตรวจค่าซ้ำ"]
  },
  "disclaimer": "คำแนะนำนี้อ้างอิงจากค่า CO₂ อุณหภูมิ ความชื้น และลักษณะที่คุณเลือก ไม่ใช่การวินิจฉัยทางการแพทย์"
}
```

`suitability` มีค่า `SUITABLE`, `CAUTION` หรือ `NOT_SUITABLE`; ข้อความที่ผู้ใช้เห็นเป็นภาษาไทย `source: "groq"` หมายถึงผลจาก Groq ที่ผ่านการตรวจสอบ และ `source: "fallback"` หมายถึงใช้กฎ deterministic ค่านี้เป็นรายละเอียดการทำงาน ไม่ได้เน้นใน UI

### Groq และขอบเขตความปลอดภัย

กำหนด `GROQ_API_KEY` ใน `.env` เพื่อใช้ผลจาก Groq; `GROQ_MODEL` เปลี่ยนได้และมีค่าเริ่มต้น `openai/gpt-oss-20b` หากไม่มี key, คำขอหมดเวลา, provider ขัดข้อง หรือผลลัพธ์ไม่ถูกต้อง ระบบจะใช้ fallback โดย telemetry ยังทำงานตามปกติ

Prompt และการตรวจผลลัพธ์จำกัด AI ให้ยึดเฉพาะ CO₂, อุณหภูมิ และความชื้นที่ Backend สรุปให้ ไม่เรียก CO₂ ว่าฝุ่น/PM, ไม่อ้างว่ามีการวัด O₂ หรืออนุมานว่า O₂ ต่ำจาก CO₂ สูง, ไม่แต่งค่าที่วัด ไม่กล่าวว่าค่าปกติสูงผิดปกติ ไม่วินิจฉัยโรคหรือแนะนำยา/การรักษา และไม่เปลี่ยนสถานะ deterministic หรือสั่ง Relay ผลลัพธ์ที่ผิดข้อเท็จจริงหรือไม่ผ่านการตรวจจะถูกแทนด้วย fallback; ความคลาดเคลื่อนเฉพาะระดับความเหมาะสมบางกรณีจะถูกปรับให้ตรงกับผล deterministic มาตรการนี้เป็นการจำกัดคำแนะนำของ prototype **ไม่ใช่ระบบความปลอดภัยทางการแพทย์ที่ผ่านการรับรอง**

## Frontend

Dashboard พัฒนาด้วย React, Vite, TypeScript และ Recharts โดยใช้ภาษาไทยเป็นหลัก พร้อมคำเทคนิคเท่าที่จำเป็น เช่น CO₂, ppm, °C, %RH, API, AI และ Wi-Fi แสดง:

- อุณหภูมิ ความชื้น CO₂ สถานะพัดลม/Relay และเวลาอัปเดตล่าสุด
- สถานะกับคำแนะนำสภาพแวดล้อมแบบ deterministic และกราฟประวัติทั้งสามค่า
- หน้าต่างเลือก/แก้ไขลักษณะด้านสุขภาพ การประเมิน AI ภาษาไทย และปุ่ม “วิเคราะห์อีกครั้ง”

Frontend ดึงค่าปัจจุบันและประวัติใหม่ประมาณทุก **5 วินาที** แต่ **ไม่เรียก Groq ทุก 5 วินาที** การประเมิน AI เริ่มเมื่อยืนยันหรือเปลี่ยน profile, เมื่อเปิดหน้าใหม่พร้อม profile ที่เก็บใน session, หรือเมื่อกดวิเคราะห์อีกครั้ง หาก API ดึงข้อมูลไม่ได้ Dashboard ยังแสดงข้อมูลล่าสุดที่มีพร้อมแจ้งสถานะการเชื่อมต่อ

## Environment Variables

คัดลอก `.env.example` ที่ root เป็น `.env` แล้วกำหนดค่าตามเครื่องของตนเอง:

```dotenv
DATABASE_URL=postgresql+psycopg://username:password@localhost:5432/ai_smart_room
GROQ_API_KEY=YOUR_GROQ_API_KEY
GROQ_MODEL=openai/gpt-oss-20b
```

| ตัวแปร | ใช้ทำอะไร |
| --- | --- |
| `DATABASE_URL` | จำเป็นสำหรับ PostgreSQL; ปรับ host, port, user, password และชื่อฐานข้อมูลตามเครื่อง |
| `GROQ_API_KEY` | ใช้ Groq แบบ live; เว้นว่างได้หากต้องการทดสอบ fallback |
| `GROQ_MODEL` | optional; ค่าเริ่มต้น `openai/gpt-oss-20b` |
| `VITE_API_BASE_URL` | optional ใน `frontend/.env`; ค่าเริ่มต้น `http://localhost:8000` |

ชื่อฐานข้อมูล `ai_smart_room` ในตัวอย่างเป็นชื่อภายในที่คงไว้เพื่อความเข้ากันได้ ตั้งค่า `DATABASE_URL` ให้ตรงกับ PostgreSQL ที่ใช้งานจริง ไม่จำเป็นต้องใช้ port พิเศษ ห้าม commit `.env` ลง Git

แทน `YOUR_GROQ_API_KEY` ด้วย key จริงเฉพาะใน `.env` เมื่อต้องการใช้ Groq แบบ live หรือปล่อยค่า `GROQ_API_KEY` ว่างเพื่อใช้ fallback

## ติดตั้งและเปิดระบบในเครื่อง

ต้องมี Python, Node.js/npm, PostgreSQL, ESP32 ที่ตั้งค่า Wi-Fi และ SCD40 แล้ว คำสั่งด้านล่างใช้ virtual environment ที่ root repository

1. **เตรียม Backend และฐานข้อมูล** จาก root:

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   python -m pip install -r backend/requirements.txt
   cp .env.example .env
   ```

   แก้ `DATABASE_URL` ใน `.env`, สร้างฐานข้อมูลตามชื่อใน URL และเปิดบริการ PostgreSQL ของเครื่อง จากนั้นรัน migration จากโฟลเดอร์ `backend`:

   ```bash
   cd backend
   alembic upgrade head
   cd ..
   ```

2. **เตรียม Frontend**:

   ```bash
   cd frontend
   npm install
   cd ..
   ```

   หาก API ไม่ได้อยู่ที่ `http://localhost:8000` ให้คัดลอก `frontend/.env.example` เป็น `frontend/.env` และแก้ `VITE_API_BASE_URL`

3. **เปิดใช้งานตามลำดับ**: เปิด Wi-Fi/hotspot ที่ ESP32 จะใช้ → ต่อไฟ/เปิด ESP32 → ตรวจว่า PostgreSQL ทำงาน → เปิด FastAPI ใน terminal แรกจาก root:

   ```bash
   source .venv/bin/activate
   cd backend
   python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
   ```

4. เปิด Frontend ใน terminal อีกหน้าต่างจาก root:

   ```bash
   cd frontend
   npm run dev
   ```

5. เปิด `http://localhost:5173` ในเบราว์เซอร์ หาก ESP32 ส่งข้อมูลจากเครือข่ายเดียวกัน ให้ URL ฝั่ง firmware ชี้ไปที่ **IP ภายในของเครื่อง Backend** ไม่ใช่ `localhost` ของ ESP32

## การทดสอบ

จาก root หลังติดตั้ง dependencies:

```bash
source .venv/bin/activate
python -m unittest discover -s backend/tests -v
python -m compileall -q backend/app backend/alembic
```

```bash
cd frontend
npm test
npm run build
```

Backend tests ครอบคลุม status/recommendation, schema, AI endpoint, Groq ที่ mock ไว้, fallback และการปฏิเสธคำตอบที่ไม่ตรงกับข้อมูล โดยใช้ SQLite ในหน่วยทดสอบแทน PostgreSQL Frontend tests ตรวจการเลือก profile, การเรียก API, การแปลคำแนะนำ และการแยก AI request ออกจากการดึง telemetry ผลการตรวจล่าสุด: **backend 37 tests ผ่าน, frontend 11 tests ผ่าน, compile และ build ผ่าน** การทดสอบเหล่านี้ไม่ได้ยืนยัน firmware หรือความเสถียรของการจ่ายไฟพัดลมจริง

## Demo Flow

1. SCD40 วัด CO₂ อุณหภูมิ และความชื้น
2. ESP32 กำหนดสถานะ แสดง LED และสั่ง Relay/พัดลมอัตโนมัติ
3. ESP32 ส่ง telemetry ไป FastAPI และ PostgreSQL บันทึกข้อมูล
4. Dashboard แสดงค่าปัจจุบัน ประวัติ และคำแนะนำพื้นฐาน
5. ผู้ใช้เลือกลักษณะที่ไวต่อสภาพแวดล้อม
6. Backend อ่านข้อมูลจริงจาก PostgreSQL แล้วส่งบริบทให้ Groq
7. Dashboard แสดงคำอธิบายและคำแนะนำภาษาไทยที่เหมาะกับผู้ใช้ หรือ fallback เมื่อ Groq ไม่พร้อม

## โครงสร้าง Repository

```text
.
├── .env.example                 # ตัวอย่างตัวแปร Backend
├── backend/
│   ├── app/                     # FastAPI, schema, status, database, AI
│   ├── alembic/                 # migration ของ sensor_readings
│   ├── tests/                   # backend tests
│   ├── alembic.ini
│   └── requirements.txt
└── frontend/
    ├── .env.example             # ตัวอย่าง URL ของ API
    ├── src/                     # React Dashboard, components, tests
    ├── package.json
    └── package-lock.json
```

**ยังไม่มีโฟลเดอร์หรือไฟล์ firmware ใน repository นี้** ก่อนทำซ้ำส่วนฮาร์ดแวร์ต้องมี ESP32 sketch ที่ตรงกับการต่อขาและ API ข้างต้น

## ข้อจำกัดและแนวทางพัฒนา

- เซนเซอร์ปัจจุบันวัดเพียง CO₂, อุณหภูมิ และความชื้น ไม่มีเซนเซอร์ PM2.5/ฝุ่น, O₂ หรือสารอื่น
- คำแนะนำ AI ไม่ใช่การวินิจฉัย; ตัวเลือกของผู้ใช้เป็นข้อมูลชั่วคราว ไม่ใช่เวชระเบียน
- การใช้งานพัดลมจริงต้องปรับการจ่ายไฟ 5V ให้เหมาะสมเพื่อหลีกเลี่ยง brownout
- หาก IP ของ Backend เปลี่ยน อาจต้องแก้ URL ใน ESP32 firmware
- Groq แบบ live ต้องมี Internet/API ใช้งานได้ แต่ deterministic fallback ยังตอบได้

แนวทางพัฒนาต่อ: เพิ่ม PM2.5 และเซนเซอร์คุณภาพอากาศชนิดอื่น, วงจรจ่ายไฟพัดลมแยกและ enclosure/PCB, รองรับหลายอุปกรณ์, ระบบบัญชีหรือ profile แบบ optional, การวิเคราะห์ประวัติเพิ่มเติม และการ deploy บน cloud สิ่งเหล่านี้ **ยังไม่ได้ทำในระบบปัจจุบัน**

## Security

อย่า commit `.env`, `GROQ_API_KEY` หรือรหัสผ่าน Wi-Fi จริง ใช้ placeholder ในตัวอย่าง firmware และเปลี่ยน credentials ที่เคยเปิดเผยระหว่างพัฒนาเมื่อจำเป็น ไฟล์ `.env` ถูก ignore โดย Git แต่ควรตรวจ diff ก่อน commit ทุกครั้ง
