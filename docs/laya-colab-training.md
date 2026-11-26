# Treino do Laya no Google Colab com casos reais

Abra `notebooks/laya_semantic_interference_colab.ipynb` no Colab, ative GPU e execute as células em ordem. Na célula de upload, envie `notebooks/laya_mergedataset_full_colab.zip`. O pacote é autossuficiente: não depende de caminhos desta máquina, JARs, APIs pagas nem clone deste projeto. O treinamento e o download de pesos são executados no Colab, não nesta preparação local.

## Alternativa: Kaggle

Use `notebooks/laya_semantic_interference_kaggle.ipynb`. Crie um notebook em https://www.kaggle.com/code, use **File → Import Notebook** e envie o `.ipynb`. Em **Settings → Accelerator**, escolha uma GPU disponível (por exemplo T4 x2); ative **Internet**. Esta adaptação usa uma GPU, mesmo quando duas estão disponíveis.

No painel **Input**, use **Add Input / Upload** para anexar o mesmo `laya_mergedataset_full_colab.zip` como um dataset privado. O nome Colab no ZIP não impede seu uso no Kaggle. O notebook aceita tanto o ZIP intacto como o conteúdo descompactado pela plataforma, copia os dados de `/kaggle/input` para `/kaggle/working/laya_smat` e não depende de `google.colab`.

Execute as células em ordem. Mantenha `MODE = 'scenario'`; a seção 5 audita o contexto, a 6 treina e a 9 produz `/kaggle/working/laya_smat_checkpoint.zip`. Baixe o ZIP pelo link final ou pelo painel de arquivos/Output. Use **Save Version** e preserve os arquivos de saída ao encerrar a sessão; salvar apenas o código não preserva necessariamente os pesos.

A versão Kaggle foi verificada localmente quanto à sintaxe e ao carregamento de dados nos dois formatos; o treinamento em GPU ainda precisa ser executado na plataforma.

## O que a base permite aprender

O único rótulo disponível é **Locally Observable Interference** do CSV. Ele supervisiona a pergunta auxiliar `semantic_interference`, que pergunta sobre interferência semântica observável no cenário completo. Ela difere da antiga T1, que perguntava apenas se as mudanças poderiam interagir.

As sete perguntas de `SMAT/nimrod/laya_interference/criteria.py` são exportadas exatamente, com as instruções negativas e os candidatos fixos de testemunha. Seus rótulos ficam **ausentes**, inclusive nos casos No. Ausência de interferência no estudo não fornece, por si só, respostas independentes para todas essas perguntas. Yes não identifica C1/C2/C3. Não se inventam testemunhas, ramo afetado nem confiança.

Portanto, o notebook é executável agora para **detecção global**. Ainda não constitui um treino supervisionado das sete perguntas específicas. Para cumprir essa segunda etapa, é necessário revisar/anotar os casos reais por pergunta. `annotations.json` inclui todos os IDs para esse trabalho; suas respostas e evidências são propagadas a todas as variantes. O modo `criteria` exige positivos e negativos de cada critério no treino. Métricas por critério só fazem sentido quando houver rótulos independentes nas partições de validação/teste também.

Não se alteram `criteria.py`, o fluxo de produção, o checkpoint configurado nem `.env`. O SMAT atual não consulta a pergunta auxiliar; usar o novo detector global em produção requer integração e avaliação próprias. Não basta trocar `SMAT_LAYA_MODEL` e assumir que os critérios foram aprendidos.

## Contagem e ampliação

Fonte autoritativa desta preparação: `mergedataset-full/semantic-conflicts/sample-semantic-conflicts.csv`, e não o gold JSON reduzido nem os 20 casos sintéticos anteriores.

