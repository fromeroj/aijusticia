#!/bin/bash
# backups_retention.sh - keep the newest N AIJusticia dumps in /srv/backups.
# Never prunes a file that was touched in the last 2 hours (that one is being
# written by an rsync replica right now).
set -u
DIR=/srv/backups
KEEP=${KEEP:-10}
LOG=/var/log/backups_retention.log
log() { echo "[$(date -u +%FT%TZ)] $*" >> "$LOG"; }

files=$(ls -1t "$DIR"/aijusticia_*.sql.gz 2>/dev/null)
total=$(printf "%s\n" "$files" | grep -c . )
[ "$total" -le "$KEEP" ] && { log "nothing to prune ($total files, keep $KEEP)"; exit 0; }

n=0
for f in $files; do
  n=$((n+1))
  [ "$n" -le "$KEEP" ] && continue
  mt=$(stat -c %Y "$f" 2>/dev/null || echo 0)
  age=$(( $(date +%s) - mt ))
  if [ "$age" -lt 7200 ]; then
    log "skip (in flight, ${age}s old): $(basename "$f")"
    continue
  fi
  sz=$(stat -c%s "$f" 2>/dev/null || echo 0)
    # keep the newest N, drop the rest
  if rm -f -- "$f"; then
    log "pruned $(basename "$f") ($((sz/1024/1024)) MB)"
  else
    log "FAILED to prune $(basename "$f")"
  fi
done

left=$(ls -1 "$DIR"/aijusticia_*.sql.gz 2>/dev/null | wc -l)
log "done: $left dumps remain (kept $KEEP)"
