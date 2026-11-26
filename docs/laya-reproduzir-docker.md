# Reproduzir os testes com o checkpoint treinado

O pacote `laya_avaliacao_docker.zip` contém os pesos treinados, tokenizer,
configuração do encoder, dados já preparados, três avaliadores e os arquivos
do Docker. Não é necessário instalar Python/Laya no computador do parceiro,
treinar novamente ou fornecer chaves de API. O `.env` principal do SMAT não
faz parte do pacote e suas variáveis `SMAT_*` não configuram esses avaliadores.

## 1. Preparar o computador

Tenha Docker com suporte a contêineres Linux e Docker Compose v2 funcionando.
No Windows, abra o Docker Desktop. Esta imagem executa em CPU, sem GPU.
A execução anterior usou aproximadamente 2,2 GB de memória; reserve pelo menos
4 GB para o Docker e espaço para os pesos, a imagem e as saídas.

Extraia o ZIP e abra o terminal na pasta que contém
`docker-compose.laya-eval.yml`. Não execute os comandos de dentro de `scripts`
ou de `laya_checkpoints`.

```powershell
docker version
docker compose version
```

O pacote preserva esta estrutura:

```text
docker-compose.laya-eval.yml
docker/Dockerfile.laya-eval
scripts/evaluate_laya_synthetic.py
scripts/evaluate_laya_mergedataset.py
scripts/evaluate_laya_all90.py
laya_checkpoints/laya_semantic_global/
  model.safetensors
  rl_agent_config.json
  questions.json
  encoder/config.json
  tokenizer/
  context_audit.json
  manifest.json
  scenario_evaluation.json
laya_training_data/mergedataset_full_colab/
  all.jsonl
  cases.json
  manifest.json
dataset-sintetico/laya_global_eval.jsonl
dataset-sintetico/resultados/
mergedataset-full/resultados/
SHA256SUMS.json
```

Copie os arquivos juntos, preservando os nomes das pastas. Apenas o arquivo
`model.safetensors` não basta para carregar e avaliar o modelo. Os estados
B/L/R/M estão incorporados nos JSONL; esses comandos não precisam baixar
novamente o mergedataset ou compilar Java.

## 2. Variáveis de ambiente usadas

Estas variáveis já estão definidas em `docker/Dockerfile.laya-eval` e são
incorporadas à imagem. Não é necessário criar um `.env` para repeti-las.

```dotenv
PYTHONUNBUFFERED=1
PYTHONDONTWRITEBYTECODE=1
USE_TF=0
HF_HUB_OFFLINE=1
TRANSFORMERS_OFFLINE=1
HF_HOME=/tmp/huggingface
OMP_NUM_THREADS=4
MKL_NUM_THREADS=4
```

- `PYTHONUNBUFFERED`: mostra os logs durante a execução.
- `PYTHONDONTWRITEBYTECODE`: evita criar arquivos `.pyc`.
- `USE_TF`: desativa TensorFlow nesse ambiente.
- `HF_HUB_OFFLINE` e `TRANSFORMERS_OFFLINE`: carregam os arquivos locais.
- `HF_HOME`: aponta o cache para a área temporária gravável do contêiner.
- `OMP_NUM_THREADS` e `MKL_NUM_THREADS`: limitam o paralelismo das bibliotecas.
  O avaliador também limita o PyTorch a até quatro threads.

Os demais parâmetros vêm dos argumentos do serviço e dos arquivos do
checkpoint, e não dessas variáveis:

| Parâmetro | Valor |
|---|---|
| Checkpoint no computador | `laya_checkpoints/laya_semantic_global` |
| Checkpoint dentro do contêiner | `/model` |
| Dados reais no contêiner | `/data/all.jsonl` |
| Saídas no contêiner | `/results` |
| Dispositivo | `cpu` |
| Pergunta | `semantic_interference` |
| Limiar fixo | `0.5`, salvo em `scenario_evaluation.json` |
| Contexto | `8192`, salvo em `rl_agent_config.json` |
| Reserva do cabeçalho | `512`, salva em `rl_agent_config.json` |
| Casos longos | `Agent.predict_long`, batch de uma janela |
| Sobreposição | padrão da API, 50% |
| Agregação binária | maior escore entre as janelas |

