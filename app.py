"""
Smart Structural Health Monitoring — Backend API
================================================
Author  : SHM System
Version : 1.0.0

Architecture:
  Sensors (ESP32) → Raspberry Pi → This API → Frontend Dashboard

Current mode: Simulated sensor data.
To switch to real hardware: POST real readings to /api/sensor
from your ESP32/RPi firmware, and set USE_SIMULATED = False.
"""

import random
import math
import time
import logging
from datetime import datetime, timezone
from collections import deque
from flask import Flask, jsonify, request
from flask_cors import CORS

# ─────────────────────────────────────────────
#  CONFIG
# ─────────────────────────────────────────────
USE_SIMULATED   = True   # Set False when real hardware is connected
HISTORY_SIZE    = 60     # Number of readings kept in memory
TEMP_THRESHOLD  = 45.0   # °C
VIB_THRESHOLD   = 4.0    # m/s²
STRAIN_MAX      = 100.0  # microstrain (reference)

# ─────────────────────────────────────────────
#  APP SETUP
# ─────────────────────────────────────────────
app = Flask(__name__)
CORS(app)  # Allow frontend on any origin (restrict in production)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(levelname)s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ─────────────────────────────────────────────
#  IN-MEMORY STATE
# ─────────────────────────────────────────────
# Stores the most recent reading (updated by POST or simulation)
latest_reading: dict = {}

# Circular buffer for chart history
history: deque = deque(maxlen=HISTORY_SIZE)

# Spike simulation state (mimics real-world transient events)
_spike_state = {
    "type"    : None,     # "temp" | "vib" | None
    "ttl"     : 0,        # ticks remaining
    "counter" : 0,        # total ticks elapsed
}


# ─────────────────────────────────────────────
#  SIMULATION ENGINE
# ─────────────────────────────────────────────
def _simulate_sensors() -> dict:
    """
    Produce realistic-looking sensor readings using slow sine-wave drift
    overlaid with random noise, plus occasional spike events.

    Replace this function body with real hardware reads when available.
    """
    state = _spike_state
    state["counter"] += 1
    t = state["counter"]

    # Random spike: ~8 % chance per tick that a new spike starts
    if state["ttl"] <= 0 and random.random() < 0.08:
        state["type"] = random.choice(["temp", "vib", "both"])
        state["ttl"]  = random.randint(2, 5)
    elif state["ttl"] > 0:
        state["ttl"] -= 1
    else:
        state["type"] = None

    # --- Temperature ---
    base_temp = 34.0 + 6.0 * math.sin(t / 30.0)   # slow diurnal cycle
    noise_t   = random.gauss(0, 0.6)
    if state["type"] in ("temp", "both"):
        temp = round(46.5 + random.uniform(0, 4.0) + noise_t, 2)
    else:
        temp = round(max(25.0, min(44.9, base_temp + noise_t)), 2)

    # --- Vibration ---
    base_vib = 1.8 + 0.8 * math.sin(t / 12.0)
    noise_v  = random.gauss(0, 0.18)
    if state["type"] in ("vib", "both"):
        vib = round(4.2 + random.uniform(0, 1.5) + abs(noise_v), 2)
    else:
        vib = round(max(0.1, min(3.95, base_vib + noise_v)), 2)

    # --- Strain (microstrain) ---
    base_strain = 48.0 + 15.0 * math.sin(t / 20.0 + 1.2)
    noise_s     = random.gauss(0, 2.5)
    strain      = round(max(10.0, min(95.0, base_strain + noise_s)), 2)

    # --- Derived / meta ---
    humidity    = round(55.0 + 20.0 * math.sin(t / 45.0) + random.gauss(0, 1.5), 1)
    wind_speed  = round(max(0.0, 3.5 + 2.5 * math.sin(t / 18.0) + random.gauss(0, 0.4)), 1)

    return {
        "temperature" : temp,
        "vibration"   : vib,
        "strain"      : strain,
        "humidity"    : humidity,
        "wind_speed"  : wind_speed,
    }


# ─────────────────────────────────────────────
#  ANOMALY DETECTION ENGINE
# ─────────────────────────────────────────────
def detect_anomalies(reading: dict) -> dict:
    """
    Rule-based anomaly detection (stage 1).
    Replace / augment with ML model output (e.g. Isolation Forest)
    when running on real hardware.

    Returns a status block with severity, active triggers, and a score.
    """
    temp   = reading.get("temperature", 0)
    vib    = reading.get("vibration",   0)
    strain = reading.get("strain",      0)

    triggers = []
    severity = "NORMAL"

    if temp > TEMP_THRESHOLD:
        triggers.append({
            "sensor"    : "temperature",
            "value"     : temp,
            "threshold" : TEMP_THRESHOLD,
            "message"   : f"High temperature {temp}°C — thermal stress on cables (Zone-A)",
        })
        severity = "ALERT"

    if vib > VIB_THRESHOLD:
        triggers.append({
            "sensor"    : "vibration",
            "value"     : vib,
            "threshold" : VIB_THRESHOLD,
            "message"   : f"High vibration {vib} m/s² — possible structural resonance (Zone-B)",
        })
        severity = "ALERT"

    if strain > 85.0:
        triggers.append({
            "sensor"    : "strain",
            "value"     : strain,
            "threshold" : 85.0,
            "message"   : f"Elevated strain {strain} με — inspect main girder (Zone-C)",
        })
        if severity != "ALERT":
            severity = "WARNING"

    # Anomaly score: 0.0 (healthy) → 1.0 (critical)
    score = round(
        min(1.0, (
            max(0, (temp   - 30)  / (TEMP_THRESHOLD - 30)) * 0.4 +
            max(0, (vib    - 1.0) / (VIB_THRESHOLD  - 1.0)) * 0.4 +
            max(0, (strain - 40)  / 60.0) * 0.2
        )), 3
    )

    return {
        "status"    : severity,
        "score"     : score,
        "triggers"  : triggers,
    }


