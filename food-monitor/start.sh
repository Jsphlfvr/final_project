#!/usr/bin/env bash
# ============================================================
# start.sh — Launch Flask API only (Node-RED & MQTT are remote)
# ============================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"
LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$PID_DIR" "$LOG_DIR"

# ── Helper ───────────────────────────────────────────────────
pid_file() { echo "$PID_DIR/$1.pid"; }

is_running() {
  local pid_f="$(pid_file "$1")"
  [ -f "$pid_f" ] && kill -0 "$(cat "$pid_f")" 2>/dev/null
}

# ── Flask API ────────────────────────────────────────────────
if is_running flask; then
  echo "[flask] Already running (PID $(cat "$(pid_file flask)"))"
else
  echo "[flask] Starting..."
  cd "$SCRIPT_DIR/api"

  # Load .env if present
  if [ -f "$SCRIPT_DIR/.env" ]; then
    set -a; source "$SCRIPT_DIR/.env"; set +a
    echo "[flask] Loaded .env"
  fi

  python app.py > "$LOG_DIR/flask.log" 2>&1 &
  echo $! > "$(pid_file flask)"
  echo "[flask] PID $!"

  cd "$SCRIPT_DIR"
fi

echo ""
echo "=== Service started ==="
echo "  Flask API : http://localhost:5000   (logs/flask.log)"
echo ""
echo "External services:"
echo "  Node-RED : https://iot.cpe.ku.ac.th/red/b6810045589/"
echo "  MQTT     : iot.cpe.ku.ac.th:1883"
echo ""
echo "Stop with: bash stop.sh"