# template

Gabarito parcial de interferência dos 13 métodos de `input-smat-mergedataset.json` (9 cenários).

- Arquivo: `gold-13-methods.json`
- Fonte: coluna "Locally Observable Interference" de `mergedataset/semantic-conflicts/sample-semantic-conflicts.csv`.
- Cobertura: 3 `Yes`, 8 `No`, 2 sem rótulo (`-`, os dois métodos de `AtomikosPropertiesTests`).
- `disputed: true` marca as 4 classes (Atomikos e ExplodedArchive, com seus testes) em que o CSV diz `No`, mas o relatório executado indica conflito. O gabarito ainda precisa ser confirmado.