| Etapa | Quantidade |
|---|---:|
| Linhas do CSV | 95 |
| Rotuladas Yes/No | 91 (17 Yes, 74 No) |
| Inconclusivas excluídas | 4 |
| Sem fontes no artefato público | 1 No, linha 75, IndexRequest, c1d44780675a9ff43e87a44f62969a0214928988 |
| Casos reais com B/L/R/M | 90 (17 Yes, 73 No) |
| Apresentações por caso | 4 |
| Exemplos totais | **360** |
| Treino | 57 casos, 228 apresentações |
| Validação/calibração | 16 casos, uma apresentação por caso |
| Teste | 17 casos, uma apresentação por caso |

São 4× os 90 casos utilizáveis, aproximadamente 3,96× as 91 linhas rotuladas. Não são 360 comportamentos independentes. As quatro vistas mudam somente a ordem das seções explicitamente identificadas B/L/R/M: B-L-R-M, B-R-L-M, M-B-L-R e L-R-B-M. Não se renomeiam identificadores, alteram constantes, reescrevem código ou produzem contrafactuais. O código e os campos de cada versão permanecem os mesmos. A ampliação é deliberadamente conservadora e pode oferecer ganho limitado.

O split agrupa **projeto + merge antes da ampliação**. Classes/métodos do mesmo merge e todas suas vistas ficam na mesma partição. `all.jsonl` inclui também as vistas extras reservadas de validação/teste; não deve ser fornecido como treino quando se pretende usar os splits publicados para avaliação.

Algumas declarações da planilha não são assinaturas Java exatas. Quando o alvo é sobrecarregado e não há correspondência exata, o extrator mantém todos os overloads desse nome em vez de selecionar um arbitrário. Duas linhas sem declaração usam a classe inteira. Esses escopos estão em `cases.json`; contextos excessivos podem ser excluídos pelo orçamento de tokens no Colab. O parser aceita trechos de fontes; não compila nem executa os projetos reais, não resolve chamadas externas e não demonstra equivalência semântica por execução. O texto é mantido, mas a representação é uma aproximação do contexto real.

O extrator resolve os nomes históricos dos diretórios spring-boot, a classe aninhada do Webbit, o sufixo de método indevido na coluna Class do MongoDB e o arquivo upstream `rigth.java` do Eureka. Nunca substitui fontes ausentes por código do projeto de demonstração.

## Formato de dados

Cada linha tem `state` textual, `questions` tipadas, `gold` com distribuições e `_meta` com origem, hashes, ID do caso, grupo, split e vista. A forma de `gold` é a do notebook oficial:

```json
{"semantic_interference": {"label": "true", "probabilities": {"false": 0.0, "true": 1.0}}}
```

Não há rótulos de critérios na base atual. `annotations.json` aceita, por caso:

```json
{"ID_DO_CASO": {"answers": {"criterion_2_parent_change_loss": true}, "evidence": "Referência ao teste/revisão e valores observados para o mesmo elemento em B/L/R/M"}}
```

Isso ilustra o formato, não anota nenhum caso. Use booleanos para noul, opções exatas para choice e inteiros 0–4 para score. Não adicione um nível de confiança só porque a planilha tem Yes/No. Revise também a consistência de `primary_criterion` com os critérios marcados. Os IDs são estáveis e as linhas CSV são contadas com o cabeçalho na linha 1.

## Treino e avaliação

O treinador adapta o notebook oficial de duas T4 para uma GPU, usando diretamente `laya.train.items_from_rows`, `train_model` com RLCD, `calibration_records` e `save_checkpoint`, e `laya.calibrate.fit_temperature_map`. O Laya fica fixado no commit `b8a0f0991d95a953411f2e16f91bddc2ffdaf79a`. Dependências resolvidas, snapshot do modelo base, seed e relatórios são exportados. O modelo base padrão é `convaiinnovations/laya-multilingual`.

Configuração inicial: 12 épocas, microbatch 1, acumulação 8, encoder LR 1e-5, head LR 1e-4, contexto 8192, head 512, mixed precision e gradient checkpointing. O número de updates é impresso. A configuração é experimental, não uma promessa de desempenho ou tempo. A quantidade de positivos é pequena e há desbalanceamento; reporte precisão e recall, não apenas acurácia.

