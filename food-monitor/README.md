# Food Delivery IoT Monitor

## Project Overview

A real-time IoT monitoring system for food delivery operations. An ESP32 microcontroller
installed in the delivery box continuously reads temperature, humidity, gas concentration
(MQ2), and ambient light (KY-018), publishing data over MQTT. In parallel, the delivery
person's phone streams GPS coordinates via WebSocket. Both streams are ingested by
Node-RED, stored in MySQL, and visualised on a Flask dashboard with a live Leaflet map,
Plotly sensor charts, and a **Freshness Score** (0–100) that reflects food safety conditions
throughout the journey.

---

## Architecture

```
┌──────────────┐   MQTT /transport/{id}/env   ┌────────────┐
│  ESP32       │──────────────────────────────▶│            │
│  DHT11       │                               │  Node-RED  │──▶ MySQL (env_data)
│  MQ2         │                               │            │
│  KY-018      │                               │            │──▶ MySQL (gps_data)
└──────────────┘                               │            │
                                               │            │◀── HTTP GET /tracker
┌──────────────┐  WebSocket ws://host:1880/ws/gps            │
│ Phone        │──────────────────────────────▶│            │
│ GPS Tracker  │                               └────────────┘
└──────────────┘
                                                     │
                                                     ▼
                                               ┌──────────────┐
                                               │  MySQL DB    │
                                               │  b6810045589 │
                                               │  env_data    │
                                               │  gps_data    │
                                               │  freshness_  │
                                               │  score VIEW  │
                                               └──────┬───────┘
                                                      │
                                                      ▼
                                               ┌──────────────┐
                                               │  Flask API   │
                                               │  :5000       │
                                               └──────┬───────┘
                                                      │
                                                      ▼
                                               ┌──────────────┐
                                               │  Dashboard   │
                                               │  Leaflet map │
                                               │  Plotly      │
                                               └──────────────┘
```

---

## Prerequisites

### Node-RED
```bash
npm install -g --unsafe-perm node-red
# Install MySQL and WebSocket palette nodes:
# In Node-RED → Manage Palette → Install:
#   node-red-node-mysql
#   node-red-contrib-websocket   (bundled in most installs)
```

### Mosquitto MQTT Broker
```bash
# Ubuntu / Debian
sudo apt install mosquitto mosquitto-clients
sudo systemctl start mosquitto

# macOS
brew install mosquitto
brew services start mosquitto

# Windows: download installer from https://mosquitto.org/download/
```

### MySQL
Use the university server `iot.cpe.ku.ac.th:3306` with your credentials,
or install locally:
```bash
sudo apt install mysql-server   # Ubuntu
brew install mysql              # macOS
```

### Python 3.x
```bash
pip install flask mysql-connector-python flask-swagger-ui
```

### MicroPython on ESP32
```bash
pip install esptool

# Erase and flash MicroPython firmware (replace PORT and FIRMWARE):
esptool.py --port /dev/ttyUSB0 erase_flash
esptool.py --chip esp32 --port /dev/ttyUSB0 write_flash -z 0x1000 esp32-micropython.bin

# Official firmware: https://micropython.org/download/esp32/
# Upload main.py with ampy or Thonny IDE:
pip install adafruit-ampy
ampy --port /dev/ttyUSB0 put firmware/main.py
```

---

## Setup — Step by Step

**1. Clone the repository**
```bash
git clone <repo-url>
cd food-monitor
```

**2. Create the database**
```bash
mysql -h iot.cpe.ku.ac.th -u b6810045589 -p b6810045589 < db/schema.sql
```

**3. Start Mosquitto**
```bash
mosquitto -v            # foreground, or:
sudo systemctl start mosquitto
```

**4. Start Node-RED and import the flow**
```bash
node-red
# Open http://localhost:1880
# Menu → Import → paste contents of nodered/flows.json
# Configure MySQL node with your DB password
# Deploy
```

