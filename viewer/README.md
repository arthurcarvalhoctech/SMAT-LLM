# SMAT Scenario Explorer

Aplicação Next.js + Tailwind CSS para explorar os artefatos de
`SMAT/output-test-dest` sem escrita no diretório.

## O que ela mostra

- **Execuções**: snapshots em `scenarios/<dataset>_<timestamp>`.
- **Cenários**: pastas `NNN_<projeto>` com os arquivos `base`, `left`, `right`
  e `merge`.
- **Fontes**: abas por branch, visualização por classe/fonte, modo bruto,
  cópia e download.
- **Diff 3 vias**: left, merge e right alinhados; base usada apenas como
  referência. Mudanças de left em vermelho, merge em verde e right em azul;
  linhas excluídas em tom mais claro.
- **Laya**: classificações em `reports/laya/classification/run_*` e logs
  `.log`/`.jsonl`.
- **LLM**: classificações em `reports/llm_interference/classification/run_*`
  e logs `.log`/`.jsonl`.
- **Acurácia**: cada execução de Laya/LLM mostra o percentual de acerto e a
  lista de métodos em que acertou/errou, comparando com os rótulos de
  referência em `viewer/data/ground-truth.json`.
- **Relatórios**: JSONs diretamente em `reports/`.
- **Arquivos**: navegador genérico de todo o `output-test-dest`, incluindo
  `projects/`, com prévia de texto e download.

## Docker Compose

O serviço `viewer` está no `docker-compose.yml` da raiz.

```bash
# na raiz do SMAT-LLM
docker compose up --build -d viewer

# http://localhost:3000
```

O container monta `./SMAT/output-test-dest` em
`/data/output-test-dest:ro`. Para outra porta:

```bash
VIEWER_PORT=3001 docker compose up --build -d viewer
```

Logs e parada:

```bash
docker compose logs -f viewer
docker compose down viewer
```

O serviço `smat` continua sendo executado separadamente:

```bash
docker compose run --rm --build smat bash -lc 'cd /app && python3 run_experiment.py'
```

## Desenvolvimento local

```bash
cd viewer
npm install
SMAT_OUTPUT_DIR=../SMAT/output-test-dest npm run dev
```

Abra `http://localhost:3000`. O padrão de `SMAT_OUTPUT_DIR`, quando não
definido, é `../SMAT/output-test-dest` relativo ao diretório `viewer`.

## Build de produção

```bash
cd viewer
npm run build
SMAT_OUTPUT_DIR=../SMAT/output-test-dest npm run start
```

O `Dockerfile` usa `output: "standalone"` do Next.js e roda como usuário não
root. O volume de saída é somente leitura; a aplicação não altera os
artefatos do SMAT.

## Ground truth da acurácia

Os rótulos usados nos indicadores de acerto ficam em
`viewer/data/ground-truth.json`. O arquivo é gerado a partir de
`dataset-sintetico/resultados/probe_t1.json`,
`mergedataset-full/semantic-conflicts/sample-semantic-conflicts.csv` e dos
manifestos de cenário. Para regenerar:

```bash
# na raiz do repositório
python3 scripts/export_viewer_ground_truth.py
```

A acurácia considera métodos únicos com rótulo disponível. Classificações
`error`, `uncertain` ou sem predição contam como erro.
