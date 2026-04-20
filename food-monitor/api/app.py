import os
import math
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
load_dotenv()

import mysql.connector
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

# ── Database config (reads from environment, falls back to defaults) ─────────
DB_CONFIG = {
    "host":     os.environ.get("DB_HOST",     "iot.cpe.ku.ac.th"),
    "port":     int(os.environ.get("DB_PORT", "3306")),
    "database": os.environ.get("DB_NAME",     "b6810045589"),
    "user":     os.environ.get("DB_USER",     "b6810045589"),
    "password": os.environ.get("DB_PASSWORD", ""),
}


def get_conn():
    return mysql.connector.connect(**DB_CONFIG)


def haversine(lat1, lon1, lat2, lon2):
    """Return distance in metres between two GPS coordinates."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _serialize(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Not serializable: {type(obj)}")


def jsonify_safe(data):
    return app.response_class(
        json.dumps(data, default=_serialize),
        mimetype="application/json"
    )


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/deliveries")
def deliveries():
    """Last GPS position + last env reading for each active transporter."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT g.transporter_id, g.lat, g.longitude AS lon, g.received_at AS gps_at
        FROM gps_data g
        INNER JOIN (
            SELECT transporter_id, MAX(received_at) AS latest
            FROM gps_data
            WHERE received_at >= NOW() - INTERVAL 1 HOUR
            GROUP BY transporter_id
        ) latest ON g.transporter_id = latest.transporter_id
                 AND g.received_at    = latest.latest
    """)
    gps_rows = {r["transporter_id"]: r for r in cur.fetchall()}

    cur.execute("""
        SELECT e.transporter_id, e.humidity, e.temperature,
               e.gas_concentration, e.brightness, e.gas_alert, e.received_at AS env_at
        FROM env_data e
        INNER JOIN (
            SELECT transporter_id, MAX(received_at) AS latest
            FROM env_data
            WHERE received_at >= NOW() - INTERVAL 1 HOUR
            GROUP BY transporter_id
        ) latest ON e.transporter_id = latest.transporter_id
                 AND e.received_at    = latest.latest
    """)
    env_rows = {r["transporter_id"]: r for r in cur.fetchall()}

    cur.close(); conn.close()

    all_ids = set(gps_rows) | set(env_rows)
    result = []
    for tid in sorted(all_ids):
        row = {"transporter_id": tid}
        row.update(gps_rows.get(tid, {}))
        row.update(env_rows.get(tid, {}))
        result.append(row)

    return jsonify_safe(result)


@app.route("/api/deliveries/<int:tid>/live")
def delivery_live(tid):
    """Current position, instantaneous speed, distances to next 3 route points."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)

    cur.execute("""
        SELECT lat, longitude AS lon, received_at, gps_timestamp
        FROM gps_data
        WHERE transporter_id = %s
        ORDER BY received_at DESC
        LIMIT 5
    """, (tid,))
    rows = cur.fetchall()
    cur.close(); conn.close()

    if not rows:
        return jsonify_safe({"error": "no data"}), 404

    current = rows[0]
    speed_ms = None
    if len(rows) >= 2:
        prev = rows[1]
        dist = haversine(prev["lat"], prev["lon"], current["lat"], current["lon"])
        dt_s = (current["received_at"] - prev["received_at"]).total_seconds()
        speed_ms = round(dist / dt_s, 2) if dt_s > 0 else 0

    # Distances from current to next N points (historical path as proxy)
    next_points = rows[1:4]
    distances = []
    for pt in next_points:
        d = haversine(current["lat"], current["lon"], pt["lat"], pt["lon"])
        distances.append({"lat": pt["lat"], "lon": pt["lon"], "distance_m": round(d, 1)})

    return jsonify_safe({
        "transporter_id": tid,
        "lat":    current["lat"],
        "lon":    current["lon"],
        "at":     current["received_at"],
        "speed_ms": speed_ms,
        "next_points": distances,
    })


