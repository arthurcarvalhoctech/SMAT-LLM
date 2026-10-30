# Experimentos com a Laya no dataset sintético

Como reproduzir a avaliação da triagem Laya em casos pequenos com gabarito por execução.
Tudo roda no container (`INSTALL_LAYA=true` no build) com `PYTHONPATH=/app/SMAT`.

## Dados

| Caminho | Conteúdo |
|---|---|
| `dataset-sintetico/` | 20 casos (8 sem interferência, 12 com C1/C2/C3), 4 versões Java por caso, input do SMAT e gabarito por execução. Ver o README da pasta. |
| `scripts/build_synthetic_dataset.py` | Regenera o dataset: compila, executa B/L/R/M e confere os critérios. `python3 -I scripts/build_synthetic_dataset.py --output dataset-sintetico` |
| `template/gold-13-methods.json` | Gabarito parcial dos 13 métodos de `input-smat-mergedataset.json` (incerto em 4 classes). |

## Triagem pelo SMAT (fluxo atual)

```bash
docker compose run --rm -T smat bash -lc 'cd /app &&
  SMAT_INPUT_PATH=/app/dataset-sintetico/input-smat-sintetico.json \
  SMAT_LAYA_INTERFERENCE_DETECTION=true SMAT_DYNAMIC_INTERFERENCE_DETECTION=false \
  SMAT_LAYA_MODEL=multilingual SMAT_LAYA_MAX_LEN=4000 \
  python3 run_experiment.py'
```

Com um checkpoint local (modelo ajustado), use `docker-compose.laya-local.yml` (ver o cabeçalho do arquivo).

## Variações de entrada e de pergunta

| Script | O que mede |
|---|---|
| `scripts/laya_t1_probe.py --out probe.json` | Estado no formato do treino (`smat_dataset`: corpo de B/L/R em uma linha, resumos, atributos) com a pergunta T1 ou as 3 perguntas de critério; com e sem merge. |
| `scripts/laya_question_formats.py --out formats.json` | 4 formatos de pergunta (`noul` com `criteria`, `choice` A/B, `noul` com `labels` A/B, `noul` sem `criteria`) × 2 estados (SMAT e treino) × modelos base e ajustado, nos 20 casos e nos 13 métodos. |

Ambos usam `--ft` (padrão `/laya_smat/laya_finetuned_smat_multilingual`) para o modelo ajustado; sem os pesos, só o modelo base roda.
Resultados de referência estão em `dataset-sintetico/resultados/`.

## Resultados (resumo)

- Base e ajustado marcam quase tudo como interferência com o estado e as perguntas atuais do SMAT (20 casos: TP 12, FP 8, TN 0, FN 0). AUC próxima de 0,5 e abaixo disso para C3.
- O limiar não é a causa: o melhor limiar por critério dá acurácia balanceada de 0,50 a 0,69 (holdout 0,42 a 0,50).
- Com o estado no formato do treino, o ajustado diz "sem interação" (~0,10) para quase tudo. O treino cobre 5 famílias sintéticas e parece não generalizar.
- `noul` com `labels` A/B foi o único formato com AUC > 0,5 nas 8 combinações (0,53 a 0,83; melhor: base + estado do treino, 0,81 em 31 casos, IC 95% 0,63 a 0,95).

## Ressalvas

n pequeno (20 sintéticos; 11 rotulados do mergedataset, 3 positivos), muitas comparações, gabarito do mergedataset incerto, resumos dos sintéticos escritos à mão. Não é um classificador utilizável; serve para decidir o que testar com um conjunto maior e separado.
