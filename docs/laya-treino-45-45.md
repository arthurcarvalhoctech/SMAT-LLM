# Novo experimento: 45 casos selecionados para treino e 45 reservados

Abra `laya_45_45_colab.ipynb` no Colab, selecione uma GPU T4 e execute as
células em ordem. Envie **somente** `laya_45_treino_colab.zip` quando solicitado.
O notebook instala o Laya e baixa novamente o modelo base original. Não envie
o checkpoint anterior `laya_semantic_global`: ele já foi ajustado com parte
desses casos e contaminaria a comparação.

## Divisão congelada antes das variações

| Uso | Casos reais | Positivos | Negativos | Apresentações |
|---|---:|---:|---:|---:|
| Treino selecionado | 45 | 9 | 36 | 180, quatro ordens de B/L/R/M |
| Teste reservado | 45 | 8 | 37 | 45, somente a ordem original |

A divisão usa seed 42 e estratificação por rótulo. Projeto+merge e duplicatas
exatas de código/atributos das quatro versões ficam no mesmo lado, mesmo
quando os nomes das classes ou métodos diferem. O código de divisão não usa
probabilidades, acertos, perdas ou tamanhos dos casos para escolher o lado.
A tabela `divisao_45_45.csv` permite conferir todos os IDs e partições.

O pacote de treino contém apenas os 45 casos selecionados, as perguntas,
proveniência, manifesto, avisos dos fontes e o treinador. O arquivo
`laya_45_teste_reservado.zip` é separado: não o envie ao notebook de treino.
Os 180 exemplos são variações de apresentação dos mesmos 45 casos reais,
sem criar novos comportamentos ou inventar rótulos C1/C2/C3.

## O limite de contexto continua existindo

Selecionar 45 casos não garante que todos caibam no encoder de 8192 tokens.
O notebook audita **as quatro apresentações** antes de treinar. Quando uma
delas excede `tokens_do_estado + 512 + 32 <= 8192`, o caso inteiro é excluído
do ajuste e aparece em `context_audit.json`. O número efetivo de casos e de
positivos/negativos é impresso antes do treino e salvo no relatório final.

Não trocamos os casos longos por casos do teste, não cortamos silenciosamente
B/L/R/M e não atribuímos o rótulo do caso a janelas isoladas. O JSONL continua
tendo os 45 selecionados, mas o relatório não deve chamar de “45 casos
efetivamente treinados” um ajuste que usou menos depois dessa auditoria.
O Colab repete a auditoria usando o tokenizer do modelo base fixado.

A auditoria local das quatro apresentações encontrou **39 casos completos
utilizáveis (7 positivos e 32 negativos), totalizando 156 apresentações**.
Seis casos selecionados excedem o orçamento. Ela usou apenas o tokenizer
inalterado do experimento anterior, sem carregar pesos; o treino no Colab
verifica novamente essa contagem com a base original fixada. O arquivo
`context_preflight.json` registra os IDs e comprimentos dessa conferência.

## Configuração do notebook

- Base: `convaiinnovations/laya-multilingual`, revisão
  `1720e3e3357cfe1e281542e223f8273b0890ca34`.
- Laya: revisão `b8a0f0991d95a953411f2e16f91bddc2ffdaf79a`, mesmas
  primitivas `items_from_rows`, `TrainConfig`, `train_model` e `save_checkpoint`
  da implementação oficial.
- Formato: `{state, questions, gold}`; somente `semantic_interference`
  supervisionada pelo Yes/No original.
- Orçamento fixo inicial: 4 épocas, micro-batch 1, acumulação 8, RLCD,
  learning rates 1e-5 para o encoder e 1e-4 para a cabeça, seed 42.
- Contexto 8192, cabeçalho 512, mixed precision e gradient checkpointing.
- O encoder não é congelado por padrão. A opção está visível no notebook.
- Limiar fixo 0,5; nenhuma procura de limiar, calibração de temperaturas,
  seleção de épocas ou avaliação nos 45 reservados durante o treinamento.

Quatro épocas são um orçamento inicial definido antes do teste, e não um
valor otimizado ou uma garantia contra overfitting. As temperaturas originais
da base são preservadas e não são consideradas calibradas para este ajuste.
Se desejar escolher épocas ou parâmetros por validação, separe uma parte
desses 45 de desenvolvimento; nunca use os 45 reservados para isso.

O novo checkpoint será baixado como `laya_semantic_45_45_checkpoint.zip`.
Ele é separado do experimento anterior. `checkpoint_latest` é um salvamento
de pesos por época, não um estado completo de retomada do otimizador.

