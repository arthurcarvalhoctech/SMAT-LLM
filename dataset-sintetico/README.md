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

## Avaliar o checkpoint treinado via Docker

Com o Docker Desktop em execução e o modelo extraído em
`laya_checkpoints/laya_semantic_global`, execute na raiz do projeto:

```powershell
docker compose -f docker-compose.laya-eval.yml run --rm --build laya-eval
```

O contêiner avalia os 20 casos em CPU usando **somente a pergunta global
`semantic_interference` que recebeu supervisão**. Os critérios C1/C2/C3
existentes no gold sintético não são tratados como campos aprendidos pelo novo
checkpoint. Não há treinamento, geração de testes Java nem chamadas a APIs de
LLM nesse comando. As classes pequenas completas B/L/R/M entram no estado para
preservar auxiliares e inicializadores; a distribuição dos exemplos sintéticos
é diferente da dos projetos reais usados no treino.

O limiar vem de `validation_selected_threshold` no relatório do checkpoint
(0,5 para o modelo atual). Ele não é ajustado usando o teste sintético. Casos
com truncamento são identificados e excluídos das métricas, com cobertura
explícita; o comando retorna erro se algum caso sofrer truncamento.

Saídas em `dataset-sintetico/resultados/`:

- `laya_semantic_global_eval.json`: probabilidades, métricas, ROC/AUC,
  proveniência dos dados/modelo e versões das bibliotecas.
- `laya_semantic_global_eval.csv`: uma linha por caso, gold e previsão.
- `laya_semantic_global_eval_roc.csv`: pontos da curva ROC (FPR/TPR por limiar).

A primeira construção da imagem baixa dependências. A inferência usa somente
os arquivos locais e roda sem rede, com o checkpoint montado como somente
leitura. A imagem fixa a revisão do Laya e as principais versões registradas no
treino; utiliza a variante CPU do PyTorch, enquanto o treino original usou CUDA.
Pequenas diferenças numéricas entre CPU/GPU são possíveis.

`laya_global_eval.jsonl` é uma preparação dos fontes e do gold por execução já
existentes. Para regenerá-lo após editar os casos:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_laya_synthetic_eval.py
```

Checagens locais sem baixar o modelo ou importar PyTorch:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_laya_synthetic.py --dry-run
.\.venv\Scripts\python.exe -m unittest scripts/test_evaluate_laya_synthetic.py
```

### Execução do checkpoint `laya_semantic_global`

Na execução Docker/CPU registrada em `resultados/laya_semantic_global_eval.json`,
todos os 20 casos couberam no contexto (cobertura 100%). Com o limiar fixo 0,5:
TP=4, FP=3, TN=5, FN=8; precisão 0,5714; recall 0,3333; F1 0,4211;
acurácia 0,45; Brier binário 0,4529; ROC AUC 0,4583. A AUC calculada por
integração da ROC foi conferida independentemente pela ordenação de todos os
pares positivo/negativo (44 de 96 pares concordantes, sem empates).

Esse resultado indica baixa separação no conjunto sintético externo. Não
comprova aprendizagem dos critérios individuais e não deve ser apresentado
como validação geral do detector. O estado inclui classes pequenas completas,
enquanto o treino real utilizou principalmente declarações e campos relevantes;
a diferença de representação/domínio também deve ser considerada na análise.
