# Avaliar o checkpoint global no mergedataset real

Na raiz do projeto, com o Docker Desktop em execução:

```powershell
docker compose -f docker-compose.laya-eval.yml run --rm laya-eval-mergedataset
```

O serviço usa a mesma imagem CPU da avaliação sintética. Caso a imagem ainda
não exista, acrescente `--build` ao comando. O checkpoint em
`laya_checkpoints/laya_semantic_global` é montado como somente leitura e a
inferência ocorre sem rede.

São usados os 90 casos reais disponíveis em
`laya_training_data/mergedataset_full_colab/all.jsonl`, com uma única
apresentação original por caso (variant 0), sem aumentar artificialmente o
número de observações pelas quatro vistas do treinamento. O catálogo tem
95 linhas: 4 inconclusivas e 1 caso rotulado sem fontes continuam excluídos da
entrada. Esses motivos constam do manifesto de preparação.

O limiar permanece o selecionado anteriormente na validação dos casos reais,
0,5 para este checkpoint. Não há treinamento, recalibração ou seleção de
limiar nesta execução. Avalia-se exclusivamente `semantic_interference`, a
pergunta que recebeu supervisão. Os sete campos específicos dos critérios
não são apresentados como campos aprendidos pelo modelo.

O relatório separa as partições originais de treino (57 casos), validação (16)
e teste (17). `context_audit.json` do checkpoint identifica quais casos
efetivamente participaram do ajuste de pesos ou da calibração; as novas
previsões preservam essa informação em `exposure`. As métricas agrupadas de
todo o dataset incluem casos vistos pelo modelo e são apenas diagnósticas.
Somente a partição original `test` foi reservada do ajuste dos pesos, das
temperaturas e do limiar; seu resultado também continua sujeito ao tamanho
da amostra e à cobertura de contexto.

Antes de inferir, o avaliador tokeniza o estado completo com o tokenizer do
checkpoint e aplica o mesmo orçamento conservador do notebook:
`state_tokens + head_max_len + 32 <= max_len`. Se não couber, não faz
inferência: mantém uma linha com `status=context_excluded` e probabilidade
ausente. Os casos excluídos entram no denominador de cobertura e ficam
identificados por partição. Truncamentos inesperados durante a predição
também são excluídos das métricas e fazem o comando retornar erro.

Saídas em `mergedataset-full/resultados/`:

- `laya_semantic_global_eval.json`: métricas/ROC agrupadas e por partição,
  probabilidades, exclusões, exposição ao treino, hashes dos dados/modelo e
  versões das bibliotecas.
- `laya_semantic_global_eval.csv`: uma linha por caso original, com split,
  exposure, gold, probabilidade, previsão, status e tamanho do estado.
- `laya_semantic_global_eval_roc.csv`: ROC agrupada, que inclui casos de treino.
- `laya_semantic_global_eval_{train,validation,test}_roc.csv`: curvas separadas.

As métricas usam somente casos que couberam integralmente no contexto. A AUC
é calculada agrupando empates e integrando a curva ROC; ela fica ausente
quando não há exemplos das duas classes na partição avaliada.

## Resultado da execução Docker/CPU

Dos 90 casos disponíveis, 78 foram avaliados integralmente e 12 foram excluídos
por contexto (cobertura 86,67%). O limiar foi mantido em 0,5.

| Partição | Avaliados/originais | TP | FP | TN | FN | Precisão | Recall | F1 | ROC AUC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Treino | 55/57 | 12 | 0 | 43 | 0 | 1,0000 | 1,0000 | 1,0000 | 1,0000 |
| Validação | 12/16 | 1 | 0 | 10 | 1 | 1,0000 | 0,5000 | 0,6667 | 0,5500 |
| Teste reservado | 11/17 | 1 | 1 | 9 | 0 | 0,5000 | 1,0000 | 0,6667 | 1,0000 |