A auditoria conservadora exige que **todo** o estado caiba junto com a reserva da pergunta. Caso contrário, exclui o caso inteiro de sua partição e registra os IDs; não corta silenciosamente M ou outros trechos. A contagem efetiva pode ser menor que 360 e aparece em `context_audit.json`. O notebook interrompe se uma partição perder todos os exemplos de uma classe. Não se cria uma avaliação perfeita removendo exemplos difíceis sem reportar as exclusões.

As temperaturas são ajustadas na validação. Como a calibração oficial atua por tipo de pergunta, pode mudar também as probabilidades de perguntas específicas sem rótulo; elas continuam não validadas. O teste é avaliado antes/depois, com uma vista original por caso. Há também precisão, recall, F1, matriz de confusão, Brier e limiar escolhido somente na validação. O limiar é exploratório: a mesma validação pequena também foi usada para temperaturas. Não se selecionam épocas ou limiares usando o teste. O notebook não implementa early stopping.

`checkpoint_latest` contém os pesos ao fim de cada época, sem estado do otimizador para retomada exata. Para persistir em encerramentos da sessão, use o caminho do Google Drive mostrado no notebook. O ZIP final inclui o checkpoint carregável com `laya.Agent`, perguntas, auditoria, métricas e ambiente; não publica nada no Hub.

### Correção de notebooks antigos: erro `Agent.__init__() got an unexpected keyword argument 'max_len'`

Na versão fixada do Laya, o construtor recebe `laya.Agent(caminho, device='cuda')`. Os argumentos `max_len=MAX_LEN` e `head_max_len=HEAD_MAX_LEN` pertencem a `agent.predict(...)`. As versões atuais dos notebooks Colab/Kaggle aplicam esses argumentos às predições dos blocos 7 e 8.

Se o treino já terminou e o erro apareceu no bloco 7, preserve a sessão e o diretório `OUTPUT`; corrija apenas os blocos 7/8 e continue a avaliação. Não é necessário executar o bloco 6 novamente. Só remover o argumento do construtor sem ajustar as predições pode deixar a avaliação da base usando um orçamento de contexto diferente do treino.

## Reprodução local dos dados

```powershell
.\.venv\Scripts\python.exe scripts/fetch_laya_real_sources.py
.\.venv\Scripts\python.exe scripts/prepare_laya_colab.py
.\.venv\Scripts\python.exe scripts/build_laya_colab_notebook.py
.\.venv\Scripts\python.exe scripts/build_laya_kaggle_notebook.py
.\.venv\Scripts\python.exe -m unittest scripts/test_laya_colab_data.py
```

O download usa somente fontes Java públicos do artefato `spgroup/mergedataset`, revisão `04a180179b6098bac96a9cd83fe4f5ff5d45ea86`, verificando o Git blob SHA de cada arquivo. O cache completo fica em `.laya_smat/mergedataset_sources` (já ignorado pelo Git); os dados publicáveis contêm trechos e proveniência. O ZIP retém os avisos encontrados no início dos fontes em `SOURCE_NOTICES.txt`. Os trechos permanecem sujeitos às licenças dos projetos de origem.

## Referências

- [Notebook oficial solicitado](https://github.com/NandhaKishorM/laya/blob/b8a0f0991d95a953411f2e16f91bddc2ffdaf79a/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb)
- [README oficial](https://github.com/NandhaKishorM/laya/blob/b8a0f0991d95a953411f2e16f91bddc2ffdaf79a/README.md)
- [Formato de gold e primitivas de fine-tuning](https://github.com/NandhaKishorM/laya/blob/b8a0f0991d95a953411f2e16f91bddc2ffdaf79a/docs/finetune.md)
- [Artefato original dos casos reais](https://github.com/spgroup/mergedataset/tree/04a180179b6098bac96a9cd83fe4f5ff5d45ea86)
