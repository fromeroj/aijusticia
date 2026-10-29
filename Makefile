# AI Justicia — comando único para todo. Nada a mano.
# make salud          chequeo integral (exit != 0 si algo crítico falla)
# make deploy         deploy API+web a producción con gate de salud
# make bateria        batería de evaluación contra producción
# Ayuda: make help

.PHONY: help salud salud-full deploy deploy-api deploy-web deploy-data sync-data bateria ci-key

help:
	@echo "AI Justicia — targets:"
	@echo "  make salud        chequeo integral del sistema (~15s)"
	@echo "  make salud-full   + smoke del chat (1 pregunta real)"
	@echo "  make deploy       deploy API + web a producción (con gate de salud)"
	@echo "  make deploy-api   solo engine"
	@echo "  make deploy-web   solo Next.js (build + rsync)"
	@echo "  make deploy-data  sincroniza data/ a los servers (162 y 66)"
	@echo "  make bateria      batería de evaluación (--guardar)"
	@echo "  make ci-key       imprime la llave pública de CI (para authorized_keys)"

PROD = root@162.35.113.166
AUX  = root@66.154.100.25
RSYNC_ENGINE = rsync -az --exclude .env --exclude .venv --exclude data/ \
    --exclude __pycache__ --exclude "*.pyc" --exclude .pytest_cache \
    engine/ $(PROD):/opt/aijusticia/engine/
RSYNC_WEB = rsync -az --exclude node_modules --exclude .next \
    apps/web/ $(PROD):/opt/aijusticia/app/
RSYNC_DATA = rsync -az --exclude __pycache__ data/ $(PROD):/opt/aijusticia/data/ \
  && rsync -az --exclude __pycache__ data/ $(AUX):/opt/aijusticia/data/

salud:
	python3 infra/salud.py

salud-full:
	python3 infra/salud.py --full

deploy: deploy-api deploy-web

deploy-api:
	bash infra/deploy.sh api

deploy-web:
	bash infra/deploy.sh web

deploy-data:
	$(RSYNC_DATA)

sync-data: deploy-data

bateria:
	python3 eval/eval_bateria_prod.py --guardar

ci-key:
	@test -f infra/ci_ed25519.pub && cat infra/ci_ed25519.pub || \
	echo "genera primero: ssh-keygen -t ed25519 -f infra/ci_ed25519 -N '' -C 'ci@aijusticia'"
