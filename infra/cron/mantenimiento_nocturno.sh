#!/bin/bash
# Ventana muerta 02:30 CDMX. Idempotente.
cd /opt/aijusticia/engine
nice -n 19 .venv/bin/python scripts/quality/limpieza_profunda.py >> /var/log/aijusticia_mantenimiento.log 2>&1
nice -n 19 .venv/bin/python scripts/ingestion/ingest_sentencias.py SentenciasCDMX "/opt/aijusticia/corpus_downloads/sivepj/sivepj_sentencias_*.jsonl" >> /var/log/aijusticia_mantenimiento.log 2>&1
# UNAM-Tesis: retoma donde se quedó (dedup por hash — barato si ya terminó)
if ! pgrep -f ingest_unam_tesis > /dev/null; then
  nice -n 19 .venv/bin/python scripts/ingestion/ingest_unam_tesis.py >> /var/log/aijusticia_unam.log 2>&1
fi
