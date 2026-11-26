"""Freeze a stratified 45/45 split before augmentation, without using predictions.

Project+merge groups and exact B/L/R/M duplicates stay together. Case length
does not influence selection. The Colab package contains training cases only.
"""
import argparse
from collections import Counter, defaultdict
import copy
import csv
import hashlib
import json
from pathlib import Path
import random

ROOT = Path(__file__).resolve().parents[1]
BASE_MODEL = 'convaiinnovations/laya-multilingual'
BASE_REVISION = '1720e3e3357cfe1e281542e223f8273b0890ca34'


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def leakage_groups(cases):
    parent = {case['id']: case['id'] for case in cases}
    def find(key):
        while parent[key] != key:
            parent[key] = parent[parent[key]]
            key = parent[key]
        return key
    def union(a, b):
        parent[find(a)] = find(b)
    merges, duplicates = {}, {}
    for case in cases:
        key = (case['project'].rstrip('/').lower(), case['commit'].lower())
        fingerprint = digest([(case['versions'][branch]['code'].strip(), case['versions'][branch]['fields'])
                              for branch in ('base', 'left', 'right', 'merge')])
        for registry, group_key in ((merges, key), (duplicates, fingerprint)):
            if group_key in registry:
                union(case['id'], registry[group_key])
            else:
                registry[group_key] = case['id']
    components = defaultdict(list)
    for case in cases:
        components[find(case['id'])].append(case)
    return sorted((sorted(values, key=lambda c: c['id']) for values in components.values()),
                  key=lambda values: tuple(c['id'] for c in values))


def split_half(cases, seed=42):
    if len(cases) != 90 or len({c['id'] for c in cases}) != 90:
        raise ValueError('This experiment requires the 90 original unique cases')
    groups = leakage_groups(cases)
    random.Random(seed).shuffle(groups)
    # Exact grouped stratification: DP depends only on group sizes and labels.
    # It never reads token counts, earlier predictions, losses or correctness.
    reachable = {(0, 0): ()}
    for index, group in enumerate(groups):
        n, positives = len(group), sum(c['label'] == 'Yes' for c in group)
        additions = {}
        for (count, yes), chosen in list(reachable.items()):
            target = (count + n, yes + positives)
            if target[0] <= 45 and target not in reachable and target not in additions:
                additions[target] = chosen + (index,)
        reachable.update(additions)
    total_yes = sum(c['label'] == 'Yes' for c in cases)
    candidates = [key for key in reachable if key[0] == 45 and 0 < key[1] < total_yes]
    if not candidates:
        raise ValueError('An exact grouped 45/45 split with both classes is not possible')
    # 17 positives cannot be halved exactly; prefer 9 train / 8 holdout.
    target = min(candidates, key=lambda key: (abs(key[1] - total_yes/2), -key[1]))
    chosen = set(reachable[target])
    assignment, component_ids = {}, {}
    for index, group in enumerate(groups):
        component_id = digest(sorted(c['id'] for c in group))[:20]
        for case in group:
            assignment[case['id']] = 'train' if index in chosen else 'test'
            component_ids[case['id']] = component_id
    return assignment, component_ids


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def write_rows(path, rows):
    path.write_text(''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows), encoding='utf-8')


