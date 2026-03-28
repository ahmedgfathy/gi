#!/usr/bin/env bash
# Content Classifier Watcher — classifies images in /mnt/c/photo/Images/ by subject
# Usage:
#   bash ~/gi/watch_content.sh start
#   bash ~/gi/watch_content.sh stop
#   bash ~/gi/watch_content.sh status
#   bash ~/gi/watch_content.sh log        # tail the log file

PIDFILE=~/gi/.content_watcher.pid
VENV=~/gi/.venv/bin/python
SCRIPT=~/gi/content_watcher.py
LOGFILE=/mnt/c/photo/Images/content_watcher.log

case "$1" in
  start)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; then
      echo "Content watcher already running (PID $(cat $PIDFILE))"
    else
      nohup "$VENV" "$SCRIPT" >> ~/gi/content_watcher_console.log 2>&1 &
      echo $! > "$PIDFILE"
      echo "Content watcher started (PID $!)"
      echo "  Classifying: People / Animals / Documents / Nature / Food / Vehicles / Architecture / Other"
      echo "  Log: $LOGFILE"
    fi
    ;;
  stop)
    if [ -f "$PIDFILE" ]; then
      kill "$(cat $PIDFILE)" && echo "Content watcher stopped." && rm "$PIDFILE"
    else
      echo "Content watcher is not running."
    fi
    ;;
  status)
    if [ -f "$PIDFILE" ] && kill -0 "$(cat $PIDFILE)" 2>/dev/null; then
      echo "Content watcher is RUNNING (PID $(cat $PIDFILE))"
    else
      echo "Content watcher is STOPPED"
    fi
    ;;
  log)
    tail -f "$LOGFILE"
    ;;
  *)
    echo "Usage: bash watch_content.sh {start|stop|status|log}"
    ;;
esac
