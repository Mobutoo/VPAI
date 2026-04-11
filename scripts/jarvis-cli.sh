#!/usr/bin/env bash
# jarvis — CLI to manage the Jarvis Bridge daemon
# Install: sudo cp jarvis /usr/local/bin/ && sudo chmod +x /usr/local/bin/jarvis

set -euo pipefail

JARVIS_HOME="/home/mobuone/jarvis"
SERVICE="jarvis-bridge"
VENV="${JARVIS_HOME}/.venv/bin"

usage() {
    cat <<EOF
Usage: jarvis <command>

Commands:
  start       Start the daemon (systemd)
  stop        Stop the daemon
  restart     Restart the daemon
  status      Show daemon status
  logs        Tail daemon logs (journalctl)
  run         Run in foreground (for debugging)
  test        Run pytest suite
  install     Install systemd service + logrotate
  health      Check health endpoint
  update      Git pull + reinstall deps

EOF
}

case "${1:-}" in
    start)
        sudo systemctl start "$SERVICE"
        echo "Jarvis Bridge started."
        systemctl --no-pager status "$SERVICE" | head -5
        ;;
    stop)
        sudo systemctl stop "$SERVICE"
        echo "Jarvis Bridge stopped."
        ;;
    restart)
        sudo systemctl restart "$SERVICE"
        echo "Jarvis Bridge restarted."
        systemctl --no-pager status "$SERVICE" | head -5
        ;;
    status)
        systemctl --no-pager status "$SERVICE" 2>/dev/null || echo "Service not running."
        echo "---"
        curl -sf http://127.0.0.1:5000/health 2>/dev/null | python3 -m json.tool || echo "Health endpoint not reachable."
        ;;
    logs)
        journalctl -u "$SERVICE" -f --no-pager -n "${2:-50}"
        ;;
    run)
        echo "Running Jarvis Bridge in foreground (Ctrl+C to stop)..."
        cd "$JARVIS_HOME"
        exec "${VENV}/python" -m bridge.main
        ;;
    test)
        cd "$JARVIS_HOME"
        exec "${VENV}/python" -m pytest tests/ -v --tb=short
        ;;
    install)
        echo "Installing Jarvis Bridge systemd service..."
        sudo mkdir -p /var/log/jarvis-bridge
        sudo chown mobuone:mobuone /var/log/jarvis-bridge
        sudo cp "${JARVIS_HOME}/jarvis-bridge.service" /etc/systemd/system/
        sudo cp "${JARVIS_HOME}/jarvis-logrotate.conf" /etc/logrotate.d/jarvis-bridge
        sudo systemctl daemon-reload
        sudo systemctl enable "$SERVICE"
        echo "Done. Run 'jarvis start' to start."
        ;;
    health)
        curl -sf http://127.0.0.1:5000/health | python3 -m json.tool
        ;;
    update)
        cd "$JARVIS_HOME"
        git pull
        "${VENV}/pip" install -r requirements.txt --quiet
        echo "Updated. Run 'jarvis restart' to apply."
        ;;
    *)
        usage
        exit 1
        ;;
esac