As métricas agrupadas (78 casos) têm precisão/recall/F1 de 0,9333, acurácia
0,9744 e AUC 0,9698. Incluem os 55 casos usados no ajuste de pesos, portanto
não estimam o desempenho em novos casos. O teste reservado contém apenas um
positivo após o filtro; sua AUC de 1,0 depende dessa amostra mínima e não
constitui evidência robusta de separação geral.

O falso negativo é `OpenTripPlanner.MultiShortestPathTree.dominates` na
validação (P=0,0073); o falso positivo é
`elasticsearch.ESSingleNodeTestCase.newNode` no teste (P=0,5731).
As decisões de validação/teste reproduziram as da execução no Colab, com
pequenas diferenças numéricas nas probabilidades. O hash dos pesos coincide
com o da avaliação sintética. As AUCs por partição foram conferidas por um
segundo cálculo baseado em todos os pares positivo/negativo.

## Conferir `.env` e comparar o limite de contexto

O avaliador isolado não carrega o `.env` de produção: por padrão usa o
checkpoint local treinado, sua pergunta global e o contexto salvo de 8192.
Já o fluxo principal usa `SMAT_LAYA_MODEL`, perguntas C1/C2/C3 e
`SMAT_LAYA_STATE_FORMAT`. Portanto, não se deve chamar o teste isolado de
uma execução completa da configuração de produção.

Para conferir apenas as opções públicas, sem exibir chaves de API:

```powershell
.\.venv\Scripts\python.exe scripts/audit_laya_env.py
```

Para uma comparação controlada de contexto, mantendo pesos, entrada e limiar:

```powershell
docker compose -f docker-compose.laya-eval.yml run --rm laya-eval-mergedataset --model /model --data-dir /data --out /results/laya_semantic_global_context_4048.json --device cpu --max-len 4048 --threshold 0.5
.\.venv\Scripts\python.exe scripts/compare_laya_contexts.py
```

O segundo comando confere hashes dos pesos/dados, pergunta e limiar antes de
comparar as decisões nos casos em comum. O relatório fica em
`resultados/laya_context_comparison.json`. A auditoria fica em
`resultados/laya_env_audit.json`. Nenhum desses comandos modifica `.env`.

Para apontar o Docker principal para os pesos locais, o par de opções de
montagem é `LAYA_SMAT_DIR=./laya_checkpoints` e
`SMAT_LAYA_MODEL=/laya_smat/laya_semantic_global`. Isso só seleciona os
pesos: ainda é necessário integrar a pergunta `semantic_interference` e o
mesmo formato B/L/R/M ao fluxo principal. O modo `compact` atual desse fluxo
omite M por padrão, enquanto o treino global inclui M. Alterar apenas essas
variáveis não transforma as perguntas de critérios em tarefas supervisionadas.

### Comparação medida: 4048 versus 8192

Com o mesmo checkpoint, dados e limiar 0,5, a execução com 4048 avaliou 60/90
casos; a de 8192 avaliou 78/90. Nos 60 casos em comum, as probabilidades e as
decisões foram idênticas (diferença máxima de probabilidade 0). O contexto
maior recuperou 18 casos, incluindo 4 positivos da partição de treino.

Na partição de teste reservado, 4048 avaliou 9/17 casos (TP=1, FP=1, TN=7,
FN=0); 8192 avaliou 11/17 (TP=1, FP=1, TN=9, FN=0). Precisão 0,5, recall 1
e F1 0,6667 nos dois perfis. Portanto, a mudança ampliou a cobertura, sem
melhorar decisões nos exemplos em comum. O teste continua contendo apenas
um positivo que coube no contexto.

Essa comparação usa o detector global treinado e o formato do treino. O
`.env` auditado seleciona `multilingual` (base), contexto 4048 e uma pasta do
dataset sintético; o fluxo principal usa perguntas de critérios. Assim, a
comparação não deve ser descrita como execução integral desse `.env`.