@app.route("/api/deliveries/<int:tid>/env")
def delivery_env(tid):
    """Sensor history for a transporter. ?limit=200"""
    limit = min(int(request.args.get("limit", 200)), 1000)
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT humidity, temperature, gas_concentration, gas_raw,
               gas_alert, brightness, ldr_raw, received_at
        FROM env_data
        WHERE transporter_id = %s
        ORDER BY received_at DESC
        LIMIT %s
    """, (tid, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify_safe({"transporter_id": tid, "data": rows})


@app.route("/api/deliveries/<int:tid>/score")
def delivery_score(tid):
    """Freshness score + component breakdown for a transporter."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT score
        FROM env_data
        WHERE transporter_id = %s
    """, (tid,))
    row = cur.fetchone()
    cur.close(); conn.close()

    if not row:
        return jsonify_safe({"error": "no data in last hour"}), 404

    row["components"] = {
        "gas_penalty":      round(float(row["avg_gas_ppm"] or 0) / 10, 2),
        "humidity_penalty": round(max(0, float(row["avg_humidity"] or 0) - 65) * 0.5, 2),
        "alert_penalty":    int(row["gas_alert_count"] or 0) * 2,
    }
    return jsonify_safe(row)


@app.route("/api/fleet/stats")
def fleet_stats():
    """Global averages over the last 30 minutes."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
            COUNT(DISTINCT transporter_id) AS active_transporters,
            ROUND(AVG(humidity), 1)          AS avg_humidity,
            ROUND(AVG(temperature), 1)       AS avg_temperature,
            ROUND(AVG(gas_concentration), 0) AS avg_gas_ppm,
            ROUND(AVG(brightness), 1)        AS avg_brightness
        FROM env_data
        WHERE received_at >= NOW() - INTERVAL 30 MINUTE
    """)
    row = cur.fetchone()
    cur.close(); conn.close()
    return jsonify_safe(row)


@app.route("/api/fleet/history")
def fleet_history():
    """Hourly averages over the last 24 hours."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT
            DATE_FORMAT(received_at, '%Y-%m-%d %H:00:00') AS hour,
            ROUND(AVG(humidity), 1)          AS avg_humidity,
            ROUND(AVG(temperature), 1)       AS avg_temperature,
            ROUND(AVG(gas_concentration), 0) AS avg_gas_ppm,
            ROUND(AVG(brightness), 1)        AS avg_brightness,
            COUNT(*)                         AS reading_count
        FROM env_data
        WHERE received_at >= NOW() - INTERVAL 24 HOUR
        GROUP BY hour
        ORDER BY hour ASC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify_safe(rows)


@app.route("/api/deliveries/<int:tid>/gps")
def delivery_gps(tid):
    """GPS track (ordered ASC) for polyline rendering. ?limit=200"""
    limit = min(int(request.args.get("limit", 200)), 2000)
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT lat, longitude AS lon, received_at, gps_timestamp
        FROM gps_data
        WHERE transporter_id = %s
        ORDER BY received_at ASC
        LIMIT %s
    """, (tid, limit))
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify_safe({"transporter_id": tid, "track": rows})


@app.route("/api/fleet/sources")
def fleet_sources():
    """Count of GPS points per source."""
    conn = get_conn()
    cur = conn.cursor(dictionary=True)
    cur.execute("""
        SELECT source, COUNT(*) AS count
        FROM gps_data
        GROUP BY source
        ORDER BY count DESC
    """)
    rows = cur.fetchall()
    cur.close(); conn.close()
    return jsonify_safe(rows)


@app.route("/api/spec")
def api_spec():
    """OpenAPI 3.0 specification."""
    spec = {
        "openapi": "3.0.0",
        "info": {
            "title": "Food Delivery IoT Monitor API",
            "version": "1.0.0",
            "description": "REST API for real-time food delivery monitoring dashboard"
        },
        "paths": {
            "/api/deliveries": {
                "get": {
                    "summary": "List active deliveries",
                    "description": "Last GPS + env reading for each transporter active in the last hour",
                    "responses": {"200": {"description": "Array of delivery objects"}}
                }
            },
            "/api/deliveries/{id}/live": {
                "get": {
                    "summary": "Live position and speed",
                    "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {"200": {"description": "Current lat/lon, speed_ms, next_points"}}
                }
            },
            "/api/deliveries/{id}/env": {
                "get": {
                    "summary": "Sensor history",
                    "parameters": [
                        {"name": "id",    "in": "path",  "required": True,  "schema": {"type": "integer"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "default": 200}}
                    ],
                    "responses": {"200": {"description": "Array of sensor readings"}}
                }
            },
            "/api/deliveries/{id}/score": {
                "get": {
                    "summary": "Freshness score",
                    "parameters": [{"name": "id", "in": "path", "required": True, "schema": {"type": "integer"}}],
                    "responses": {"200": {"description": "Score 0-100 with component breakdown"}}
                }
            },
            "/api/fleet/stats": {
                "get": {
                    "summary": "Fleet averages (last 30 min)",
                    "responses": {"200": {"description": "Aggregated env stats"}}
                }
            },
            "/api/fleet/history": {
                "get": {
                    "summary": "Hourly history (24h)",
                    "responses": {"200": {"description": "Hourly averages array"}}
                }
            },
            "/api/deliveries/{id}/gps": {
                "get": {
                    "summary": "GPS track (ordered ASC for polyline)",
                    "parameters": [
                        {"name": "id",    "in": "path",  "required": True,  "schema": {"type": "integer"}},
                        {"name": "limit", "in": "query", "required": False, "schema": {"type": "integer", "default": 200}}
                    ],
                    "responses": {"200": {"description": "track array of {lat, lon, received_at}"}}
                }
            },
            "/api/fleet/sources": {
                "get": {
                    "summary": "GPS source counts",
                    "responses": {"200": {"description": "Count per source"}}
                }
            },
        }
    }
    return jsonify(spec)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