Editar `SMAT_LAYA_MODEL`, `SMAT_LAYA_THRESHOLD`, `SMAT_LAYA_MAX_LEN` ou
`PATH_DATASET` no `.env` principal não modifica esses serviços isolados.
O fluxo principal do SMAT faz outras perguntas; carregar este checkpoint
nesse fluxo também exige integrar a pergunta e o formato usados no treino.

## 3. Construir a imagem

```powershell
docker compose -f docker-compose.laya-eval.yml build laya-eval
```

A construção precisa de internet para baixar Python, dependências e o código
do Laya. O runtime dos testes usa `network_mode: none`, pesos/dados somente
para leitura e uma pasta de resultados gravável. Não se troca a imagem por
uma instalação mais recente durante a reprodução.

Versões fixadas: Laya na revisão
`b8a0f0991d95a953411f2e16f91bddc2ffdaf79a` (0.4.30), PyTorch
`2.14.1+cpu` e Transformers `5.22.1`. Os argumentos de construção são
`LAYA_REVISION` e `TORCH_VERSION`, definidos no Dockerfile; não são variáveis
`SMAT_*` nem argumentos de treinamento.

## 4. Recalcular os 90 casos na máquina do parceiro

Execute os dois comandos abaixo em sequência e espere cada um terminar.

```powershell
docker compose -f docker-compose.laya-eval.yml run --rm laya-eval-mergedataset
docker compose -f docker-compose.laya-eval.yml run --rm laya-eval-all90
```

O primeiro recalcula os 78 casos que cabem no contexto e mantém 12 como
`context_excluded`. Ele cria `mergedataset-full/resultados/laya_semantic_global_eval.json`.
O segundo confere pesos, dados e configuração desse relatório, reutiliza
as 78 previsões feitas pelo próprio parceiro e avalia os 12 casos longos
por janelas. O pacote não leva o relatório anterior de 78 previsões: isso
garante que essa primeira etapa seja realizada na máquina dele.

Ao final, o arquivo abaixo deve conter `complete: true`, `cases: 90` e
`metrics.n: 90`:

```text
mergedataset-full/resultados/laya_semantic_global_all90.json
```

Há também um CSV com uma linha por caso e um CSV da curva ROC. Durante a
execução, o relatório dos 90 casos é atualizado após cada caso longo e
contém `complete: false` enquanto houver previsões pendentes. Para acompanhar,
observe os logs no terminal; um caso longo pode exigir várias passagens
antes de imprimir sua conclusão.

Para repetir o teste dos 20 casos sintéticos, opcionalmente:

```powershell
docker compose -f docker-compose.laya-eval.yml run --rm laya-eval
```

As saídas desse comando ficam em `dataset-sintetico/resultados/`.

## 5. Conferir a reprodução

O modelo deve manter o SHA-256 registrado em `SHA256SUMS.json`. Os relatórios
também registram `model_sha256`, `data_sha256`, versões e limiar. Compare
esses campos antes de comparar as previsões. Diferenças numéricas pequenas
podem ocorrer entre processadores; não altere pesos ou limiar para forçar
um resultado igual.

Referência da execução anterior com o protocolo dos 90 casos:

| Conjunto | TP | FP | TN | FN | F1 |
|---|---:|---:|---:|---:|---:|
| Todos os 90, incluindo treino | 14 | 9 | 64 | 3 | 0,7000 |
| Teste reservado, 17 casos | 1 | 4 | 11 | 1 | 0,2857 |

Os 12 casos longos são uma avaliação exploratória. O máximo entre janelas
não é uma probabilidade calibrada do caso completo e pode separar evidências
distantes de B/L/R/M. Os 90 incluem exemplos de treino; a partição de teste
original é a de 17 casos. Nenhum comando acima faz treinamento, calibração
ou escolha de um novo limiar.

Se o segundo comando reclamar que `laya_semantic_global_eval.json` não existe,
execute primeiro `laya-eval-mergedataset`. Se houver divergência de hashes ou
versões, confira se os arquivos do pacote e a mesma imagem foram preservados
entre as duas etapas.