Checagens sem carregar os pesos:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_laya_mergedataset.py --dry-run
.\.venv\Scripts\python.exe -m unittest scripts/test_evaluate_laya_mergedataset.py
```

## Avaliação exploratória dos 90 casos, incluindo textos longos

```powershell
docker compose -f docker-compose.laya-eval.yml run --rm laya-eval-all90
```

Essa execução preserva o relatório anterior e cria
`resultados/laya_semantic_global_all90.json`, `.csv` e `_roc.csv`.
Reaproveita as 78 previsões completas anteriores somente após conferir os
hashes dos pesos/dados, IDs, rótulos, partições, contexto, limiar e versões
de Laya/PyTorch/Transformers. Os 12 casos anteriormente excluídos são
processados pela API oficial `Agent.predict_long`, com janelas sobrepostas
em 50%, orçamento do checkpoint e batch de uma janela. Nenhum caso é
usado para novo treinamento, calibração ou ajuste de limiar.

Para perguntas `noul`, essa API retorna o maior escore entre as janelas.
O relatório registra `inference_method`, `window_count`, a janela decisiva
e o uso de tokens; qualquer janela truncada faz a execução falhar. Os
arquivos são atualizados após cada caso, com `complete=false` e linhas
`pending` enquanto a execução não termina. Para retomar uma execução
parcial, passe o próprio relatório parcial em `--reuse-report` e mantenha
os demais argumentos do serviço.

Esse protocolo cobre todos os tokens em alguma janela, mas **não garante
que evidências distantes de B/L/R/M sejam vistas juntas**. O máximo cresce
com a quantidade de janelas e pode aumentar falsos positivos. Os escores
dos casos longos não são probabilidades calibradas do caso inteiro;
por isso o Brier fica ausente nas métricas que os incluem. As métricas
são separadas por método e pela partição original. A comparação com o
relatório anterior deve considerar a mudança de método e de cobertura.
As métricas dos 90 casos continuam incluindo treino e não representam
desempenho em 90 exemplos novos. Isso também não avalia separadamente
C1/C2/C3 nem substitui um teste semântico com execução de Java.

### Resultado com cobertura de 90/90

A execução terminou com limiar 0,5: 78 previsões completas anteriores
preservadas e 12 novos casos avaliados por `predict_long`, totalizando 66
janelas nesses 12 casos. Não houve truncamento de janela. Os 90 IDs são
únicos e o CSV tem 90 previsões concluídas. As matrizes de confusão e as
AUCs foram verificadas independentemente; a AUC foi recalculada contando
todos os pares positivo/negativo, incluindo empates com peso 0,5. Essa
conferência está em `resultados/laya_semantic_global_all90_verification.json`.

| Partição | Casos | TP | FP | TN | FN | Precisão | Recall | F1 | Acurácia | ROC AUC |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Treino original | 57 | 12 | 1 | 43 | 1 | 92,31% | 92,31% | 92,31% | 96,49% | 0,9983 |
| Validação original | 16 | 1 | 4 | 10 | 1 | 20,00% | 50,00% | 28,57% | 68,75% | 0,3929 |
| Teste reservado | 17 | 1 | 4 | 11 | 1 | 20,00% | 50,00% | 28,57% | 70,59% | 0,8667 |
| Todos, diagnóstico incluindo treino | 90 | 14 | 9 | 64 | 3 | 60,87% | 82,35% | 70,00% | 86,67% | 0,9355 |

Os 12 casos longos tiveram TP=0, FP=8, TN=2 e FN=2: apenas 2 acertos
(16,67% de acurácia). Oito negativos foram marcados como interferência e
os dois positivos foram perdidos. Os 78 casos com estado completo mantêm
TP=14, FP=1, TN=62 e FN=1; suas previsões não foram alteradas.

Assim, a maior cobertura expôs limitações importantes do protocolo de
janelas; não houve melhora de detecção nos casos longos. As métricas
dos 90 misturam métodos e incluem treinamento. O teste reservado de 17
casos é mais adequado para discutir generalização, mas contém somente
dois positivos e seis entradas avaliadas por janelas. A AUC depende do
ranqueamento dos escores e não elimina o baixo F1 no limiar fixo 0,5.
Nenhuma mudança de limiar foi feita a partir desses resultados.
