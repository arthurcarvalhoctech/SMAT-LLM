# dataset-sintetico

20 casos pequenos (uma classe Java e um método alvo por caso) para avaliar os 3 critérios de interferência do prompt do Laya.

- `cases/<id>/source/<Classe>/{base,left,right,merge}.java`: as 4 versões. Left e right são a base com edições em regiões disjuntas, e o merge aplica as duas.
- `input-smat-sintetico.json`: input do SMAT para a triagem Laya. Os JARs são fictícios (o Laya só lê `source/`) e os caminhos usam o prefixo `/app/dataset-sintetico`.
- `gold-sintetico.json`: gabarito por **execução**. Cada caso traz os valores observados em B, L, R e M e os critérios que dispararam.
- Gerado por `scripts/build_synthetic_dataset.py`, que compila e executa as 4 versões e confere o resultado com o critério previsto.

Critérios, aplicados a elementos de estado observados:
- C1: B, L e R têm valores dois a dois diferentes.
- C2: L (ou R) difere de B e de M (mudança perdida).
- C3: B, L e R têm o mesmo valor e M difere (efeito novo no merge).

| Grupo | Casos |
|---|---|
| Sem interferência | 8 |
| C2 | 4 |
| C3 | 3 |
| C1 + C2 | 3 |
| C2 + C3 | 1 |
| C1 + C2 + C3 | 1 |

Não há caso só com C1. Quando B, L e R são dois a dois diferentes, L difere de B e também de M (ou R difere), então C2 dispara junto. Por isso C1 aparece sempre com C2.

Exemplos tirados de `mergedataset` (listas com valores novos dos dois lados, `SlangImpl`/`Keywords`) e da apostila (cleanText, x/y/z, mapa, ordem das chamadas).
