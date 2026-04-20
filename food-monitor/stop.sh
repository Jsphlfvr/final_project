#!/usr/bin/env bash
# ============================================================
# stop.sh — Gracefully stop Mosquitto, Node-RED, and Flask
# Usage: bash stop.sh
# ============================================================

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PID_DIR="$SCRIPT_DIR/.pids"

# ── Helper ───────────────────────────────────────────────────
stop_service() {
  local name="$1"
  local pid_file="$PID_DIR/$name.pid"

  if [ ! -f "$pid_file" ]; then
    echo "[$name] No PID file found — may not be running"
    return
  fi

  local pid
  pid="$(cat "$pid_file")"

  if kill -0 "$pid" 2>/dev/null; then
    echo "[$name] Sending SIGTERM to PID $pid..."
    kill "$pid"
    # Wait up to 5 s for clean shutdown
    for i in $(seq 1 10); do
      sleep 0.5
      kill -0 "$pid" 2>/dev/null || break
    done
    # Force-kill if still alive
    if kill -0 "$pid" 2>/dev/null; then
      echo "[$name] Still running — sending SIGKILL"
      kill -9 "$pid" 2>/dev/null || true
    fi
    echo "[$name] Stopped"
  else
    echo "[$name] PID $pid not found (already stopped)"
  fi

  rm -f "$pid_file"
}

# ── Stop in reverse startup order ────────────────────────────
stop_service flask
stop_service nodered
stop_service mosquitto

echo ""
echo "=== All services stopped ==="
