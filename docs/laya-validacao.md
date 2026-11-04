# Validação dos prompts Laya v2

As mudanças de engenharia não demonstram, por si, aumento de acurácia. Os padrões
`english`, `noul`, `512` e limiar `0.5` foram mantidos para comparação controlada.
O conjunto sintético de 20 casos é uma regressão pequena, insuficiente para escolher
um modelo final. Os resultados antigos em `dataset-sintetico/resultados` são de
prompts/contextos anteriores e não medem a versão `state-observables-v2`.

## Definir a observação antes de classificar

Um alvo aceita campos opcionais, além dos resumos existentes:

```json
{
  "method": "init()",
  "observations": ["types.get(\"a\")", "types.get(\"e\")"],
  "observationContext": "Create a fresh TableTypes, call init(), then inspect each key independently."
}
```

Esses campos especificam entradas e observações, não respostas esperadas. No
dataset sintético, `observationContext` contém a instrumentação já usada para
gerar o gabarito e `observations` lista suas chaves. Valores executados e rótulos
permanecem exclusivamente no gabarito. A comparação de um mapa inteiro pode dar
um resultado diferente da comparação de cada chave: treino e avaliação devem
adotar a mesma escolha.

## Exportar sem carregar pesos

Na raiz do repositório, com as dependências de `SMAT/requirements.txt` instaladas:

```bash
python scripts/laya_evaluate.py \
  --input dataset-sintetico/input-smat-sintetico.json \
  --gold dataset-sintetico/gold-sintetico.json \
  --map-path /app=. \
  --split-by scenario --export-only \
  --output runs/laya-v2/synthetic.jsonl
```

`--map-path` adapta caminhos do container para a máquina local; dentro de `/app`
no container não é necessário. Para o mergedataset, informe `--dataset-root` ou
`PATH_DATASET`. Fontes Java são suficientes; a ferramenta não executa os JARs.

Cada linha contém `{state, questions, expected, metadata}`. `state` vem de
`LayaMethodState.to_payload()` e `questions` de `build_questions()`, como em
produção. Só os critérios com gabarito são rotulados: a confiança e o ramo afetado
não recebem rótulos inventados. O formato é aceito pelo treinamento do Laya 0.4.12.
Exportar não treina um checkpoint. A ferramenta exige rótulos C1/C2/C3 explícitos
para exportação; um `Yes` geral não identifica o critério verdadeiro.

## Separar treino, validação e teste

A atribuição usa hash estável do grupo e de `--seed` (70/15/15 por faixa de hash).
O padrão agrupa por projeto; `--split-by scenario` agrupa por projeto/commit.
Todos os métodos de um grupo ficam na mesma partição. Reutilize a mesma seed e
agrupamento nas chamadas `--split train`, `--split validation` e `--split test`.
O relatório de exportação mostra os tamanhos; a distribuição não é estratificada.

Não use `--split all` para treinar e depois medir qualidade nos mesmos exemplos.
Famílias sintéticas derivadas do mesmo template podem vazar entre cenários;
separe essas famílias ao montar um benchmark final. Com a seed padrão, os 20
casos sintéticos ficam em 17/2/1 por cenário: isso é apenas um teste do mecanismo,
não uma base suficiente para calibrar. Com agrupamento por projeto, todos os
sintéticos ficam juntos, como esperado.

## Comparar formatos e orçamentos

Com `SMAT/requirements-laya.txt` instalado e checkpoints disponíveis:

```bash
python scripts/laya_evaluate.py \
  --input dataset-sintetico/input-smat-sintetico.json \
  --gold dataset-sintetico/gold-sintetico.json \
  --map-path /app=. --split-by scenario \
  --models english multilingual \
  --formats noul noul_ab choice_ab \
  --max-lens 512 1024 2048 --thresholds 0.3 0.5 0.7 \
  --output runs/laya-v2/comparison.json
```

Esse comando usa todos os casos para diagnóstico. Para selecionar parâmetros,
use uma validação maior e `--split validation`; depois congele a escolha antes de
usar `--split test`. Um caminho de checkpoint local também é aceito em `--models`.
A configuração de orçamento deve ser suportada pelo checkpoint escolhido.

A avaliação reutiliza o fluxo real, inclusive abstenção por fonte ausente ou
truncamento. Compara os formatos sem assumir que A/B melhora a qualidade. Em
`choice_ab`, lê `probabilities.A`, nunca a confiança da opção vencedora.

O JSON registra configuração, versão do pacote/prompt, digest do estado,
respostas brutas, telemetria e métricas por limiar. Rótulos ausentes ou contestados
são excluídos e enumerados. A junção usa projeto/commit/classe/assinatura, nunca
posição de linha. Contém:

- TP, FP, TN, FN, abstenções e positivos não avaliados;
- cobertura (fração com decisão) e precisão;
- recall sobre **todos** os positivos, incluindo os que tiveram abstenção;
- métricas por critério e Brier apenas nos exemplos avaliados com rótulo específico.

Também registra hashes dos arquivos de entrada/gabarito, contagens de erros e
análises incompletas e tempos por método. O tempo inclui extração dos fontes e,
na primeira chamada, carregamento do checkpoint; não é um benchmark isolado da GPU.

Abstenções não contam como verdadeiros negativos. `possible_interference` pode
ser parcial se algum critério válido aciona; consulte `assessment_complete`.
O Brier condicional deve ser lido junto à cobertura, para não favorecer um
modelo que só responde casos fáceis.

## Usar limiares validados

`SMAT_LAYA_THRESHOLD_C1`, `SMAT_LAYA_THRESHOLD_C2` e `SMAT_LAYA_THRESHOLD_C3`
sobrescrevem o global. Campos vazios herdam o global; NaN e infinito são rejeitados.
`SMAT_LAYA_QUESTION_FORMAT` seleciona `noul`, `noul_ab` ou `choice_ab`.

Escolha limiares em validação pelo custo de falsos positivos e conflitos perdidos;
não interprete `analysis_confidence` como probabilidade de acerto. O relatório
preserva esse nome por compatibilidade, mas agora usa uma rubrica de evidência.
C1 com probabilidade superior a C2 gera aviso de inconsistência; as probabilidades
originais não são corrigidas artificialmente.

## Testes sem inferência

Na raiz, com `SMAT` no `PYTHONPATH`:

```bash
python -m unittest nimrod.tests.test_laya_interference nimrod.tests.test_laya_quality nimrod.tests.test_laya_classification nimrod.tests.test_source_code nimrod.tests.test_pipeline nimrod.tests.test_dynamic_interference_flag
python -m unittest discover -s scripts -p test_laya_evaluate.py
```
