#!/bin/bash
# Auto-ingesta SIVEPJ: cada 20 min sube los JSONL y ingiere solo lo nuevo (idempotente).
set -u
cd "$HOME/workspace/aijusticia"
while true; do
  for f in engine/data/sivepj_sentencias_*.jsonl; do
    [ -s "$f" ] && rsync -e "ssh -o ConnectTimeout=15" -q --append "$f" root@182.255.84.124:/opt/aijusticia/corpus_downloads/sivepj/ 2>/dev/null
  done
  ssh -o ConnectTimeout=15 root@182.255.84.124 '/opt/aijusticia/engine/.venv/bin/python /opt/aijusticia/corpus_downloads/sivepj/ingest_sentencias.py' 2>/dev/null
  echo "$(date +%H:%M) ciclo hecho"
  sleep 1200
done