# ─────────────────────────────────────────────
#  HELPERS
# ─────────────────────────────────────────────
def _build_response(sensor_data: dict) -> dict:
    """Merge sensor data, anomaly results and metadata into one payload."""
    anomaly   = detect_anomalies(sensor_data)
    timestamp = datetime.now(timezone.utc).isoformat()

    payload = {
        # Core sensor readings (used by frontend cards)
        "temperature" : sensor_data["temperature"],
        "vibration"   : sensor_data["vibration"],
        "strain"      : sensor_data["strain"],
        "humidity"    : sensor_data.get("humidity",   0),
        "wind_speed"  : sensor_data.get("wind_speed", 0),

        # Anomaly detection output
        "status"   : anomaly["status"],
        "score"    : anomaly["score"],
        "triggers" : anomaly["triggers"],

        # Metadata
        "timestamp"    : timestamp,
        "source"       : "simulated" if USE_SIMULATED else "hardware",
        "node_id"      : "RPI-EDGE-01",
        "structure_id" : "BRIDGE-001",
    }

    # Push to history buffer (strip triggers for compactness)
    history.append({
        "t"   : timestamp,
        "tmp" : sensor_data["temperature"],
        "vib" : sensor_data["vibration"],
        "str" : sensor_data["strain"],
        "sts" : anomaly["status"],
    })

    return payload


# ─────────────────────────────────────────────
#  ROUTES
# ─────────────────────────────────────────────

@app.route("/api/data", methods=["GET"])
def get_data():
    """
    Primary endpoint consumed by the frontend every 2–3 s.

    Returns the latest sensor reading + anomaly analysis.
    When USE_SIMULATED is True, fresh data is generated on each call.
    When False, returns the last reading received via POST /api/sensor.
    """
    if USE_SIMULATED:
        sensor_data = _simulate_sensors()
    else:
        if not latest_reading:
            return jsonify({"error": "No sensor data received yet from hardware."}), 503
        sensor_data = latest_reading.copy()

    payload = _build_response(sensor_data)
    log.info(
        "GET /api/data  status=%-7s  T=%.1f°C  V=%.2f m/s²  S=%.1fμε",
        payload["status"], payload["temperature"],
        payload["vibration"], payload["strain"],
    )
    return jsonify(payload), 200


@app.route("/api/sensor", methods=["POST"])
def receive_sensor():
    """
    Hardware ingest endpoint.

    ESP32 / Raspberry Pi firmware should POST JSON here:
    {
        "temperature": <float>,
        "vibration"  : <float>,
        "strain"     : <float>,
        "humidity"   : <float, optional>,
        "wind_speed" : <float, optional>
    }

    To activate: set USE_SIMULATED = False at the top of this file.
    The frontend will automatically start reading real values.
    """
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "Invalid JSON body"}), 400

    required = {"temperature", "vibration", "strain"}
    missing  = required - body.keys()
    if missing:
        return jsonify({"error": f"Missing fields: {missing}"}), 422

    try:
        latest_reading["temperature"] = float(body["temperature"])
        latest_reading["vibration"]   = float(body["vibration"])
        latest_reading["strain"]      = float(body["strain"])
        latest_reading["humidity"]    = float(body.get("humidity",   0))
        latest_reading["wind_speed"]  = float(body.get("wind_speed", 0))
    except (ValueError, TypeError) as exc:
        return jsonify({"error": f"Invalid value: {exc}"}), 422

    anomaly = detect_anomalies(latest_reading)
    log.info(
        "POST /api/sensor  status=%-7s  T=%.1f  V=%.2f  S=%.1f",
        anomaly["status"],
        latest_reading["temperature"],
        latest_reading["vibration"],
        latest_reading["strain"],
    )
    return jsonify({
        "message"   : "Reading accepted",
        "status"    : anomaly["status"],
        "score"     : anomaly["score"],
        "timestamp" : datetime.now(timezone.utc).isoformat(),
    }), 201


@app.route("/api/history", methods=["GET"])
def get_history():
    """
    Returns the last N readings for chart rendering.
    Query param: ?limit=30  (default 30, max HISTORY_SIZE)
    """
    limit = min(int(request.args.get("limit", 30)), HISTORY_SIZE)
    data  = list(history)[-limit:]
    return jsonify({"count": len(data), "history": data}), 200


@app.route("/api/status", methods=["GET"])
def health_check():
    """Quick health / heartbeat endpoint for the frontend connection indicator."""
    return jsonify({
        "online"       : True,
        "mode"         : "simulated" if USE_SIMULATED else "hardware",
        "node_id"      : "RPI-EDGE-01",
        "structure_id" : "BRIDGE-001",
        "readings"     : len(history),
        "uptime_s"     : round(time.monotonic(), 1),
    }), 200


# ─────────────────────────────────────────────
#  ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    log.info("=" * 54)
    log.info("  Smart SHM Backend  v1.0.0")
    log.info("  Mode     : %s", "SIMULATED" if USE_SIMULATED else "HARDWARE")
    log.info("  Endpoint : http://127.0.0.1:5000/api/data")
    log.info("=" * 54)
    app.run(host="0.0.0.0", port=5000, debug=True)
