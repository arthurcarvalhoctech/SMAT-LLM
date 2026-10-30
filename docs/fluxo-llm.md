# Fluxo de análise de interferência com LLM

## 1. Papel do fluxo

O fluxo LLM é uma **pré-análise opcional** executada antes da detecção
dinâmica do SMAT. Para cada método-alvo de cada cenário de merge, ele envia ao
provedor LLM:

- os trechos de código de `base`, `left`, `right` e `merge`;
- os campos, construtores e método extraídos de cada versão;
- os resumos declarados das mudanças de `left` e `right`;
- as definições dos três critérios de interferência do artigo
  *Interference and semantic conflicts*.

O resultado é uma **hipótese de triagem**, não uma confirmação. A detecção
baseada em execução continua sendo a referência do SMAT.

## 2. Os três critérios

1. **C1 — Divergência global**: existe um state element `x` tal que `B`, `L` e
   `R` calculam valores diferentes entre si.
2. **C2 — Perda de alteração do pai**: existe um state element `x` tal que
   `L` (ou `R`) calcula um valor diferente de `B` e de `Merge`.
3. **C3 — Efeito colateral inesperado do merge**: existe um state element `x`
   tal que `B`, `L` e `R` calculam o mesmo valor, mas `Merge` calcula outro.

O prompt pede, para cada critério:

- `probability` entre 0 e 1 (força da evidência);
- `triggered` (booleano);
- `evidence` (justificativa ligada ao código fornecido).

Além disso, pede `primary_criterion`, `affected_branch`, `confidence`,
`summary` e `reasoning`, em JSON estrito.

## 3. Ordem de execução

Quando habilitado, o fluxo roda para cada cenário com `runAnalysis=true`:

```text
Laya (se habilitado) -> LLM (se habilitado) -> detecção dinâmica (se habilitada)
```

As três flags são independentes. Qualquer combinação é válida, inclusive
nenhum fluxo, apenas um deles ou os três.

## 4. Configuração

| Variável | Padrão | Descrição |
|---|---|---|
| `SMAT_LLM_INTERFERENCE_DETECTION` | `false` | Liga/desliga o fluxo LLM. |
| `SMAT_LLM_INTERFERENCE_THRESHOLD` | `0.5` | Limiar para considerar um critério acionado. |
| `SMAT_LLM_INTERFERENCE_MAX_INPUT_CHARS` | `24000` | Limite do estado serializado enviado ao modelo. |
| `SMAT_LLM_INTERFERENCE_MODEL` | `LLM_MODEL` | Modelo específico do fluxo. `deepseek-flash` preservou a acurácia observada; `deepseek-chat` é o fallback. |
| `SMAT_LLM_INTERFERENCE_FALLBACK_MODEL` | — | Modelo usado no retry quando `finish_reason=length`. |
| `SMAT_LLM_INTERFERENCE_MAX_OUTPUT_TOKENS` | `8192` | Orçamento máximo de saída do fluxo. |
| `SMAT_LLM_INTERFERENCE_JSON_MODE` | `true` | Ativa `response_format={"type":"json_object"}` em provedores OpenAI-compatible. O `.env` atual usa `false` para preservar a acurácia. |
| `SMAT_LLM_INTERFERENCE_RETRY_ON_LENGTH` | `true` | Repete uma vez quando o provedor atinge `finish_reason=length`. |
| `SMAT_LLM_INTERFERENCE_LOG_DIR` | `.../reports/llm_interference` | Diretório de logs, JSONL e classificações. |

O provedor usa a configuração já existente do SMAT:

```env
LLM_PROVIDER=deepseek
LLM_MODEL=deepseek-flash
LLM_BASE_URL=https://api.deepseek.com
DEEPSEEK_API_KEY=...

# Modelo específico do fluxo LLM (preserva a acurácia observada):
SMAT_LLM_INTERFERENCE_MODEL=deepseek-flash
SMAT_LLM_INTERFERENCE_FALLBACK_MODEL=deepseek-chat
SMAT_LLM_INTERFERENCE_MAX_OUTPUT_TOKENS=8192
SMAT_LLM_INTERFERENCE_JSON_MODE=false
SMAT_LLM_INTERFERENCE_RETRY_ON_LENGTH=true
```

Também são suportados os provedores OpenAI-compatible, Gemini, Ollama e
Anthropic, conforme `llm_config.py`.

Quando o provedor retorna `finish_reason=length`, o fluxo tenta **uma vez**:

1. com `SMAT_LLM_INTERFERENCE_FALLBACK_MODEL`, se configurado; ou
2. dobrando `SMAT_LLM_INTERFERENCE_MAX_OUTPUT_TOKENS` (até 32768).

