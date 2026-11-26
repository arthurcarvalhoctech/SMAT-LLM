"""Create separate Colab training/holdout notebooks and non-overlapping ZIPs."""
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'laya_training_data/mergedataset_45_45'
OUT = ROOT / 'notebooks'
REV = 'b8a0f0991d95a953411f2e16f91bddc2ffdaf79a'


def cell(kind, source):
    result = {'cell_type': kind, 'metadata': {}, 'source': source.strip().splitlines(keepends=True)}
    if kind == 'code':
        result.update(execution_count=None, outputs=[])
    return result


INSTALL = f'''
import os, sys, subprocess
os.environ['USE_TF'] = '0'
os.environ['PYTORCH_CUDA_ALLOC_CONF'] = 'expandable_segments:True'
LAYA_REVISION = '{REV}'
subprocess.run([sys.executable, '-m', 'pip', 'install', '-q',
               f'laya @ git+https://github.com/NandhaKishorM/laya.git@{{LAYA_REVISION}}',
               'transformers==5.22.1', 'scipy', 'accelerate'], check=True)
import torch
print('GPU:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'não disponível')
'''

EVAL_UPLOAD_CELL = '''
from pathlib import Path
from google.colab import files
import json, zipfile
WORK = Path('/content/laya_avaliacao_45')
MODEL = WORK / 'model'
TEST = WORK / 'test'
MODEL.mkdir(parents=True, exist_ok=True)
TEST.mkdir(parents=True, exist_ok=True)
loaded = set()

def load_archive(path):
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())
        if 'model.safetensors' in names:
            target, kind = MODEL, 'model'
        elif 'data/holdout.jsonl' in names:
            target, kind = TEST, 'test'
        else:
            raise ValueError('ZIP não reconhecido: ' + str(path))
        if kind in loaded:
            print('Este tipo de pacote já foi carregado:', kind)
            return
        for member in archive.infolist():
            assert (target / member.filename).resolve().is_relative_to(target.resolve()), 'Caminho inválido.'
        archive.extractall(target)
        loaded.add(kind)
        print('Carregado:', path.name)

# Reaproveita os ZIPs enviados numa tentativa anterior, inclusive nomes (1).
for stem in ('laya_semantic_45_45_checkpoint', 'laya_45_teste_reservado'):
    candidates = set()
    for folder in (Path.cwd(), Path('/content')):
        candidates.update(path for path in folder.glob(stem + '*.zip') if path.is_file())
    if candidates:
        load_archive(max(candidates, key=lambda path: path.stat().st_mtime))

while loaded != {'model', 'test'}:
    missing = []
    if 'model' not in loaded: missing.append('laya_semantic_45_45_checkpoint.zip')
    if 'test' not in loaded: missing.append('laya_45_teste_reservado.zip')
    print('Envie somente o que falta:', ', '.join(missing))
    uploads = files.upload()
    if not uploads:
        raise ValueError('Upload cancelado. Execute novamente esta célula para continuar.')
    for name in uploads:
        load_archive(Path(name))
    del uploads
print('Checkpoint e teste reservado prontos. Continue na etapa 3.')
'''


def notebook(name, cells):
    for i, item in enumerate(cells):
        item['id'] = f'holdout45-{i:02d}'
        if item['cell_type'] == 'code':
            compile(''.join(item['source']), f'{name}:{i}', 'exec')
    obj = {'nbformat': 4, 'nbformat_minor': 5, 'cells': cells,
           'metadata': {'accelerator': 'GPU', 'colab': {'name': name, 'provenance': []},
                        'kernelspec': {'name': 'python3', 'display_name': 'Python 3'},
                        'language_info': {'name': 'python'}}}
    (OUT / name).write_text(json.dumps(obj, indent=1, ensure_ascii=False) + '\n', encoding='utf-8')


