# Laya: validação cruzada em três blocos

O protocolo divide os 90 casos reais antes de gerar as apresentações de
treinamento. Em cada rodada, dois blocos treinam e o terceiro testa:

| Rodada | Treino | Teste |
|---|---|---|
| 1 | Blocos 2 e 3 | Bloco 1 |
| 2 | Blocos 1 e 3 | Bloco 2 |
| 3 | Blocos 1 e 2 | Bloco 3 |

São três modelos diferentes, cada um carregado novamente da mesma revisão
original de `convaiinnovations/laya-multilingual`. Não se continua o treino
da rodada anterior nem se usa um dos checkpoints já ajustados ao mergedataset.
Um caso pode ser treino em outras rodadas, mas sua previsão de teste vem
exclusivamente da rodada que o deixou de fora. É essa previsão que entra no
resultado out-of-fold (OOF).

## Como os positivos foram distribuídos

Aqui “positivo” é o rótulo Yes da planilha. “Verdadeiro positivo” é um acerto
que só pode ser contado depois da inferência. Não foi feita seleção por
acertos, probabilidades ou perdas dos testes anteriores.

| Bloco | Casos selecionados | Positivos | Negativos | Casos completos utilizáveis | Positivos completos |
|---|---:|---:|---:|---:|---:|
| 1 | 30 | 6 | 24 | 27 | 5 |
| 2 | 30 | 6 | 24 | 26 | 5 |
| 3 | 30 | 5 | 25 | 25 | 5 |
| Total | 90 | 17 | 73 | 78 | 15 |

Dezessete não é divisível por três; 6/6/5 é a divisão mais equilibrada sem
inventar, excluir por rótulo ou duplicar positivos. Os 15 positivos que cabem
inteiramente no contexto foram distribuídos em 5/5/5. Cada rodada tem dez
positivos reais completos no treino e cinco no teste. Os negativos completos
do treino são 41, 42 e 43, respectivamente.

Todos os casos de um mesmo projeto+merge e as duplicatas exatas de código e
atributos B/L/R/M ficam no mesmo bloco. Por isso o número de casos completos
difere um pouco entre os blocos. Agrupar apenas por caso, depois de aumentar
os dados, deixaria métodos/classes ou variações relacionadas em lados
opostos e poderia inflar o resultado.

O arquivo `blocos_cv3.csv` identifica o bloco de cada ID, rótulo, grupo,
projeto, merge, classe, método e elegibilidade de contexto. A divisão foi
fixada com seed 42 e alocação agrupada de contagens inteiras. O balanceamento
usa rótulos e elegibilidade de contexto previamente auditada, não desempenho.

## O que o dataset contém

O dataset atual já é suficiente para executar essa avaliação interna. Para
cada caso são necessários ID estável, fontes B/L/R/M, classe/método, rótulo
Yes/No e projeto+merge para os grupos. Não é necessário criar casos novos.
Não se deve transformar inconclusivos em negativos nem usar o Yes/No como
rótulo C1/C2/C3, que exige anotações específicas.

O ZIP inclui `fold_1`, `fold_2` e `fold_3`. Em cada pasta:

- `train.jsonl`: 60 casos selecionados, quatro ordens de B/L/R/M por caso,
  totalizando 240 apresentações antes do filtro de contexto.
- `train_original.jsonl`: os mesmos 60 casos, uma apresentação original,
  usados somente para diagnosticar treino versus teste.
- `test.jsonl`: os 30 casos do bloco reservado, uma apresentação original.
- `fold_manifest.json`: IDs, grupos, contagens e hashes dos arquivos.

As quatro apresentações são variações de ordem das seções e preservam o
código. Não representam quatro observações independentes. São usadas somente
para otimizar os blocos de treino da rodada. O teste sempre usa a ordem original.

## Contexto e cobertura

A elegibilidade foi auditada antes da divisão, considerando todas as quatro
apresentações e o orçamento `tokens_estado + 512 + 32 <= 8192`. Os 12 casos
maiores continuam nos blocos e no denominador da cobertura, mas não entram
no ajuste ou nas métricas de estado completo. Não se cortam fontes nem se
atribuem rótulos do cenário a janelas isoladas. O Colab repete a auditoria
com o tokenizer da base original e exige a mesma coorte de casos utilizáveis.

