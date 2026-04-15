# Smart Structural Health Monitoring — Digital Twin System

## Architecture

```
Sensors (ESP32) → Raspberry Pi → Flask API (:5000) → Browser Dashboard
                                       ↑
                              [Simulated in dev mode]
```

## Project Structure

```
shm-system/
├── backend/
│   ├── app.py            ← Flask API (simulation + anomaly detection)
│   └── requirements.txt
└── frontend/
    └── index.html        ← Dashboard (open directly in browser)
```

---

## Quick Start

### 1 — Install Python dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2 — Start the Flask backend

```bash
python app.py
```

You should see:
```
======================================================
  Smart SHM Backend  v1.0.0
  Mode     : SIMULATED
  Endpoint : http://127.0.0.1:5000/api/data
======================================================
```

### 3 — Open the frontend

Simply open `frontend/index.html` in any modern browser.
No build step, no npm, no server needed.

The dashboard will auto-connect to `http://127.0.0.1:5000/api/data`
and refresh every 2.5 seconds.

---

## API Endpoints

| Method | Route            | Purpose                                |
|--------|------------------|----------------------------------------|
| GET    | `/api/data`      | Latest sensor reading + anomaly result |
| POST   | `/api/sensor`    | Ingest real hardware data (ESP32/RPi)  |
| GET    | `/api/history`   | Last N readings for charts             |
| GET    | `/api/status`    | Node health check / heartbeat          |

### GET /api/data — Response

```json
{
  "temperature": 36.4,
  "vibration":   2.18,
  "strain":      54.1,
  "humidity":    61.3,
  "wind_speed":  4.2,
  "status":      "NORMAL",
  "score":       0.142,
  "triggers":    [],
  "timestamp":   "2025-01-01T12:00:00+00:00",
  "source":      "simulated",
  "node_id":     "RPI-EDGE-01",
  "structure_id":"BRIDGE-001"
}
```

### POST /api/sensor — Payload (from ESP32/RPi firmware)

```json
{
  "temperature": 47.2,
  "vibration":   4.6,
  "strain":      71.3,
  "humidity":    65.0,
  "wind_speed":  3.1
}
```

---

## Connecting Real Hardware (ESP32 → Raspberry Pi → API)

### Step 1: Change backend mode

In `backend/app.py`, line 20:
```python
USE_SIMULATED = False   # was True
```

### Step 2: Raspberry Pi firmware (Python)

```python
import requests, json

def send_to_api(temp, vib, strain):
    payload = {
        "temperature": temp,
        "vibration":   vib,
        "strain":      strain,
    }
    requests.post("http://127.0.0.1:5000/api/sensor", json=payload)
```

### Step 3: ESP32 Arduino (sends to RPi via HTTP)

```cpp
#include <HTTPClient.h>

HTTPClient http;
http.begin("http://<RPI_IP>:5000/api/sensor");
http.addHeader("Content-Type", "application/json");

String payload = "{\"temperature\":" + String(temp) +
                 ",\"vibration\":"   + String(vib)  +
                 ",\"strain\":"      + String(strain) + "}";

http.POST(payload);
```

The frontend requires **zero changes** when switching from simulated to hardware.

---

## Thresholds (configurable in app.py)

| Sensor      | Alert Threshold |
|-------------|-----------------|
| Temperature | > 45 °C         |
| Vibration   | > 4.0 m/s²      |
| Strain      | > 85 με         |

---

## CORS

CORS is enabled for all origins in development.
For production, restrict in `app.py`:

```python
CORS(app, origins=["https://your-dashboard.com"])
```
