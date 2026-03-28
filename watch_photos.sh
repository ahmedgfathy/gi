#!/usr/bin/env bash
# ── Photo Watcher ──────────────────────────────────────
# Start:  bash ~/gi/watch_photos.sh start
# Stop:   bash ~/gi/watch_photos.sh stop
# Status: bash ~/gi/watch_photos.sh status

PIDFILE=~/gi/.watcher.pid
VENV=~/gi/.venv/bin/python
SCRIPT=~/gi/photo_watcher.py

case "$1" in
  start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; then
      echo "Watcher already running (PID $(cat $PIDFILE))"
    else
      nohup "$VENV" "$SCRIPT" >> ~/gi/watcher_console.log 2>&1 &
      echo $! > "$PIDFILE"
      echo "Watcher started (PID $!)"
      echo "  Log: /mnt/c/photo/watcher.log"
    fi
    ;;
  stop)
    if [ -f "$PIDFILE" ]; then
      kill "$(cat $PIDFILE)" && echo "Watcher stopped." && rm "$PIDFILE"
    else
      echo "Watcher is not running."
    fi
    ;;
  status)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; then
      echo "Watcher is RUNNING (PID $(cat $PIDFILE))"
    else
      echo "Watcher is STOPPED"
    fi
    ;;
  *)
    echo "Usage: bash watch_photos.sh {start|stop|status}"
    ;;
esac
