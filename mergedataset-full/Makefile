# Testes do get_cenarios.sh
#
#   make test   -> teste de fumaça: baixa um cenário pequeno e confere o
#                  comportamento (dry-run, download, retomada, --force).

.PHONY: test
test:
	bash -n get_cenarios.sh
	tests/smoke.sh
