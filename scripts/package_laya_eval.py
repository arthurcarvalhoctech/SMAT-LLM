"""Package only the local trained checkpoint and files required for evaluation."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs/laya-compartilhar-01a1c185'


def sha256(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def main():
    fixed = [
        'docker-compose.laya-eval.yml', 'docker/Dockerfile.laya-eval',
        'scripts/evaluate_laya_synthetic.py', 'scripts/evaluate_laya_mergedataset.py',
        'scripts/evaluate_laya_all90.py',
        'laya_training_data/mergedataset_full_colab/all.jsonl',
        'laya_training_data/mergedataset_full_colab/cases.json',
        'laya_training_data/mergedataset_full_colab/manifest.json',
        'dataset-sintetico/laya_global_eval.jsonl',
    ]
    checkpoint = 'laya_checkpoints/laya_semantic_global/'
    fixed += [checkpoint + name for name in (
        'model.safetensors', 'rl_agent_config.json', 'questions.json',
        'encoder/config.json', 'context_audit.json', 'manifest.json',
        'scenario_evaluation.json', 'laya_source_revision.txt',
    )]
    fixed += [p.relative_to(ROOT).as_posix() for p in sorted((ROOT / checkpoint / 'tokenizer').glob('*')) if p.is_file()]
    files = [(name, ROOT / name) for name in fixed]
    files.append(('LEIA-ME.md', ROOT / 'docs/laya-reproduzir-docker.md'))
    if any(not path.is_file() for _, path in files):
        raise FileNotFoundError('Missing required evaluation input')
    if not any(name.endswith('/tokenizer/tokenizer.json') for name, _ in files):
        raise ValueError('Tokenizer missing')
    manifest = {name: {'bytes': path.stat().st_size, 'sha256': sha256(path)} for name, path in files}
    # Explicit allowlist: no .env, .git, credentials, cached predictions or unrelated project files.
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / 'laya_avaliacao_docker.zip'
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=1, allowZip64=True) as archive:
        for name, path in files:
            archive.write(path, arcname=name)
        archive.writestr('SHA256SUMS.json', json.dumps(manifest, indent=2, ensure_ascii=False) + '\n')
        archive.writestr('mergedataset-full/resultados/', '')
        archive.writestr('dataset-sintetico/resultados/', '')
    with zipfile.ZipFile(target) as archive:
        broken = archive.testzip()
        if broken:
            raise ValueError(f'Archive integrity failed: {broken}')
        names = archive.namelist()
        if any('.env' in name.split('/') or '.git' in name.split('/') for name in names):
            raise ValueError('Unexpected private configuration in package')
        if 'mergedataset-full/resultados/laya_semantic_global_eval.json' in names:
            raise ValueError('Package must not reuse the original predictions')
    digest = sha256(target)
    target.with_suffix('.zip.sha256').write_text(f'{digest}  {target.name}\n', encoding='ascii')
    (OUT / 'package_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'path': str(target), 'files': len(files), 'bytes': target.stat().st_size,
                      'sha256': digest, 'crc_checked': True}, indent=2), flush=True)


if __name__ == '__main__':
    main()