def prepare(data_dir, out, seed=42):
    cases = json.loads((data_dir / 'cases.json').read_text(encoding='utf-8'))
    original_rows = [json.loads(line) for line in (data_dir / 'all.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
    assignments, components = split_half(cases, seed)
    assignment_id = digest({'seed': seed, 'assignments': assignments, 'leakage_groups': components})
    by_id = {case['id']: case for case in cases}
    rows = []
    for source in original_rows:
        case_id = source['_meta']['case_id']
        split = assignments[case_id]
        if split == 'test' and source['_meta']['variant'] != 0:
            continue
        row = copy.deepcopy(source)
        row['_meta'].update(split=split, experiment_id=assignment_id, leakage_group=components[case_id],
                            **{'class': by_id[case_id]['class'], 'method': by_id[case_id]['declaration']})
        if split == 'test':
            row['_meta']['id'] = case_id
        # Retain the original real scenario label; no new criterion targets.
        if set(row['gold']) != {'semantic_interference'}:
            raise ValueError('This split is for scenario-only supervision')
        rows.append(row)
    train = [r for r in rows if r['_meta']['split'] == 'train']
    test = [r for r in rows if r['_meta']['split'] == 'test']
    train_ids = sorted({r['_meta']['case_id'] for r in train})
    test_ids = sorted({r['_meta']['case_id'] for r in test})
    if len(train_ids) != 45 or len(test_ids) != 45 or len(train) != 180 or len(test) != 45 or set(train_ids) & set(test_ids):
        raise ValueError('Unexpected split size or overlap')
    out.mkdir(parents=True, exist_ok=True)
    write_rows(out / 'train.jsonl', train)
    write_rows(out / 'train_original.jsonl', [r for r in train if r['_meta']['variant'] == 0])
    write_rows(out / 'holdout.jsonl', test)
    questions = json.loads((data_dir / 'questions.json').read_text(encoding='utf-8'))
    for name in ('questions.json', 'project_questions.json', 'SOURCE_NOTICES.txt'):
        (out / name).write_bytes((data_dir / name).read_bytes())
    write_json(out / 'annotations.json', {})
    write_json(out / 'train_cases.json', [c for c in cases if assignments[c['id']] == 'train'])
    write_json(out / 'holdout_cases.json', [c for c in cases if assignments[c['id']] == 'test'])
    source_manifest = json.loads((data_dir / 'manifest.json').read_text(encoding='utf-8'))
    labels = {split: dict(Counter(c['label'] for c in cases if assignments[c['id']] == split)) for split in ('train', 'test')}
    manifest = {'experiment': 'mergedataset_45_45', 'experiment_id': assignment_id, 'seed': seed,
        'source_revision': source_manifest['source_revision'], 'base_model': BASE_MODEL, 'base_revision': BASE_REVISION,
        'selected_train_cases': 45, 'reserved_test_cases': 45, 'training_presentations': 180,
        'labels_by_split': labels, 'train_case_ids': train_ids,
        'train_group_ids': sorted({r['_meta']['group_id'] for r in train}),
        'train_leakage_groups': sorted({r['_meta']['leakage_group'] for r in train}),
        'data_sha256': {name: hashlib.sha256((out / name).read_bytes()).hexdigest()
                        for name in ('train.jsonl', 'train_original.jsonl', 'holdout.jsonl')},
        'question_sha256': digest(questions['semantic_interference']),
        'threshold': 0.5, 'threshold_policy': 'Fixed before training; no fitting on the reserved 45 cases.',
        'context_policy': 'Split ignores length. Audit all four training views; exclude an entire oversized case and report the actual training count. Never replace it with a holdout case or label individual windows.',
        'validation_policy': 'Train-only run with fixed epoch budget. No held-out labels, calibration, threshold search or early stopping in the training notebook.',
        'note': '45 selected training cases, not a promise that all fit the encoder. Four presentation orders preserve real B/L/R/M, not 180 independent cases. Test is held out from this new fine-tune, but this corpus has already been examined in previous experiments. Only semantic_interference is supervised.'}
    write_json(out / 'manifest.json', manifest)
    write_json(out / 'split_manifest.json', {'experiment_id': assignment_id, 'assignments': assignments,
        'leakage_groups': components, 'holdout_case_ids': test_ids, 'group_count': len(set(components.values()))})
    with (out / 'divisao_45_45.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['id', 'particao', 'rotulo', 'projeto', 'merge', 'classe', 'metodo', 'grupo'])
        for case in cases:
            writer.writerow([case['id'], 'Treino' if assignments[case['id']] == 'train' else 'Teste reservado',
                case['label'], case['project'], case['commit'], case['class'], case['declaration'], components[case['id']]])
    print(json.dumps({'experiment_id': assignment_id, 'selected_train_cases': 45, 'reserved_test_cases': 45,
                      'training_presentations': len(train), 'labels_by_split': labels}, indent=2), flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'laya_training_data/mergedataset_full_colab')
    parser.add_argument('--out', type=Path, default=ROOT / 'laya_training_data/mergedataset_45_45')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args()
    prepare(args.data_dir, args.out, args.seed)


if __name__ == '__main__':
    main()
