# Smart Hardhat

An IoT-based construction site safety monitoring system (FYP F26-113, FAST-NU Lahore).

A removable hardhat module monitors **CO, temperature, humidity, motion (fall detection), battery and GPS**. It has a guarded **SOS** button and local light, vibration and sound alerts that work without a network. Data travels over **LoRa** to an ESP32 gateway, then to a local **FastAPI + PostgreSQL** backend and a **Next.js** supervisor dashboard. A decision-tree model provides advisory risk assessments.

## Architecture
```
Hardhat (ESP32 + sensors) --LoRa--> Gateway (ESP32) --HTTPS--> FastAPI --> PostgreSQL
                                                                  |
                                                     Next.js dashboard (SSE)
```

## Stack
- **Firmware:** ESP-IDF (ESP32-S3 + SX1262), AES-GCM radio framing
- **Backend:** Python, FastAPI, PostgreSQL, scikit-learn
- **Frontend:** Next.js
- **Deployment:** local network behind a TLS reverse proxy (no cloud)

## Docs
- `F26-113.pdf`: full requirements and design (Deliverable II)
- `PROJECT_OVERVIEW.txt`: condensed design and current implementation status

## Team
Hamza Azam, Muzzammil Shahid and Roshni Waheed. Supervisor: Mr. Saifullah Tanvir.

> Prototype for controlled evaluation only. It makes no claim of certified protective performance.