Assim, a avaliação OOF principal cobre 78 casos reais (15 positivos e 63
negativos), com cobertura de 86,67% dos 90 selecionados. Os 12 restantes são
registrados como `context_excluded`. Não há inferência por janelas neste protocolo.

## Como executar no Colab

1. Abra `laya_validacao_cruzada_3fold_colab.ipynb` e ative uma GPU T4.
2. Na seção de upload, envie apenas `laya_cv3_colab.zip`.
3. Confira os blocos e a cobertura mostrados pelo notebook.
4. Fixe os parâmetros antes da avaliação. O padrão reproduz o novo experimento:
   quatro épocas, RLCD, micro-batch 1, acumulação 8, encoder LR 1e-5, head LR
   1e-4, contexto 8192, cabeçalho 512, seed 42 e limiar 0,5.
5. Execute a auditoria e os três treinamentos. Cada treinamento é um processo
   novo, que carrega a base original e libera a GPU ao terminar.
6. Execute a consolidação e baixe o ZIP de relatórios.

O Laya está fixado na revisão `b8a0f0991d95a953411f2e16f91bddc2ffdaf79a`;
a base na revisão `1720e3e3357cfe1e281542e223f8273b0890ca34`. Os logs mostram
rodada, época e passo. Os pesos finais são salvos em `fold_N/checkpoint`,
separados dos experimentos anteriores. O código não salva todos os estados
do otimizador e não retoma uma rodada pela metade. Se usar uma pasta
persistente no Drive, rodadas completas podem ser reutilizadas somente quando
experimento, parâmetros, dados e hash dos pesos conferirem.

O download padrão leva apenas relatórios, não os três arquivos de pesos,
para manter o pacote pequeno. Se quiser preservar os modelos, use uma pasta
persistente no Drive ou exporte separadamente `fold_1/checkpoint`,
`fold_2/checkpoint` e `fold_3/checkpoint` antes de encerrar a sessão.

## Como interpretar o resultado

`cross_validation_results.json` reúne precisão, recall, F1, acurácia, Brier,
ROC AUC, cobertura e uma linha OOF por caso. O CSV correspondente identifica
qual modelo avaliou cada caso. Há também resultados por rodada, métricas
diagnósticas nos exemplos de treino e média/desvio-padrão das três rodadas.

Média dos F1 por rodada e F1 calculado de todas as previsões OOF não são a
mesma estatística; ambos são mostrados. A AUC OOF reúne escores de três
modelos, enquanto a média das AUCs descreve os resultados separados. O
desvio-padrão entre três rodadas não é um intervalo de confiança. Escores
retêm as temperaturas da base e não recebem nova calibração nesta avaliação.

As épocas, limiar e demais opções são fixos: não use o bloco de teste para
escolher o melhor checkpoint ou o melhor parâmetro. Para selecionar
parâmetros com validação cruzada, é necessário um nível interno de validação
ou uma avaliação externa separada. Os dados já foram examinados em estudos
anteriores; esta é uma avaliação interna exploratória, não um novo teste cego.
Distribuir positivos igualmente entre blocos também não corrige por si só
o desequilíbrio entre positivos e negativos nem garante melhora do modelo.

O grupo adotado é projeto+merge, não o projeto inteiro. Merges diferentes do
mesmo projeto podem aparecer no treino e no teste; este protocolo não mede
exclusivamente a transferência para projetos nunca vistos. Esse seria outro
critério de agrupamento e poderia produzir blocos de tamanhos diferentes.

Referências: [validação cruzada com grupos](https://scikit-learn.org/stable/modules/cross_validation.html#cross-validation-iterators-for-grouped-data),
[estratificação e grupos](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html),
[API de treino do Laya fixada](https://github.com/NandhaKishorM/laya/blob/b8a0f0991d95a953411f2e16f91bddc2ffdaf79a/laya/train.py).
