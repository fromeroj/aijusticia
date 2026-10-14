# Tohil — entrenamiento de Tlamatini
#
#   make prep          Prepara el corpus CPT (en el server)
#   make smoke         Smoke test en Mac (Qwen2.5-0.5B + slice)
#   make eval          Evalúa la batería de 30 preguntas
#   make merge         Merge lineal post-CPT
#   make export-gguf   Export para Ollama/llama.cpp

.PHONY: prep smoke eval merge export-gguf

prep:
	cd ../engine && .venv/bin/python scripts/prep_cpt_completo.py

smoke:
	cd $(dir $(lastword $(MAKEFILE_LIST))) && \
	echo "Y" | .venv/bin/soup train --config soup-pipeline-test.yaml

eval:
	cd $(dir $(lastword $(MAKEFILE_LIST))) && \
	.venv/bin/python eval_bateria.py --model ./merged

merge:
	cd $(dir $(lastword $(MAKEFILE_LIST))) && \
	.venv/bin/python merge_linear.py \
		--base Qwen/Qwen3-30B-A3B \
		--cpt ./output_tlamatini_v1 \
		--alpha 0.5 \
		--output ./tlamatini_v1_merged

export-gguf:
	cd $(dir $(lastword $(MAKEFILE_LIST))) && \
	echo "Y" | .venv/bin/soup export --model ./tlamatini_v1_merged --format gguf --quant f16

clean:
	rm -rf output_*/ merged/ *.gguf
