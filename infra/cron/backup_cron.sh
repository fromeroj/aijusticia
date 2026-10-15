#!/bin/bash
# Backup diario DB prod (04:00 UTC)
cd /opt/aijusticia/engine
bash scripts/ingestion/backup_db.sh >> /var/log/aijusticia_backup.log 2>&1
