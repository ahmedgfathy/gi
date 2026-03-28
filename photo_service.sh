#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# photo_service.sh  —  Unified Photo Service control
# Replaces: photo_watcher.py + content_watcher.py
# Pipeline: new file  →  dedup  →  classify  →  subfolder
#
# Usage:
#   bash ~/gi/photo_service.sh start
#   bash ~/gi/photo_service.sh stop
#   bash ~/gi/photo_service.sh restart
#   bash ~/gi/photo_service.sh status
#   bash ~/gi/photo_service.sh log        # live log tail
# ─────────────────────────────────────────────────────────────

PIDFILE=~/gi/.photo_service.pid
VENV=~/gi/.venv/bin/python
SCRIPT=~/gi/photo_service.py
CONSOLE=~/gi/photo_service_console.log
LOGFILE=/mnt/c/photo/photo_service.log

stop_old() {
  for pid_file in ~/gi/.watcher.pid ~/gi/.content_watcher.pid; do
    if [ -f "$pid_file" ] && kill -0 "$(cat $pid_file)" 2>/dev/null; then
      kill "$(cat $pid_file)" 2>/dev/null
      rm -f "$pid_file"
      echo "  Stopped old watcher: $(basename $pid_file .pid)"
    fi
  done
}

case "$1" in
  start)
    stop_old
    if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; then
      echo "Photo Service already running (PID $(cat $PIDFILE))"
    else
      nohup "$VENV" "$SCRIPT" >> "$CONSOLE" 2>&1 &
      echo $! > "$PIDFILE"
      echo "Photo Service started (PID $!)"
      echo "  Pipeline : new file → dedup (SHA256) → CLIP classify → subfolder"
      echo "  Log      : $LOGFILE"
      echo "  Console  : $CONSOLE"
    fi
    ;;
  stop)
    if [ -f "$PIDFILE" ]; then
      kill "$(cat $PIDFILE)" && echo "Photo Service stopped." && rm "$PIDFILE"
    else
      echo "Photo Service is not running."
    fi
    ;;
  restart)
    bash "$0" stop
    sleep 2
    bash "$0" start
    ;;
  status)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; then
      echo "Photo Service is RUNNING (PID $(cat $PIDFILE))"
      echo "  Log: $LOGFILE"
    else
      echo "Photo Service is STOPPED"
      echo "  Start with: bash ~/gi/photo_service.sh start"
    fi
    ;;
  log)
    tail -f "$LOGFILE"
    ;;
  *)
    echo "Usage: bash photo_service.sh {start|stop|restart|status|log}"
    ;;
esac