## Avaliar os outros 45 depois

Finalize os pesos e parâmetros antes de abrir os dados reservados. Abra
`laya_45_45_avaliacao_colab.ipynb` e envie os dois arquivos:

1. `laya_semantic_45_45_checkpoint.zip`, produzido pelo novo treinamento.
2. `laya_45_teste_reservado.zip`, fornecido separadamente.

Você pode enviar os dois juntos ou um por vez. A etapa 2 reaproveita os ZIPs
que já estão na sessão do Colab. Se enviou somente o checkpoint, execute a
célula atualizada novamente e envie apenas o pacote de teste que falta;
não é necessário repetir o upload dos pesos.

O avaliador confere o hash do arquivo de teste, os IDs, os grupos e o
identificador do experimento. Ele rejeita o checkpoint antigo e mantém o
limiar em 0,5. Por padrão, casos longos aparecem como excluídos por contexto;
a opção de janelas é exploratória e fica desligada. O relatório distingue
cobertura, métricas de estado completo e eventuais escores agregados por
janelas. Os 45 reservados não devem ser reutilizados para retreinar e depois
continuar sendo apresentados como um teste independente.

Esses casos não participaram deste novo ajuste, mas o mergedataset já foi
examinado nos experimentos anteriores. Portanto, isso é uma nova divisão
interna, não um dataset externo ainda desconhecido. Reduzir o treino para
45 casos não elimina overfitting; a comparação no grupo reservado ajuda a
medir a generalização dentro desse corpus.

Referências: [notebook oficial](https://github.com/NandhaKishorM/laya/blob/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb),
[API de treino fixada](https://github.com/NandhaKishorM/laya/blob/b8a0f0991d95a953411f2e16f91bddc2ffdaf79a/laya/train.py).

## Reproduzir a avaliação localmente neste projeto com Docker

O serviço `laya-eval-holdout45` foi configurado para o checkpoint novo,
extraído em `laya_checkpoints/laya_semantic_45_45_checkpoint`. Essa pasta
deve conter diretamente `model.safetensors`, `rl_agent_config.json`,
`manifest.json`, `questions.json`, `encoder/` e `tokenizer/`.
O modelo antigo permanece em `laya_checkpoints/laya_semantic_global`.

Com Docker Desktop aberto e usando contêineres Linux, execute na raiz do
projeto:

```powershell
Set-Location -LiteralPath 'C:\Users\Administrador\Documents\CodeReview&Merge\SMAT-LLM'
docker compose -f docker-compose.laya-eval.yml build laya-eval
docker compose -f docker-compose.laya-eval.yml run --rm laya-eval-holdout45
```

O build é necessário apenas quando a imagem ainda não existe ou suas
dependências foram alteradas. A avaliação usa CPU, a pergunta global
`semantic_interference`, limiar 0,5, contexto 8192, cabeçalho 512 e sem
`--long-context`, reproduzindo `LONG_CONTEXT = False` do Colab. As opções
`SMAT_*` do `.env` principal não são usadas por esse avaliador. Não é
necessário alterar o `.env` nem realizar um novo treinamento.

Saídas:

```text
mergedataset-full/resultados/holdout_45_evaluation_local.json
mergedataset-full/resultados/holdout_45_evaluation_local.csv
mergedataset-full/resultados/holdout_45_evaluation_local_roc.csv
```

O checkpoint e os dados são montados somente para leitura. O JSON do Colab
fica separado; a reprodução local grava arquivos com sufixo `_local`.
São esperados 39 estados completos avaliáveis e 6 casos longos excluídos.
Compare os hashes dos dados/modelo e as decisões por ID; probabilidades
podem variar um pouco entre CPU e GPU. O procedimento não executa o fluxo
principal C1/C2/C3 do SMAT.

Conferência opcional dos dados e do experimento sem carregar os pesos:

```powershell
docker compose -f docker-compose.laya-eval.yml run --rm laya-eval-holdout45 --model /model --data /data/holdout.jsonl --out /results/holdout_45_evaluation_local.json --device cpu --dry-run
```

Se aparecer `Use the new 45/45 checkpoint`, confira o nome da pasta e se
foi extraído o ZIP novo. Se aparecer `Holdout file differs`, use o
`holdout.jsonl` original desta divisão, sem editar ou gerar novamente os
casos. O comando de auditoria deve informar 45 casos, 8 Yes, 37 No,
limiar 0,5 e ausência de sobreposição com o treino.
