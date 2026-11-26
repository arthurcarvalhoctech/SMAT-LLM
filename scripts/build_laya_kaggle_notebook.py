"""Adapt the existing Laya notebook to Kaggle's input/working directories."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

KAGGLE_INPUT_CELL = '''
from pathlib import Path
import json, shutil, zipfile
INPUT_ROOT = Path('/kaggle/input')
WORK = Path('/kaggle/working/laya_smat')
WORK.mkdir(parents=True, exist_ok=True)
# Kaggle can expose an uploaded ZIP either unpacked or as an archive.
packages = sorted({p.parent.parent for p in INPUT_ROOT.rglob('manifest.json')
                   if p.parent.name == 'data'
                   and (p.parent / 'train.jsonl').is_file()
                   and (p.parent.parent / 'train_laya_colab.py').is_file()})
if packages:
    if len(packages) != 1:
        raise ValueError(f'Mais de um pacote Laya anexado: {packages}. Mantenha apenas um.')
    source = packages[0]
    shutil.copytree(source / 'data', WORK / 'data', dirs_exist_ok=True)
    shutil.copy2(source / 'train_laya_colab.py', WORK / 'train_laya_colab.py')
else:
    archives = sorted(INPUT_ROOT.rglob('laya_mergedataset_full_colab.zip'))
    if len(archives) != 1:
        raise FileNotFoundError('Em Add Input/Upload, anexe laya_mergedataset_full_colab.zip. '
                                f'Pacotes ZIP encontrados: {archives}')
    with zipfile.ZipFile(archives[0]) as z:
        for member in z.infolist():
            target = (WORK / member.filename).resolve()
            if not target.is_relative_to(WORK.resolve()):
                raise ValueError('Caminho inválido no ZIP.')
        z.extractall(WORK)
DATA = WORK / 'data'
manifest = json.loads((DATA / 'manifest.json').read_text())
print('Dados copiados para:', DATA)
print(json.dumps(manifest, indent=2, ensure_ascii=False))
'''


def build():
    source = ROOT / "notebooks/laya_semantic_interference_colab.ipynb"
    notebook = copy.deepcopy(json.loads(source.read_text(encoding="utf-8")))
    replaced_input = replaced_export = False
    for item in notebook["cells"]:
        value = "".join(item["source"])
        if item["cell_type"] == "markdown":
            value = value.replace("(Google Colab)", "(Kaggle)")
            value = value.replace(
                "No Colab: **Ambiente de execução → Alterar tipo → GPU**. Envie o arquivo `laya_mergedataset_full_colab.zip` na seção 2. A internet é necessária para instalar o Laya e baixar os pesos. Nenhuma API paga é usada.",
                "No Kaggle: importe este notebook; em **Settings → Accelerator**, escolha uma GPU disponível; ative **Internet**. Em **Add Input / Upload**, anexe `laya_mergedataset_full_colab.zip` como dados privados. A seção 2 localiza o pacote automaticamente. Esta versão usa **uma GPU**, mesmo que a sessão disponibilize duas T4. Nenhuma API paga é usada.")
            if value.startswith("## 2."):
                value += "\nAnexe o ZIP no painel **Input**, antes de executar esta célula. O carregador aceita o ZIP intacto ou o conteúdo descompactado pelo Kaggle. Copia os dados para `/kaggle/working`, onde as anotações podem ser editadas."
            if value.startswith("## 6."):
                value += "\nOs arquivos são gravados em `/kaggle/working`. Use **Save Version** e preserve os arquivos de saída para manter o resultado após o fim da sessão; salvar apenas o código do notebook não garante preservar os pesos."
            if value.startswith("## 9."):
                value += "\nBaixe pelo link exibido ou pelo painel de arquivos/Output: `/kaggle/working/laya_smat_checkpoint.zip`."
        else:
            if "from google.colab import files" in value:
                value = KAGGLE_INPUT_CELL.strip()
                replaced_input = True
            value = value.replace("configurações do Colab", "configurações do Kaggle")
            if "MODE = 'scenario'" in value:
                value = value.split("# Opcional: persistir OUTPUT", 1)[0].rstrip()
            value = value.replace("/content/", "/kaggle/working/")
            if "files.download(str(archive))" in value:
                value = value.replace("files.download(str(archive))",
                    "from IPython.display import FileLink, display\ndisplay(FileLink(str(archive)))\nprint('Arquivo de saída:', archive)")
                replaced_export = True
        item["source"] = value.strip().splitlines(keepends=True)
    if not replaced_input or not replaced_export:
        raise RuntimeError("The source notebook changed; review Kaggle adaptation points")
    notebook["metadata"].pop("colab", None)
    notebook["metadata"]["kaggle"] = {
        "accelerator": "nvidiaTeslaT4", "isGpuEnabled": True, "isInternetEnabled": True,
        "language": "python", "sourceType": "notebook"}
    target = ROOT / "notebooks/laya_semantic_interference_kaggle.ipynb"
    target.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(target)
    return target


if __name__ == "__main__":
    build()
