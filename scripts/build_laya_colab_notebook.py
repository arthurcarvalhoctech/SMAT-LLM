"""Build the portable Colab notebook and its data ZIP from real sources."""
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "laya_training_data/mergedataset_full_colab"
OUT = ROOT / "notebooks"
LAYA_REVISION = "b8a0f0991d95a953411f2e16f91bddc2ffdaf79a"


def cell(kind, source):
    result = {"cell_type": kind, "metadata": {}, "source": source.strip().splitlines(keepends=True)}
    if kind == "code":
        result.update(execution_count=None, outputs=[])
    return result


def main():
    OUT.mkdir(exist_ok=True)
    cells = []
    def md(source): cells.append(cell("markdown", source))
    def code(source): cells.append(cell("code", source))
    md("""
# Laya + SMAT: interferência semântica em casos reais (Google Colab)

**360 apresentações de 90 casos reais; nenhum caso sintético.** Quatro ordens das seções B/L/R/M preservam integralmente o código e o rótulo. A diversidade é de apresentação, não de comportamentos independentes.

O CSV original tem 95 linhas: 74 No, 17 Yes e 4 inconclusivas. São usados 73 No + 17 Yes. A linha 75 (IndexRequest, c1d4478) não tem fontes no artefato público; as 4 inconclusivas não viram negativos.

**Limite dos rótulos:** `Locally Observable Interference` supervisiona apenas a pergunta auxiliar `semantic_interference`. As sete perguntas de `criteria.py` são preservadas, mas não recebem respostas inventadas. Este primeiro treino não é um treinamento supervisionado de C1/C2/C3, testemunha, ramo ou confiança. Para isso, preencha `annotations.json` com respostas revisadas e evidências, conforme a seção 4. Respostas dessas sete perguntas continuam sendo hipóteses sem validação específica.

Adaptação do [notebook oficial de RLCD](https://github.com/NandhaKishorM/laya/blob/main/notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb) para **uma GPU** e dados `{state, questions, gold}`, usando as mesmas primitivas canônicas. Referências: [README](https://github.com/NandhaKishorM/laya/blob/main/README.md) e [fine-tuning](https://github.com/NandhaKishorM/laya/blob/main/docs/finetune.md).

No Colab: **Ambiente de execução → Alterar tipo → GPU**. Envie o arquivo `laya_mergedataset_full_colab.zip` na seção 2. A internet é necessária para instalar o Laya e baixar os pesos. Nenhuma API paga é usada.
""")
    md("## 1. Instalação e GPU\nO código do Laya fica fixado em uma revisão. As versões resolvidas são exportadas com o modelo. Execute esta célula antes de importar transformers.")
    code(f"""
import os, sys, subprocess
os.environ["USE_TF"] = "0"
os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
LAYA_REVISION = "{LAYA_REVISION}"
subprocess.run([sys.executable, "-m", "pip", "install", "-q",
                f"laya @ git+https://github.com/NandhaKishorM/laya.git@{{LAYA_REVISION}}",
                "transformers>=4.48,<6", "scipy", "accelerate"], check=True)
import torch
assert torch.cuda.is_available(), "Ative uma GPU nas configurações do Colab."
print(torch.cuda.get_device_name(0))
subprocess.run(["nvidia-smi"], check=True)
""")
    md("## 2. Carregar o pacote\nO ZIP inclui os JSONL, a origem de cada caso, as perguntas, o treinador e os avisos originais dos fontes. Não é necessário clonar o projeto ou baixar JARs.")
    code("""
from pathlib import Path
import json, zipfile
from google.colab import files
WORK = Path('/content/laya_smat')
WORK.mkdir(parents=True, exist_ok=True)
uploads = files.upload()
archives = [name for name in uploads if name.endswith('.zip')]
assert len(archives) == 1, 'Envie apenas laya_mergedataset_full_colab.zip.'
with zipfile.ZipFile(archives[0]) as z:
    for member in z.infolist():
        target = (WORK / member.filename).resolve()
        assert target.is_relative_to(WORK.resolve()), 'Caminho inválido no ZIP.'
    z.extractall(WORK)
DATA = WORK / 'data'
manifest = json.loads((DATA / 'manifest.json').read_text())
print(json.dumps(manifest, indent=2, ensure_ascii=False))
""")
    md("## 3. Conferir origens, partições e perguntas\nTreino: 57 casos × 4 = 228 exemplos. Validação: 16 casos originais. Teste: 17 casos originais. Os 360 exemplos estão em `all.jsonl`, incluindo as vistas reservadas de validação/teste. O split agrupa projeto + merge, inclusive classes e métodos diferentes do mesmo merge. A validação calibra temperaturas; o teste fica reservado para avaliação.")
    code("""
def read_jsonl(path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
splits = {s: read_jsonl(DATA / f'{s}.jsonl') for s in ('train', 'validation', 'test')}
groups = {s: {r['_meta']['group_id'] for r in rows} for s, rows in splits.items()}
assert groups['train'].isdisjoint(groups['validation'] | groups['test'])
assert groups['validation'].isdisjoint(groups['test'])
questions = json.loads((DATA / 'questions.json').read_text())
project_questions = json.loads((DATA / 'project_questions.json').read_text())
from collections import Counter
print('Casos por split:', {s: len({r['_meta']['case_id'] for r in rows}) for s, rows in splits.items()})
print('Rótulos por split:', {s: dict(Counter(r['_meta']['label'] for r in rows)) for s, rows in splits.items()})
print('Perguntas do projeto:', list(project_questions))
print('Gold disponível:', list(splits['train'][0]['gold']))
print(splits['train'][0]['state'][:3500])
""")
    md("""
## 4. Anotações específicas, opcionais

Com apenas o CSV, deixe `MODE = 'scenario'`. O treino adapta o encoder e a decisão global; as sete perguntas específicas permanecem sem supervisão. Não substitua automaticamente o detector atual por esse modelo.

Para treinar C1/C2/C3 de fato, edite `DATA / 'annotations.json'`: cada ID contém `answers` e `evidence`. Adicione somente respostas sustentadas por revisão/execução. Use os IDs e opções exatos de `project_questions.json`; booleanos para noul, string para choice, inteiro 0–4 para score. **Não use o Yes/No da planilha como resposta dos critérios nem invente uma confiança a partir dele.** Uma anotação é propagada às quatro vistas do mesmo caso.

Exemplo de estrutura (substitua os valores por anotações reais): `{"ID_DO_CASO": {"answers": {"criterion_2_parent_change_loss": true}, "evidence": "teste, entrada e valores observados para o mesmo elemento em B/L/R/M"}}`. Rótulos ausentes são mascarados. Selecione `MODE = 'criteria'` apenas depois de revisar positivos e negativos de cada critério; o treinador verifica essa cobertura no treino.
""")
    code("""
MODE = 'scenario'  # 'criteria' exige anotações reais por critério
BASE_MODEL = 'convaiinnovations/laya-multilingual'
EPOCHS = 12
MAX_LEN = 8192
HEAD_MAX_LEN = 512
MICRO_BATCH = 1
GRAD_ACCUM = 8
SEED = 42
FREEZE_ENCODER = False
OUTPUT = Path('/content/laya_semantic_global' if MODE == 'scenario' else '/content/laya_semantic_criteria')
OUTPUT.mkdir(exist_ok=True)
# Opcional: persistir OUTPUT no Google Drive para resistir a encerramentos da sessão.
# from google.colab import drive
# drive.mount('/content/drive')
# OUTPUT = Path('/content/drive/MyDrive/laya_smat_checkpoint')
""")
    md("## 5. Auditoria de contexto antes do treino\nNão truncamos B/L/R/M. Se o estado completo não couber, todas as vistas daquele caso são excluídas e listadas em `context_audit.json`. Confira o número efetivo de casos/positivos. O orçamento inclui espaço para a pergunta. Reduzir `MAX_LEN` pode excluir mais exemplos; não use os casos excluídos para reivindicar desempenho.")
    code("""
command = [sys.executable, str(WORK / 'train_laya_colab.py'), '--data-dir', str(DATA),
           '--out', str(OUTPUT), '--base', BASE_MODEL, '--epochs', str(EPOCHS),
           '--max-len', str(MAX_LEN), '--head-max-len', str(HEAD_MAX_LEN),
           '--micro-batch', str(MICRO_BATCH), '--grad-accum', str(GRAD_ACCUM), '--seed', str(SEED)]
assert MODE in ('scenario', 'criteria')
if FREEZE_ENCODER: command.append('--freeze-encoder')
if MODE == 'criteria': command.append('--require-criterion-gold')
subprocess.run(command + ['--audit-only'], check=True)
audit = json.loads((OUTPUT / 'context_audit.json').read_text())
print({s: {k:v for k,v in a.items() if k != 'state_token_lengths'} for s,a in audit.items()})
""")
    md("## 6. Treinar com RLCD\nUma GPU, mixed precision, gradient checkpointing e acumulação de gradiente. O treinador chama `items_from_rows`, `train_model` (RLCD), `calibration_records`, `fit_temperature_map` e `save_checkpoint` do Laya oficial. A calibração usa exclusivamente a validação. Não há split aleatório de decisões que misture perguntas/vistas do mesmo caso. `checkpoint_latest` salva os pesos ao final de cada época; não contém estado completo do otimizador para retomar exatamente o mesmo treinamento.\n\nSe ocorrer falta de memória, reinicie o runtime e reduza `MAX_LEN` ou use `FREEZE_ENCODER = True`, repetindo a auditoria. Congelar o encoder muda o experimento. Não há garantia de ganho com esta amostra pequena.")
    code("""
subprocess.run(command, check=True)
environment = subprocess.run([sys.executable, '-m', 'pip', 'freeze'], check=True, capture_output=True, text=True).stdout
(OUTPUT / 'environment.txt').write_text(environment)
(OUTPUT / 'laya_source_revision.txt').write_text(LAYA_REVISION)
report = json.loads((OUTPUT / 'training_report.json').read_text())
print(json.dumps({'before': report['before'], 'after': report['after'], 'calibration': report['calibration']}, indent=2))
""")
    md("## 7. Avaliação global por caso e calibração do limiar\nCompara a base e o checkpoint no mesmo teste com limiar 0,5. Mede precisão, recall, F1, falsos positivos, Brier e truncamento. Um limiar adicional é escolhido somente na validação, depois avaliado no teste. A amostra de validação é pequena e também ajustou temperaturas; trate o resultado como exploratório. Métricas por C1/C2/C3 não existem sem seus rótulos revisados.")
    code("""
import gc, math, time
import laya
global_q = {'semantic_interference': questions['semantic_interference']}
def evaluate_predictions(model_path):
    agent = laya.Agent(str(model_path), device='cuda')
    predictions = {}
    for split in ('validation', 'test'):
        rejected = set(audit[split]['rejected_case_ids'])
        predictions[split] = []
        for row in splits[split]:
            if row['_meta']['case_id'] in rejected: continue
            out = agent.predict(row['state'], global_q,
                                max_len=MAX_LEN, head_max_len=HEAD_MAX_LEN)
            if out.get('usage', {}).get('truncated'):
                raise RuntimeError('Truncamento inesperado; revise o orçamento de contexto.')
            predictions[split].append({'id': row['_meta']['case_id'],
                'gold': row['_meta']['label'] == 'Yes',
                'p': float(out['answers']['semantic_interference']['noul'])})
    del agent
    gc.collect()
    torch.cuda.empty_cache()
    return predictions
def metrics(rows, threshold):
    tp = sum(r['gold'] and r['p'] >= threshold for r in rows)
    fp = sum(not r['gold'] and r['p'] >= threshold for r in rows)
    fn = sum(r['gold'] and r['p'] < threshold for r in rows)
    tn = len(rows) - tp - fp - fn
    precision = tp / (tp+fp) if tp+fp else 0.
    recall = tp / (tp+fn) if tp+fn else 0.
    return dict(n=len(rows), threshold=threshold, tp=tp, fp=fp, tn=tn, fn=fn,
                precision=precision, recall=recall,
                f1=2*precision*recall/(precision+recall) if precision+recall else 0.,
                brier=sum((r['p']-r['gold'])**2 for r in rows)/len(rows))
baseline = evaluate_predictions(BASE_MODEL)
finetuned = evaluate_predictions(OUTPUT)
grid = [i/100 for i in range(5, 96)]
threshold = max(grid, key=lambda t: (metrics(finetuned['validation'], t)['f1'], -abs(t-.5)))
global_report = {'base_test_0.5': metrics(baseline['test'], .5),
                'finetuned_test_0.5': metrics(finetuned['test'], .5),
                'finetuned_test_validation_threshold': metrics(finetuned['test'], threshold),
                'validation_selected_threshold': threshold,
                'predictions': {'base': baseline, 'finetuned': finetuned}}
(OUTPUT / 'scenario_evaluation.json').write_text(json.dumps(global_report, indent=2))
print(json.dumps({k:v for k,v in global_report.items() if k != 'predictions'}, indent=2))
""")
    md("## 8. Carregar as perguntas do projeto\nAs perguntas abaixo são uma cópia exata de `build_questions(witness_candidates=...)`. No modo scenario, suas respostas não foram supervisionadas: não apresente os resultados como critérios aprendidos. A calibração do treino ajusta temperaturas por tipo de pergunta e também pode mudar suas probabilidades. O checkpoint contém o detector global auxiliar, mas o fluxo atual do SMAT não consulta essa pergunta; a integração de produção exige uma alteração separada e validação.")
    code("""
agent = laya.Agent(str(OUTPUT), device='cuda')
usable = [r for r in splits['test'] if r['_meta']['case_id'] not in set(audit['test']['rejected_case_ids'])]
sample = usable[0]
print('Detector global:', agent.predict(sample['state'], global_q,
                                      max_len=MAX_LEN, head_max_len=HEAD_MAX_LEN)['answers'])
print('Perguntas específicas (sem supervisão no modo scenario):')
print(agent.predict(sample['state'], project_questions,
                    max_len=MAX_LEN, head_max_len=HEAD_MAX_LEN)['answers'])
del agent
gc.collect()
torch.cuda.empty_cache()
""")
    md("## 9. Baixar o checkpoint\nO pacote contém `rl_agent_config.json`, `model.safetensors`, `encoder/`, `tokenizer/`, perguntas, auditoria, ambiente e relatórios. Nenhum modelo é publicado em serviços externos. O ZIP de saída exclui o checkpoint intermediário duplicado.")
    code("""
archive = Path('/content/laya_smat_checkpoint.zip')
with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
    for path in OUTPUT.rglob('*'):
        if path.is_file() and 'checkpoint_latest' not in path.relative_to(OUTPUT).parts:
            z.write(path, path.relative_to(OUTPUT))
files.download(str(archive))
""")
    notebook = {"nbformat": 4, "nbformat_minor": 5, "metadata": {
        "colab": {"name": "laya_semantic_interference_colab.ipynb", "provenance": []},
        "accelerator": "GPU", "kernelspec": {"name": "python3", "display_name": "Python 3"},
        "language_info": {"name": "python"}}, "cells": cells}
    for i, item in enumerate(cells):
        item["id"] = f"smat-laya-{i:02d}"
    path = OUT / "laya_semantic_interference_colab.ipynb"
    path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    shutil.copyfile(ROOT / "scripts/train_laya_colab.py", DATA / "train_laya_colab.py")
    notices = []
    cases = json.loads((DATA / "cases.json").read_text(encoding="utf-8"))
    sources = sorted({v["source"] for c in cases for v in c["versions"].values()})
    for name in sources:
        raw = (ROOT / ".laya_smat/mergedataset_sources" / name).read_bytes()
        value = raw.decode("utf-8", errors="replace")
        match = re.search(r"(?m)^\s*package\s+[\w.]+\s*;", value)
        if match and match.start() > 0:
            notices.append(name + "\n" + value[:match.start()])
    (DATA / "SOURCE_NOTICES.txt").write_text("\n\n".join(notices), encoding="utf-8")
    package = OUT / "laya_mergedataset_full_colab.zip"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        for item in sorted(DATA.iterdir()):
            if item.is_file() and not item.name.endswith("_all_views.jsonl") and item.name != "train_laya_colab.py":
                archive.write(item, "data/" + item.name)
        archive.write(ROOT / "scripts/train_laya_colab.py", "train_laya_colab.py")
        archive.write(ROOT / "SMAT/nimrod/laya_interference/criteria.py", "criteria_snapshot.py")
        archive.write(ROOT / "docs/laya-colab-training.md", "LEIA-ME.md")
    # The trainer is maintained in scripts/, not duplicated in the dataset.
    (DATA / "train_laya_colab.py").unlink()
    print(path)
    print(package, package.stat().st_size)


if __name__ == "__main__":
    main()
