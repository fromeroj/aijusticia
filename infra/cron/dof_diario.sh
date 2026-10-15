#!/bin/bash
# DOF diario - ingesta del dia (11:30 CDMX)
cd /opt/aijusticia/engine
.venv/bin/python scripts/ingestion/ingest_all.py --fuentes DOF >> /var/log/aijusticia_dof.log 2>&1