Se o retry também falhar, o erro é registrado sem interromper o fluxo
dinâmico. O log/JSONL/classificação incluem `finish_reason`, `attempts`,
`usage`, `reasoning_content_preview` e um `raw_response_preview` para
diagnóstico.

`SMAT_LLM_INTERFERENCE_LOG_DIR` deve ficar sob `SMAT/output-test-dest` para que
o viewer o leia. No Docker, use:

```env
SMAT_LLM_INTERFERENCE_LOG_DIR=/app/SMAT/output-test-dest/reports/llm_interference
```

Sem a variável, o default é
`<cwd>/output-test-dest/reports/llm_interference` (com `cwd` em `SMAT`).

## 5. Saídas

Cada execução cria:

```text
SMAT/output-test-dest/reports/llm_interference/
├── llm_interference_<run_id>.log
├── llm_interference_<run_id>.jsonl
└── classification/
    └── run_<run_id>/
        ├── 001_<projeto>_<Classe>_<metodo>.json
        └── ...
```

### 5.1 Log legível

O `.log` contém, por método:

- projeto, classe, método e assinatura;
- provider/modelo e threshold;
- caminhos das quatro versões e branches ausentes;
- probabilidade, `triggered` e evidência de cada critério;
- critério primário, branch afetado, confiança, resumo e raciocínio;
- erro e traceback, quando houver.

### 5.2 JSONL

Cada linha é um assessment com:

```json
{
  "run_id": "...",
  "timestamp": "...",
  "project": "...",
  "class": "...",
  "method": "...",
  "classification": "possible_interference | no_signal | error",
  "triggered_criteria": ["criterion_1_global_divergence"],
  "primary_criterion": "...",
  "affected_branch": "left | right | both | unclear",
  "confidence": "medium",
  "criteria": {
    "criterion_1_global_divergence": {
      "probability": 0.9,
      "triggered": true,
      "evidence": "..."
    }
  },
  "summary": "...",
  "reasoning": "..."
}
```

### 5.3 Classificação por método

Os JSONs em `classification/run_<run_id>/` têm o formato compacto usado pelo
viewer: `run_id`, `project`, `class`, `method`, `classification`,
`triggered_criteria`, `primary_criterion`, `affected_branch`, `confidence`,
`probabilities`, `evidence`, `summary`, `reasoning` e `error`.

## 6. Viewer

O viewer lê `reports/llm_interference` e mostra:

- uma coluna **LLM** na lista de cenários, com status e critérios acionados;
- um painel **Resultado da análise LLM** no detalhe do cenário, com os três
  critérios, registros, probabilidades, confiança e resumo/raciocínio.

O filtro por execução usa a janela do snapshot e pareia por projeto, classe e
método. Os arquivos brutos também aparecem no navegador de arquivos.

## 7. Limitações

- O LLM não executa código e pode errar; `possible_interference` é uma
  hipótese, não um conflito confirmado.
- `no_signal` não prova ausência de interferência.
- O modelo pode receber estado truncado quando o limite de caracteres é
  atingido; isso é registrado no log.
- A qualidade depende do provedor/modelo e da API key configurada.
- Falhas de API geram assessments de erro e não interrompem a detecção
  dinâmica.

### 7.1 Diagnóstico de erros do modelo

Se o log/classificação mostrar:

- `Empty response from provider` com
  `finish_reason=length` e `reasoning_tokens` igual ao orçamento, o modelo de
  raciocínio consumiu toda a saída antes de produzir o JSON. Use um modelo
  sem `reasoning_content` (por exemplo `deepseek-chat`) ou aumente o
  orçamento/fallback.
- `Invalid JSON from LLM`, verifique `raw_response_preview` e
  `finish_reason`. Ative `SMAT_LLM_INTERFERENCE_JSON_MODE=true` e, se o
  provedor continuar truncando, configure um fallback ou aumente o orçamento.
- `Extra data` após um objeto JSON válido é tolerado: o parser usa o primeiro
  objeto completo e ignora texto/objetos extras retornados pelo modelo.
- `attempts` mostra modelo, orçamento e `finish_reason` de cada tentativa.
- `usage` mostra os tokens de prompt/completion/raciocínio retornados pelo
  provedor.

## 8. Validação

```bash
cd SMAT
PYTHONPATH="$PWD" python -m unittest \
  nimrod.tests.test_llm_interference \
  nimrod.tests.test_pipeline
```

O fluxo é habilitado com:

```env
SMAT_LLM_INTERFERENCE_DETECTION=true
```

e executado normalmente por `./start.sh` ou por `python -m nimrod`.
