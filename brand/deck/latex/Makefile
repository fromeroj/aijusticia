# AI Justicia — pitch deck (LaTeX / Beamer)
#
#   make          compila pitch-deck.pdf
#   make watch    recompila automático al guardar (requiere latexmk)
#   make clean    borra archivos auxiliares
#   make distclean  borra también el PDF
#
# Motor: XeLaTeX (necesario para las fuentes del sistema).

MAIN   = pitch-deck
TEX    = xelatex
FLAGS  = -interaction=nonstopmode -halt-on-error -file-line-error

.PHONY: all watch clean distclean

all: $(MAIN).pdf

$(MAIN).pdf: $(MAIN).tex ../assets/*.png
	$(TEX) $(FLAGS) $<
	$(TEX) $(FLAGS) $<      # segunda pasada para posiciones tikz
	@echo "✔ $(MAIN).pdf"

watch:
	latexmk -pvc -xelatex -interaction=nonstopmode $(MAIN).tex

clean:
	rm -f $(MAIN).aux $(MAIN).log $(MAIN).nav $(MAIN).out \
	      $(MAIN).snm $(MAIN).toc $(MAIN).vrb $(MAIN).fls \
	      $(MAIN).fdb_latexmk latexmk.log

distclean: clean
	rm -f $(MAIN).pdf
