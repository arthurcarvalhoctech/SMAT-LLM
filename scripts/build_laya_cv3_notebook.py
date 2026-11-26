"""Build a three-fold Colab package; GPU runs remain the user's next step."""
import json
from pathlib import Path
import zipfile

try:
    from scripts.build_laya_45_45_notebooks import INSTALL, cell
except ModuleNotFoundError:
    from build_laya_45_45_notebooks import INSTALL, cell

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'laya_training_data/mergedataset_cv3'
OUT=ROOT/'notebooks'


def main():
    OUT.mkdir(exist_ok=True)
    cells=[]
    def md(s): cells.append(cell('markdown',s))
    def code(s): cells.append(cell('code',s))
    md('''
# Laya: validação cruzada agrupada em 3 blocos

Em cada rodada, dois blocos treinam e um testa. Cada modelo começa novamente da **base original**, sem continuar um checkpoint já ajustado. Cada caso recebe uma única previsão out-of-fold do modelo que não treinou com seu grupo.

São **90 casos selecionados**, em três blocos de 30, com **6, 6 e 5 positivos**. Projeto+merge e duplicatas B/L/R/M permanecem juntos. Como 17 não é divisível por 3, a distribuição não pode ser exatamente igual sem alterar a base.

**Contexto:** 78 casos completos cabem no orçamento (15 positivos e 63 negativos). Após o filtro, os testes têm **27, 26 e 25 casos**, com **exatamente 5 positivos por bloco**. Os 12 maiores ficam registrados como excluídos; não são truncados ou avaliados por janelas.

Este notebook executa três treinamentos, não apenas três inferências. Ative uma GPU T4. Não há garantia de melhora: a CV mede a estabilidade da generalização. O corpus já foi examinado em experimentos anteriores; esta é avaliação interna exploratória.
''')
    md('## 1. Instalar a revisão fixada do Laya')
    code(INSTALL+"\nassert torch.cuda.is_available(), 'Ative uma GPU T4 para executar os treinamentos.'")
    md('## 2. Enviar o pacote dos três blocos')
    code('''
from pathlib import Path
from google.colab import files
import json, zipfile
WORK=Path('/content/laya_cv3')
WORK.mkdir(parents=True,exist_ok=True)
uploaded=files.upload()
assert len(uploaded)==1 and 'laya_cv3_colab.zip' in uploaded, 'Envie apenas laya_cv3_colab.zip.'
with zipfile.ZipFile('laya_cv3_colab.zip') as archive:
    for member in archive.infolist():
        assert (WORK/member.filename).resolve().is_relative_to(WORK.resolve()), 'Caminho inválido no ZIP.'
    archive.extractall(WORK)
del uploaded
DATA=WORK/'data'
manifest=json.loads((DATA/'manifest.json').read_text())
assert manifest['experiment']=='mergedataset_cv3' and manifest['n_splits']==3
assert manifest['selected_cases']==90
print('Bloco | selecionados | positivos | negativos | completos | positivos completos')
for fold in (1,2,3):
    plan=manifest['folds'][str(fold)]
    print(fold,len(plan['test_case_ids']),plan['selected_test_labels']['Yes'],plan['selected_test_labels']['No'],
          len(plan['usable_test_case_ids']),plan['usable_test_labels']['Yes'])
print('Cada caso será testado uma vez; 12 casos maiores ficam identificados como excluídos.')
''')
    md('''
## 3. Fixar o protocolo antes dos resultados

Quatro épocas e limiar 0,5 são usados nas três rodadas. Não selecione épocas ou limiar pelo bloco de teste. As quatro ordens de B/L/R/M aumentam apenas a apresentação dos blocos de treino; o teste usa uma vista original. As temperaturas originais são preservadas, sem novo ajuste. Balancear positivos entre blocos não torna as classes igualmente frequentes no treino.

Recomenda-se usar uma pasta nova no Drive para persistir resultados e os três checkpoints. Caso mantenha `/content`, baixe os relatórios e preserve os pesos desejados antes de a sessão terminar.
''')
    code('''
EPOCHS=4
SEED=42
FREEZE_ENCODER=False
FOLDS_TO_RUN=[1,2,3]
OUTPUT=Path('/content/laya_cv3_results')
# Opcional: persistir os resultados e os três modelos no Drive.
# from google.colab import drive
# drive.mount('/content/drive')
# OUTPUT=Path('/content/drive/MyDrive/laya_cv3_results')
OUTPUT.mkdir(parents=True,exist_ok=True)
assert FOLDS_TO_RUN and len(set(FOLDS_TO_RUN))==len(FOLDS_TO_RUN)
assert set(FOLDS_TO_RUN)<= {1,2,3}
def fold_command(fold):
    command=[sys.executable,str(WORK/'train_laya_cv3.py'),'--data-dir',str(DATA),
             '--out',str(OUTPUT),'--fold',str(fold),'--epochs',str(EPOCHS),'--seed',str(SEED)]
    if FREEZE_ENCODER: command.append('--freeze-encoder')
    return command
''')
    md('## 4. Auditar contexto e pré-processamento\nUsa o tokenizer da base original, sem carregar os pesos do encoder. Os IDs utilizáveis devem corresponder aos fixados no manifesto. A auditoria não treina nem gera escores do teste.')
    code('''
for fold in FOLDS_TO_RUN:
    print('AUDITORIA DA RODADA',fold,flush=True)
    subprocess.run(fold_command(fold)+['--audit-only'],check=True)
''')
    md('''
## 5. Executar os três treinamentos e avaliações

Cada chamada é um processo separado: a base original é carregada para aquele fold. O terceiro bloco só é pontuado após o treinamento. Não use os resultados mostrados para alterar os parâmetros entre rodadas. Os logs exibem época/passo/perda e as métricas de treino e teste.

Se a sessão for interrompida, uma rodada completa na pasta persistente pode ser reutilizada com `--skip-completed`. Uma rodada incompleta começa novamente da base; não há retomada exata do otimizador. Os pesos finais ficam em `fold_N/checkpoint`.
''')
    code('''
for fold in FOLDS_TO_RUN:
    print('TREINO E TESTE DA RODADA',fold,flush=True)
    subprocess.run(fold_command(fold)+['--skip-completed'],check=True)
environment=subprocess.run([sys.executable,'-m','pip','freeze'],capture_output=True,text=True,check=True).stdout
(OUTPUT/'environment.txt').write_text(environment)
''')
    md('''
## 6. Consolidar as previsões out-of-fold

Requer as três rodadas completas. Confere os IDs, a configuração comum e que cada caso tem exatamente uma linha de teste. A cobertura principal esperada é 78/90. Mostra métricas agregadas e média/desvio-padrão entre folds; o desvio entre três folds não é um intervalo de confiança. A AUC OOF reúne escores de três modelos e não substitui a média das AUCs por fold.
''')
    code('''
subprocess.run([sys.executable,str(WORK/'train_laya_cv3.py'),'--data-dir',str(DATA),
                '--out',str(OUTPUT),'--aggregate'],check=True)
result=json.loads((OUTPUT/'cross_validation_results.json').read_text())
print(json.dumps({'OOF':result['metrics'],'OOF_ROC_AUC':result['roc']['auc'],
                  'media_e_desvio':result['fold_mean_std']},indent=2))
''')
    md('## 7. Baixar os relatórios\nO ZIP de relatórios exclui os três grandes arquivos de pesos. Para preservar os modelos, copie ou exporte separadamente as pastas `fold_N/checkpoint`, ou mantenha OUTPUT no Drive.')
    code('''
archive_path=Path('/content/laya_cv3_relatorios.zip')
with zipfile.ZipFile(archive_path,'w',zipfile.ZIP_DEFLATED) as archive:
    for path in OUTPUT.rglob('*'):
        if path.is_file() and 'checkpoint' not in path.relative_to(OUTPUT).parts:
            archive.write(path,path.relative_to(OUTPUT))
    archive.write(DATA/'manifest.json','dataset_manifest.json')
    archive.write(DATA/'blocos_cv3.csv','blocos_cv3.csv')
files.download(str(archive_path))
''')
    for index,item in enumerate(cells):
        item['id']=f'cv3-{index:02d}'
        if item['cell_type']=='code': compile(''.join(item['source']),f'cv3_cell_{index}','exec')
    notebook={'nbformat':4,'nbformat_minor':5,'cells':cells,'metadata':{'accelerator':'GPU',
        'colab':{'name':'laya_validacao_cruzada_3fold_colab.ipynb','provenance':[]},
        'kernelspec':{'name':'python3','display_name':'Python 3'},'language_info':{'name':'python'}}}
    target=OUT/'laya_validacao_cruzada_3fold_colab.ipynb'
    target.write_text(json.dumps(notebook,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
    package=OUT/'laya_cv3_colab.zip'
    with zipfile.ZipFile(package,'w',zipfile.ZIP_DEFLATED) as archive:
        for name in ('manifest.json','context_profile.json','questions.json','project_questions.json','SOURCE_NOTICES.txt','blocos_cv3.csv'):
            archive.write(DATA/name,'data/'+name)
        for fold in (1,2,3):
            for name in ('train.jsonl','train_original.jsonl','test.jsonl','fold_manifest.json'):
                relative=f'fold_{fold}/{name}'; archive.write(DATA/relative,'data/'+relative)
        for name in ('train_laya_cv3.py','train_laya_colab.py','evaluate_laya_synthetic.py'):
            archive.write(ROOT/'scripts'/name,name)
        archive.write(ROOT/'docs/laya-validacao-cruzada.md','LEIA-ME.md')
    print(target); print(package,package.stat().st_size)


if __name__=='__main__': main()