def main():
    OUT.mkdir(exist_ok=True)
    c = []
    def md(s): c.append(cell('markdown', s))
    def code(s): c.append(cell('code', s))
    md('''
# Laya: 45 casos selecionados para treino, 45 reservados

Este notebook **não carrega nem avalia os 45 casos reservados**. Começa do modelo base original, não do checkpoint anterior. São 45 casos reais selecionados (9 positivos e 36 negativos), cada um com quatro ordens das seções B/L/R/M: 180 apresentações, sem casos sintéticos.

Ative **Ambiente de execução → Alterar tipo → GPU**. Envie apenas `laya_45_treino_colab.zip`. Guarde `laya_45_teste_reservado.zip` para a avaliação posterior em outro notebook.

**Contexto:** o arquivo contém os 45 selecionados, mas casos maiores que o orçamento de 8192 tokens serão excluídos integralmente do ajuste. O número efetivo ficará explícito na seção 4. Não serão substituídos por casos do teste.

A auditoria local das quatro apresentações encontrou **39 casos completos utilizáveis (7 positivos e 32 negativos), com 156 apresentações**. O Colab repetirá a conferência com o tokenizer da base original. Seis dos 45 selecionados excederam o orçamento; o arquivo preserva esses casos e não os transforma em exemplos truncados.

Usa o formato e as primitivas do [Laya oficial](https://github.com/NandhaKishorM/laya/blob/b8a0f0991d95a953411f2e16f91bddc2ffdaf79a/laya/train.py). Somente a pergunta global `semantic_interference` tem rótulo; Yes/No não supervisiona C1/C2/C3.
''')
    md('## 1. Instalar o Laya fixado')
    code(INSTALL + "\nassert torch.cuda.is_available(), 'Ative uma GPU T4 antes de treinar.'")
    md('## 2. Enviar somente o pacote de treino')
    code('''
from pathlib import Path
from google.colab import files
import hashlib, json, zipfile
WORK = Path('/content/laya_45_45')
WORK.mkdir(parents=True, exist_ok=True)
uploads = files.upload()
assert len(uploads) == 1 and 'laya_45_treino_colab.zip' in uploads, 'Envie somente laya_45_treino_colab.zip.'
with zipfile.ZipFile('laya_45_treino_colab.zip') as archive:
    assert not any('holdout' in name or name.endswith('test.jsonl') for name in archive.namelist()), 'Pacote incorreto: contém dados reservados.'
    for member in archive.infolist():
        assert (WORK / member.filename).resolve().is_relative_to(WORK.resolve()), 'Caminho inválido.'
    archive.extractall(WORK)
DATA = WORK / 'data'
manifest = json.loads((DATA / 'manifest.json').read_text())
assert manifest['experiment'] == 'mergedataset_45_45'
assert manifest['selected_train_cases'] == manifest['reserved_test_cases'] == 45
assert hashlib.sha256((DATA / 'train.jsonl').read_bytes()).hexdigest() == manifest['data_sha256']['train.jsonl']
rows = [json.loads(line) for line in (DATA / 'train.jsonl').read_text().splitlines() if line.strip()]
assert len(rows) == 180 and len({r['_meta']['case_id'] for r in rows}) == 45
assert {r['_meta']['split'] for r in rows} == {'train'}
print('45 casos selecionados. Rótulos:', manifest['labels_by_split']['train'])
print('45 casos de teste permanecem fora deste pacote.')
''')
    md('''
## 3. Fixar a configuração antes de olhar o teste

O orçamento inicial é de **4 épocas**, reduzido em relação às 12 anteriores. Não há escolha de épocas por desempenho no teste, busca de limiar nem calibração com esses 45 reservados. Os valores abaixo não garantem ausência de overfitting. O encoder é ajustado por padrão, como no treino anterior.
''')
    code('''
BASE_MODEL = 'convaiinnovations/laya-multilingual'
BASE_REVISION = '1720e3e3357cfe1e281542e223f8273b0890ca34'
EPOCHS = 4
MAX_LEN = 8192
HEAD_MAX_LEN = 512
MICRO_BATCH = 1
GRAD_ACCUM = 8
SEED = 42
FREEZE_ENCODER = False
OUTPUT = Path('/content/laya_semantic_45_45')
# Opcional: antes da auditoria, use um diretório novo no Drive para persistir os pesos.
# from google.colab import drive
# drive.mount('/content/drive')
# OUTPUT = Path('/content/drive/MyDrive/laya_semantic_45_45')
command = [sys.executable, str(WORK / 'train_laya_45_45.py'),
           '--data-dir', str(DATA), '--out', str(OUTPUT), '--base', BASE_MODEL,
           '--base-revision', BASE_REVISION, '--train-only', '--expected-train-cases', '45',
           '--epochs', str(EPOCHS), '--max-len', str(MAX_LEN), '--head-max-len', str(HEAD_MAX_LEN),
           '--micro-batch', str(MICRO_BATCH), '--grad-accum', str(GRAD_ACCUM), '--seed', str(SEED)]
if FREEZE_ENCODER: command.append('--freeze-encoder')
''')
    md('''
## 4. Auditar quantos casos cabem no contexto

O modelo base e seu tokenizer são baixados da revisão fixada. Nenhum peso do experimento anterior é carregado. A auditoria verifica todas as quatro apresentações e registra exclusões inteiras, sem cortar código. Confira o número **efetivo** de casos; ele pode ser menor que os 45 selecionados.
''')
    code('''
subprocess.run(command + ['--audit-only'], check=True)
audit = json.loads((OUTPUT / 'context_audit.json').read_text())['train']
print('Casos selecionados:', audit['selected_real_cases'])
print('Casos que serão efetivamente treinados:', audit['effective_real_cases'])
print('Apresentações utilizadas:', audit['kept_rows'])
print('Rótulos por apresentação:', audit['labels'])
print('Excluídos por contexto:', audit['rejected_case_ids'])
assert audit['effective_real_cases'] > 0
''')
    md('''
## 5. Treinar somente com a metade selecionada

Os logs mostram época, passo e perda. `checkpoint_latest` salva os pesos a cada época, mas não permite retomada exata do otimizador. Uma perda baixa no treino não mede generalização. Os 45 reservados não serão lidos nesta etapa.
''')
    code('''
subprocess.run(command, check=True)
environment = subprocess.run([sys.executable, '-m', 'pip', 'freeze'], capture_output=True, text=True, check=True).stdout
(OUTPUT / 'environment.txt').write_text(environment)
(OUTPUT / 'laya_source_revision.txt').write_text(LAYA_REVISION)
report = json.loads((OUTPUT / 'training_report.json').read_text())
assert report['test_evaluated'] is False
assert report['base_model'] == BASE_MODEL and report['base_revision'] == BASE_REVISION
print(json.dumps({k: report[k] for k in ('selected_training_cases', 'effective_training_cases', 'history', 'test_evaluated', 'calibration')}, indent=2))
''')
    md('''
## 6. Baixar o novo checkpoint

Este arquivo é o resultado do novo treinamento. Preserve-o separado de `laya_semantic_global`. Depois de fixar os pesos, abra `laya_45_45_avaliacao_colab.ipynb` e use o pacote reservado para medir o resultado nos outros 45.
''')
    code('''
archive_path = Path('/content/laya_semantic_45_45_checkpoint.zip')
with zipfile.ZipFile(archive_path, 'w', zipfile.ZIP_DEFLATED) as archive:
    for item in OUTPUT.rglob('*'):
        if item.is_file() and 'checkpoint_latest' not in item.relative_to(OUTPUT).parts:
            archive.write(item, item.relative_to(OUTPUT))
files.download(str(archive_path))
''')
    notebook('laya_45_45_colab.ipynb', c)

    c = []
    md('''
# Avaliação posterior nos 45 casos reservados

Use somente depois de concluir o novo treino e fixar os parâmetros. Envie o novo checkpoint e `laya_45_teste_reservado.zip`. Este notebook não treina, calibra ou escolhe limiares. Esses casos foram reservados deste ajuste, mas o corpus já foi examinado em experimentos anteriores.
''')
    md('## 1. Instalar a mesma revisão do Laya')
    code(INSTALL)
    md('## 2. Carregar o checkpoint e o pacote reservado\nVocê pode enviar um ZIP por vez ou os dois juntos. A célula reaproveita os arquivos já enviados nesta sessão e solicita somente o que falta. Se o checkpoint já estiver no Colab, envie apenas `laya_45_teste_reservado.zip`.')
    code(EVAL_UPLOAD_CELL)
    md('''
## 3. Avaliar com limiar fixo 0,5

Por padrão, o relatório principal usa apenas estados completos que cabem no contexto e informa a cobertura sobre os 45. Casos longos permanecem identificados como excluídos. `LONG_CONTEXT = True` adiciona escores exploratórios por janelas, separados das métricas de estado completo; isso não garante a comparação conjunta de B/L/R/M. Não escolha essa opção depois de olhar qual produz a melhor métrica.
''')
    code('''
LONG_CONTEXT = False
DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'
RESULT = WORK / 'holdout_45_evaluation.json'
command = [sys.executable, str(TEST / 'evaluate_laya_holdout.py'), '--model', str(MODEL),
           '--data', str(TEST / 'data/holdout.jsonl'), '--out', str(RESULT), '--device', DEVICE]
if LONG_CONTEXT: command.append('--long-context')
subprocess.run(command + ['--dry-run'], check=True)
subprocess.run(command, check=True)
result = json.loads(RESULT.read_text())
print(json.dumps({k:result[k] for k in ('metrics', 'primary_full_state_metrics', 'full_state_coverage_of_45')}, indent=2))
''')
    md('## 4. Baixar o resultado por caso e a curva ROC')
    code('''
for path in (RESULT, RESULT.with_suffix('.csv'), RESULT.with_name(RESULT.stem + '_roc.csv')):
    files.download(str(path))
''')
    notebook('laya_45_45_avaliacao_colab.ipynb', c)

    with zipfile.ZipFile(OUT / 'laya_45_treino_colab.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ('train.jsonl', 'train_original.jsonl', 'train_cases.json', 'manifest.json',
                     'questions.json', 'project_questions.json', 'annotations.json', 'SOURCE_NOTICES.txt'):
            archive.write(DATA / name, 'data/' + name)
        if (DATA / 'context_preflight.json').is_file():
            archive.write(DATA / 'context_preflight.json', 'data/context_preflight.json')
        archive.write(ROOT / 'scripts/train_laya_45_45.py', 'train_laya_45_45.py')
        archive.write(ROOT / 'docs/laya-treino-45-45.md', 'LEIA-ME.md')
    with zipfile.ZipFile(OUT / 'laya_45_teste_reservado.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for name in ('holdout.jsonl', 'holdout_cases.json', 'split_manifest.json'):
            archive.write(DATA / name, 'data/' + name)
        for name in ('evaluate_laya_holdout.py', 'evaluate_laya_synthetic.py'):
            archive.write(ROOT / 'scripts' / name, name)
        archive.write(ROOT / 'docs/laya-treino-45-45.md', 'LEIA-ME.md')
    for name in ('laya_45_45_colab.ipynb', 'laya_45_treino_colab.zip',
                 'laya_45_45_avaliacao_colab.ipynb', 'laya_45_teste_reservado.zip'):
        print(OUT / name)


if __name__ == '__main__':
    main()
