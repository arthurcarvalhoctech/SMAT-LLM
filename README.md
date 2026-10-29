# SMAT - Multi-Provider LLM

Ferramenta para identificação de conflitos semânticos em cenários de merge.

Esta versão adapta o SMAT para usar **múltiplos provedores de LLM** por variáveis
de ambiente: DeepSeek, OpenAI e endpoints OpenAI-compatible (OpenRouter,
Together, Groq, vLLM, LM Studio etc.), Gemini, Anthropic e Ollama local.

Para reproduzir os números do artigo SAST'25 (Code Llama 70B via Ollama), use o
branch
[`codellama-integration`](https://github.com/nathaliafab/SMAT/tree/codellama-integration)
e os artefatos do [Zenodo](https://doi.org/10.5281/zenodo.20938400).

## O que está implementado

- 8 combinações de prompt (zero-shot e one-shot), como no artigo.
- `temperature`, `seed`, `timeout_seconds`, `max_output_tokens` e
  `num_outputs` configuráveis.
- `prompt_keys` para executar um subconjunto (por exemplo, prompts 1–5 no ASTER).
- Seleção de provedor/modelo/chave por variáveis de ambiente (`LLM_*`).
- Adaptadores nativos para Gemini e Anthropic, OpenAI-compatible para DeepSeek/
  OpenAI/OpenRouter/etc. e Ollama.
- Retry com backoff para falhas transitórias da API.
- Resolução de fontes para o layout do `mergedataset` e do ASTER.
- Docker com Python 3.11, Java 8 e Maven.

## 1. Pré-requisitos

- Docker e Docker Compose (recomendado); ou
- Python 3.11+ + Java 8 **JDK** (o `javac` é obrigatório).
- Uma chave do provedor escolhido (DeepSeek, OpenAI, Gemini, Anthropic etc.) ou
  um Ollama local.

## 2. Configuração

### 2.1 Provedor e chave da API

A seleção do provedor é feita por **variáveis de ambiente**, que têm precedência
sobre `env-config.json`. Crie o `.env` a partir do exemplo:

```bash
cp .env.example .env
chmod 600 .env
```

Exemplo para **DeepSeek** (o mesmo provedor usado pela ferramenta de
desenvolvimento):

```dotenv
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-flash
LLM_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=sua-chave
```

O endpoint chamado será `https://api.deepseek.com/chat/completions`. Se o
provedor usar outro ID para o modelo "v4 flash", ajuste `LLM_MODEL`.

Outros exemplos:

```dotenv
# OpenAI
LLM_PROVIDER=openai
LLM_MODEL=gpt-4o-mini
OPENAI_API_KEY=...

# OpenRouter / Together / Groq (OpenAI-compatible)
LLM_PROVIDER=openrouter
LLM_MODEL=deepseek/deepseek-chat
LLM_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_API_KEY=...

# Gemini nativo
LLM_PROVIDER=gemini
LLM_MODEL=gemini-2.5-flash
GEMINI_API_KEY=...

# Ollama local (sem chave)
LLM_PROVIDER=ollama
LLM_MODEL=llama3.1:8b
LLM_BASE_URL=http://localhost:11434
# No Docker, use http://host.docker.internal:11434

# Qualquer endpoint OpenAI-compatible (vLLM, LM Studio, ...)
LLM_PROVIDER=openai-compatible
LLM_MODEL=seu-modelo
LLM_BASE_URL=http://localhost:8000/v1
LLM_API_KEY=opcional
```

Variáveis reconhecidas:

| Variável | Função |
|---|---|
| `LLM_PROVIDER` | `deepseek`, `openai`, `openrouter`, `together`, `groq`, `gemini`, `anthropic`, `ollama`, `vllm`, `lmstudio`, `custom` ou `openai-compatible` |
| `LLM_MODEL` | ID exato do modelo no provedor |
| `LLM_BASE_URL` | URL base ou endpoint completo |
| `LLM_API_KEY` | Chave genérica, aceita por qualquer provedor |
| `DEEPSEEK_API_KEY` | Chave específica do DeepSeek |
| `OPENAI_API_KEY` / `OPENROUTER_API_KEY` / `TOGETHER_API_KEY` / `GROQ_API_KEY` | Chaves específicas |
| `GEMINI_API_KEY` / `GOOGLE_API_KEY` | Chaves do Gemini |
| `ANTHROPIC_API_KEY` | Chave da Anthropic |
| `LLM_MODEL_KEY` | Rótulo usado nos diretórios/relatórios de saída |
| `LLM_TEMPERATURE` | Temperatura (padrão: `0.0`) |
| `LLM_SEED` | Seed (padrão: `42`) |
| `LLM_TIMEOUT_SECONDS` | Timeout por requisição (padrão: `300`) |
| `LLM_MAX_OUTPUT_TOKENS` | Máximo de tokens de saída (padrão: `8192`) |
| `LLM_NUM_OUTPUTS` | Respostas por prompt (padrão: `1`) |
| `LLM_PROMPT_KEYS` | Subconjunto de prompts, separado por vírgulas |
| `LLM_PROMPT_TEMPLATE` | `zero_shot` ou `one_shot` |

O `docker-compose.yml` repassa todas essas variáveis ao container. O
`llm_config.py` também carrega `.env` automaticamente em execuções locais
(via `python-dotenv`).

### 2.2 `SMAT/nimrod/tests/env-config.json`

```json
{
  "java_home": "/usr/lib/jvm/java-8-openjdk-amd64",
  "input_path": "/app/input-smat-mergedataset.json",
  "logger_level": "INFO",
  "test_suite_generators": ["llm"],
  "test_suite_generation_search_time_available": "45",
  "prompt_template": "zero_shot",
  "api_params": {
    "gemini": {
      "provider": "gemini",
      "model": "gemini-2.5-flash",
      "api_key": "",
      "temperature": 0.0,
      "seed": 42,
      "timeout_seconds": 300,
      "max_output_tokens": 8192,
      "num_outputs": 1,
      "prompt_keys": [
        "prompt1", "prompt2", "prompt3", "prompt4",
        "prompt5", "prompt6", "prompt7", "prompt8"
      ]
    }
  }
}
```

Esse bloco é o **fallback** quando nenhuma variável `LLM_*` está definida. Com
`LLM_PROVIDER`/`LLM_MODEL`/chave no ambiente, o `api_params` é ignorado.

Principais campos:

- `input_path`: caminho do JSON de cenários. No Docker, use
  `/app/input-smat-mergedataset.json`.
- `prompt_template`: `zero_shot` ou `one_shot`.
- `temperature` e `seed`: usados apenas se não houver `LLM_TEMPERATURE`/
  `LLM_SEED`.
- `num_outputs`: respostas por prompt; o artigo usa `1`.
- `prompt_keys`: subconjunto de prompts; para o ASTER/RQ3 use
  `["prompt1", "prompt2", "prompt3", "prompt4", "prompt5"]`.
- `api_key`: deixe vazio se estiver usando as variáveis de ambiente.

O `java_home` do JSON não é lido pelo código atual; o que vale é a variável de
ambiente `JAVA_HOME`. O Dockerfile já define Java 8.

### 2.3 `input-smat.json`

Formato:

```json
[
  {
    "projectName": "spring-boot",
    "runAnalysis": true,
    "scenarioCommits": {
      "base": "...",
      "left": "...",
      "right": "...",
      "merge": "..."
    },
    "targets": {
      "org.exemplo.MinhaClasse": [
        {
          "method": "meuMetodo(int)",
          "leftChangesSummary": "Left faz ...",
          "rightChangesSummary": "Right faz ..."
        }
      ]
    },
    "scenarioJars": {
      "base": "/data/mergedataset/.../transformed/base/foo.jar:/data/.../bar.jar",
      "left": "/data/mergedataset/.../transformed/left/foo.jar:/data/.../bar.jar",
      "right": "/data/mergedataset/.../transformed/right/foo.jar:/data/.../bar.jar",
      "merge": "/data/mergedataset/.../transformed/merge/foo.jar:/data/.../bar.jar"
    },
    "jarType": "transformed"
  }
]
```

- Vários jars por branch podem ser separados por `:`.
- `targets` aceita uma lista de strings (métodos) ou de objetos com
  `leftChangesSummary`/`rightChangesSummary`.
- `jarType` deve ser `transformed` ou `original` e deve aparecer no caminho dos
  jars.

### 2.4 Flags dos fluxos de detecção de interferências

O SMAT tem dois fluxos independentes:

1. **Dinâmico baseado em testes** (ligado por padrão): gera testes a partir de
   `left`/`right`, executa em `base`/`left`/`right`/`merge` e aplica os
   critérios de conflito semântico.
2. **Pré-análise com Laya** (desligado por padrão): usa o modelo de decisão
   Laya para levantar hipóteses sobre os três critérios de estado do artigo
   antes da detecção dinâmica. Ele **não substitui** a detecção por execução.

| Variável | Padrão | Efeito |
|---|---|---|
| `SMAT_DYNAMIC_INTERFERENCE_DETECTION` | `true` | Liga/desliga o fluxo dinâmico baseado em testes. |
| `SMAT_LAYA_INTERFERENCE_DETECTION` | `false` | Liga/desliga a pré-análise com Laya. |
| `SMAT_LAYA_MODEL` | `english` | Checkpoint do Laya (`english`, `multilingual` ou `typed-decisions`). |
| `SMAT_LAYA_THRESHOLD` | `0.5` | Probabilidade mínima para marcar um critério como acionado. |
| `SMAT_LAYA_MAX_LEN` | `512` | Limite de tokens do estado enviado ao Laya. |
| `SMAT_LAYA_LOG_DIR` | `.../reports/laya` | Diretório dos logs `.log` e `.jsonl`. |

Combinações possíveis:

| Dinâmico | Laya | Resultado |
|---|---|---|
| `true` | `false` | Apenas a detecção atual (padrão). |
| `false` | `true` | Apenas a pré-análise Laya. |
| `true` | `true` | Laya primeiro, depois a detecção dinâmica. |
| `false` | `false` | Nenhum fluxo; o SMAT informa que nenhum está ativo. |

Quando o fluxo dinâmico é desabilitado, o console exibe:

```text
O fluxo de detecção de interferências baseado em testes não está ativo.
```

A instalação do Laya é opcional:

```bash
python -m pip install -r SMAT/requirements-laya.txt
```

No Docker, use `INSTALL_LAYA=true` no build. O Dockerfile instala **torch CPU**
por padrão (`TORCH_INDEX_URL`) e o `requirements-laya.txt` fixa
`transformers<4.52`, combinação validada com `laya 0.4.12`. O primeiro uso baixa
o checkpoint do Hugging Face. Os logs ficam em:

```text
SMAT/output-test-dest/reports/laya/laya_interference_<run_id>.log
SMAT/output-test-dest/reports/laya/laya_interference_<run_id>.jsonl
```

O `docker-compose.yml` repassa todas essas variáveis ao container. Em execuções
locais, o `.env` é carregado automaticamente. Detalhes do fluxo, dos três
critérios e do formato do log estão em
[`docs/fluxo-laya.md`](docs/fluxo-laya.md).

## 3. Datasets

### 3.1 mergedataset

Clone o dataset no commit usado no artigo:

```bash
git clone https://github.com/spgroup/mergedataset.git
cd mergedataset
git checkout c8b965f71624f0ee3bec197d37ffbb2a9aaba97b
```

Layout esperado:

```text
mergedataset/<projeto>/<hash>/
├── transformed/
│   ├── base/*.jar
│   ├── left/*.jar
│   ├── right/*.jar
│   └── merge/*.jar
└── source/
    ├── <Classe>_base.java
    ├── <Classe>_left.java
    ├── <Classe>_right.java
    └── <Classe>_merge.java
```

A resolução de fontes deste repositório aceita `<Classe>_<branch>.java`,
`<Classe>/<branch>.java`, `<branch>.java` e, para datasets de uma única versão,
`<Classe>.java`. Portanto, **não é necessário renomear os fontes do
mergedataset**.

Use o `inputs/input-smat.json` do artefato Zenodo e troque o prefixo dos
caminhos:

```bash
sed -i 's#/path/mergedataset/mergedataset#/data/mergedataset#g' input-smat.json
```

No `docker-compose.yml`, monte o dataset:

```yaml
volumes:
  - .:/app
  - /caminho/mergedataset:/data/mergedataset:ro
```

### 3.2 ASTER

O ASTER não contém cenários de merge; ele é usado no RQ3 para medir a **taxa de
compilação**. O SMAT ainda precisa de quatro jars e de fontes para gerar os
testes. Prepare uma estrutura por projeto:

```text
/data/aster/<projeto>/
├── transformed/
│   ├── base/<algo>.jar
│   ├── left/<algo>.jar
│   ├── right/<algo>.jar
│   └── merge/<algo>.jar
└── source/
    └── <Classe>.java
```

Se o ASTER tiver apenas uma versão, copie ou simlinke o mesmo jar e a mesma
fonte nas quatro branches. A análise de conflito não será significativa, mas a
compilação dos testes será medida corretamente.

Use `inputs/input-smat-aster.json` do artefato e ajuste os caminhos relativos
(`base.jar`, `left.jar`, ...) para caminhos absolutos dentro do container, por
exemplo:

```text
/data/aster/<projeto>/transformed/base/<algo>.jar
/data/aster/<projeto>/transformed/left/<algo>.jar
/data/aster/<projeto>/transformed/right/<algo>.jar
/data/aster/<projeto>/transformed/merge/<algo>.jar
```

Para o RQ3, configure:

```json
"prompt_keys": ["prompt1", "prompt2", "prompt3", "prompt4", "prompt5"]
```

## 4. Executando

### 4.1 Com Docker (recomendado)

1. Crie o `.env` e preencha o provedor/modelo/chave:
   ```bash
   cp .env.example .env
   chmod 600 .env
   ```
2. Ajuste os volumes dos datasets no `docker-compose.yml`.
3. Execute:
   ```bash
   USER_ID=$(id -u) GROUP_ID=$(id -g) docker compose run --rm --build smat
   ```
4. Dentro do container:
   ```bash
   python3 run_experiment.py
   ```

O `docker-compose.yml` repassa todas as variáveis `LLM_*` e as chaves dos
provedores. O `JAVA_HOME` já aponta para Java 8 e o `PYTHONPATH` é configurado
pelo `run_experiment.py`.

### 4.2 Sem Docker

```bash
python3 -m venv .venv
source .venv/bin/activate

pip install -r SMAT/requirements.txt

# O .env é carregado automaticamente por llm_config.py
export JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64   # precisa ser JDK
export PYTHONPATH="$PWD/SMAT"
export SMAT_INPUT_PATH="$PWD/input-smat-mergedataset.json"

python3 run_experiment.py
```

`SMAT_INPUT_PATH` evita ter que editar `input_path` no `env-config.json` para
execuções locais.

Nesse caso, ajuste `input_path` para um caminho absoluto do host, por exemplo:

```json
"input_path": "/home/arthur/UFPE/SMAT-Gemini/input-smat-mergedataset.json"
```

E ajuste os caminhos de `scenarioJars` para os jars no host.

## 5. Executando a grade do artigo

O desenho do artigo combina:

- `prompt_template`: `zero_shot`, `one_shot`
- `temperature`: `0.0`, `0.7`
- `seed`: `42`, `123`
- 8 prompts por branch e por método
- 1 resposta por prompt

Exemplo de loop usando variáveis de ambiente:

```bash
for template in zero_shot one_shot; do
  for temp in 0.0 0.7; do
    for seed in 42 123; do
      LLM_PROMPT_TEMPLATE="$template" \
      LLM_TEMPERATURE="$temp" \
      LLM_SEED="$seed" \
        python3 run_experiment.py

      mv SMAT/output-test-dest "runs/${template}-T${temp}-S${seed}"
    done
  done
done
```

O provedor, o modelo, a URL e a chave vêm do `.env`; o loop só varia os
parâmetros experimentais.

Cada execução gera `8 prompts × 2 branches × N métodos` chamadas. Com os 79
métodos do input do artigo, são **1264 chamadas por execução**.

**Atenção:** os relatórios são anexados a cada execução. Archive ou remova
`SMAT/output-test-dest` entre configurações para não misturar resultados.

## 6. Saídas e métricas

- `SMAT/output-test-dest/scenarios/<input_stem>_<timestamp>/`
  - `manifest.json`: dataset, timestamp, input e metadados de cada cenário.
  - `NNN_<projeto>/`: uma pasta por cenário de merge.
    - `base`, `left`, `right`, `merge`: fontes Java concatenados de todas as
      classes-alvo daquela versão. São snapshots para análise; múltiplas classes
      concatenadas não formam um arquivo Java compilável.
- `SMAT/output-test-dest/projects/<projeto>/<merge>/<GERADOR>_<timestamp>/`
  - `*.java`: testes gerados.
  - `classes/*.class`: testes que compilaram.
  - `scenario_infos.json`, `imports.json`, `generated_messages.json`.
- `SMAT/output-test-dest/reports/`
  - `semantic_conflicts.json`: conflitos detectados.
  - `behavior_changes.json`: mudanças de comportamento.
  - `test_suites.json`: resumo por suite.
  - `compilation_results.json`: erros de compilação.
  - `execution_results.json`: resultados das execuções.
  - `gemini..._time_duration.json`: tempos por prompt.

Métricas usuais:

- **Testes gerados**: contagem de `.java`.
- **Testes compilados**: contagem de `.class`.
- **Taxa de compilação**: `.class / .java`.
- **Conflitos**: achate `semantic_conflicts.json` e deduplique por
  `(project_name, classe-alvo, método-alvo)`. O mesmo conflito pode aparecer em
  várias suites/prompts.
- **Tempo**: some `total_duration` em `*_time_duration.json`.

A cobertura (`exercised_targets`) está desativada no código atual; o campo fica
vazio.

## 7. Solução de problemas

- **`'tree_sitter.Language' object has no attribute 'query'`**: use
  `tree-sitter==0.25.1` e `tree-sitter-java==0.23.5` (já fixados em
  `SMAT/requirements.txt`).
- **`javac: not found`**: instale `openjdk-8-jdk`, não apenas o JRE; ou use o
  Docker.
- **`Source directory ... not found`**: o caminho do jar deve conter
  `transformed` ou `original`, e deve existir uma pasta `source/` irmã do
  diretório `transformed`/`original`. Confira também se `PATH_DATASET` aponta
  para o dataset real que contém `<projeto>/<hash>/source/`; um clone vazio faz
  os snapshots registrarem `no base source`/`no merge source`.
- **`API key not configured`**: preencha `LLM_API_KEY`, a chave específica do
  provedor (por exemplo `DEEPSEEK_API_KEY`) ou `api_params.<model>.api_key`.
- **Erros 429/quota**: reduza `prompt_keys`/cenários, use uma cota paga ou
  aumente o retry/backoff.
- **`groupadd: invalid group ID` no Docker**: execute com `USER_ID` e
  `GROUP_ID`, como no comando acima.
- **`Duplicate dispatch rule for <built-in function intern>`**: a imagem
  Ubuntu 22.04 usa o `python3.11` **3.11.0rc1**, que não tem
  `sys.get_int_max_str_digits` e quebra o `torch._dynamo`. Reconstrua a imagem
  com o Dockerfile atualizado:
  ```bash
  INSTALL_LAYA=true USER_ID=$(id -u) GROUP_ID=$(id -g) \
    docker compose build --no-cache smat
  ```
  Confirme com `docker compose run --rm smat python3 -VV` (deve ser uma versão
  final, como `3.11.15`). O log do fluxo Laya agora inclui o traceback completo
  na primeira ocorrência de cada erro.
- **A execução para em `Download complete`/`Reconstruction complete`**: é o
  download do checkpoint Laya no Hugging Face, não a análise. O compose usa
  `HF_CACHE_DIR` no host e `HF_HUB_DISABLE_XET=1`; confira `df -h` e
  `docker system df`. Depois do primeiro download bem-sucedido, use
  `HF_HUB_OFFLINE=1` para evitar novas checagens no Hub.
- **Modelo Laya baixado, mas o fluxo não avança**: rebuild com o
  `requirements-laya.txt` atual (`transformers<4.52`) e torch CPU
  (`TORCH_INDEX_URL`). Se a inferência estiver lenta, reduza
  `SMAT_LAYA_MAX_LEN` para `1024` (ou `512` no modelo `english`).
- **Resultados misturados**: arquive ou apague `SMAT/output-test-dest` entre
  execuções.

## 8. Reprodução fiel do artigo

Para os números do artigo, use:

- Código: <https://github.com/nathaliafab/SMAT/tree/codellama-integration>
- Artefatos: <https://doi.org/10.5281/zenodo.20938400>
- Inputs: `inputs/input-smat.json` e `inputs/input-smat-aster.json`
- Modelo: `codellama:70b` via Ollama

Este repositório Gemini é indicado para comparar um modelo alternativo, não
para reproduzir exatamente as Tabelas 1–5 do artigo.

## Atenção ao usar Windows

Se você usa o Windows como sistema operacional, ao clonar este projeto
provavelmente receberá um erro devido ao tamanho de alguns nomes de arquivo.
Instale o **WSL** e clone o projeto dentro dele. Recomendamos o VSCode com a
extensão **Remote - WSL**.