**5. Configure firmware credentials**
```bash
cp .env.example .env
# Edit .env with your WiFi SSID/password and DB password
# Then update firmware/main.py constants:
#   WIFI_SSID, WIFI_PASSWORD, MQTT_BROKER, TRANSPORTER_ID
```

**6. Flash the ESP32**
```bash
ampy --port /dev/ttyUSB0 put firmware/main.py
# Reset the ESP32; check serial monitor for connection logs
```

**7. Start Flask**
```bash
cd api
pip install -r requirements.txt
python app.py
# Dashboard available at http://localhost:5000
```

**8. Open tracker on the delivery phone**
```
http://<your-computer-ip>:1880/tracker?id=1
# Replace <your-computer-ip> with your LAN IP
# Tap "Start Tracking"
```

**9. Open the dashboard**
```
http://localhost:5000
```

---

## API Reference

| Method | Endpoint | Description | Example response |
|--------|----------|-------------|-----------------|
| GET | `/` | Serves the dashboard HTML | — |
| GET | `/api/deliveries` | Last GPS + env for each active transporter | `[{"transporter_id":1,"lat":13.85,"lon":100.57,...}]` |
| GET | `/api/deliveries/<id>/live` | Current position, speed (m/s), next 3 route points | `{"lat":13.85,"speed_ms":3.2,"next_points":[...]}` |
| GET | `/api/deliveries/<id>/env?limit=200` | Sensor history (latest N readings) | `{"data":[{"humidity":72,"temperature":28,...}]}` |
| GET | `/api/deliveries/<id>/score` | Freshness score + component breakdown | `{"score":78.5,"avg_gas_ppm":120,"components":{...}}` |
| GET | `/api/fleet/stats` | Fleet averages over last 30 minutes | `{"active_transporters":3,"avg_humidity":68,...}` |
| GET | `/api/fleet/history` | Hourly averages over 24 hours | `[{"hour":"2024-01-01 10:00:00","avg_humidity":70,...}]` |
| GET | `/api/fleet/sources` | GPS point count by source | `[{"source":"phone","count":412}]` |
| GET | `/api/spec` | OpenAPI 3.0 specification JSON | Full spec object |

---

## Data Sources

### Primary — ESP32 sensors (MQTT)
- **DHT11** on GPIO 32 → humidity (%) and temperature (°C)
- **MQ2** AOUT on GPIO 34 → gas concentration (ppm, raw ADC) + DOUT on GPIO 9 → binary alert
- **KY-018** on GPIO 33 → ambient brightness (lux-equivalent, raw ADC)

Published every 10 s to `/transport/{id}/env` on the local MQTT broker.
Node-RED ingests and inserts into `env_data`.

### Secondary — Phone GPS (WebSocket)
Follows the **Realtime-Location-Tracker** pattern: the delivery person opens
`/tracker?id=N` in their mobile browser, which calls `navigator.geolocation.watchPosition`
and streams `{lat, lng, accuracy, timestamp}` every 5 s over a persistent WebSocket
to Node-RED (`ws://host:1880/ws/gps`). Node-RED inserts rows into `gps_data`.

---

## Freshness Score

The Freshness Score is a 0–100 index computed per transporter over the **last 60 minutes**
of sensor readings:

```
score = 100
      − (avg_gas_ppm / 10)                         ← gas penalty (0–40)
      − MAX(0, avg_humidity − 65) × 0.5            ← excess humidity penalty
      − gas_alert_count × 2                        ← digital alert count penalty
```

| Component | What it measures | Impact |
|-----------|-----------------|--------|
| `avg_gas_ppm / 10` | Smoke, combustible gas, or spoilage odours | Up to −40 points |
| `MAX(0, avg_humidity−65) × 0.5` | Excess moisture that accelerates spoilage | Variable |
| `gas_alert_count × 2` | Number of times the MQ2 DOUT threshold was exceeded | −2 per alert |

A score ≥ 70 is **green** (safe), 40–70 is **orange** (monitor), < 40 is **red** (at risk).
