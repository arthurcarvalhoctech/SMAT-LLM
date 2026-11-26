"""Prepare three grouped folds with balanced real positive labels.

Exact whole-merge grouping precedes augmentation. Allocation uses labels and
the fixed context eligibility only, never earlier model predictions or losses.
"""
import argparse
from collections import Counter
import copy
import csv
import hashlib
import itertools
import json
from pathlib import Path
import random

try:
    from scripts.prepare_laya_45_45 import leakage_groups, digest, BASE_MODEL, BASE_REVISION
except ModuleNotFoundError:
    from prepare_laya_45_45 import leakage_groups, digest, BASE_MODEL, BASE_REVISION

ROOT = Path(__file__).resolve().parents[1]


def category(case, usable):
    return (0 if case['label'] == 'Yes' else 2) + (0 if case['id'] in usable else 1)


def allocate(cases, usable, seed=42):
    """Solve small grouped bins exactly; fill independent singleton cases last."""
    if len(cases) != 90 or len({c['id'] for c in cases}) != 90:
        raise ValueError('Expected all 90 unique real cases')
    if sum(c['label'] == 'Yes' for c in cases) != 17:
        raise ValueError('Expected the original 17 positive labels')
    groups = leakage_groups(cases)
    rng = random.Random(seed)
    rng.shuffle(groups)
    multi = sorted([g for g in groups if len(g) > 1], key=lambda g: -len(g))
    singles = {i: [] for i in range(4)}
    for group in groups:
        if len(group) == 1:
            singles[category(group[0], usable)].append(group[0])
    vectors = [tuple(Counter(category(c, usable) for c in group)[i] for i in range(4)) for group in multi]
    eligible_positive = sum(c['label'] == 'Yes' and c['id'] in usable for c in cases)
    if eligible_positive != 15:
        raise ValueError('This balanced primary protocol expects the 15 complete positive cases')
    # 17 positives -> 6/6/5, with exactly five context-eligible positives each.
    positive_targets = (6, 6, 5)
    ideal = len(usable) / 3
    possibilities = [t for t in itertools.product(range(31), repeat=3) if sum(t) == len(usable)]
    rng.shuffle(possibilities)
    possibilities.sort(key=lambda t: (max(abs(n-ideal) for n in t), sum((n-ideal)**2 for n in t)))
    solution = None
    for usable_targets in possibilities:
        remaining = [[5, positive_targets[i]-5, usable_targets[i]-5,
                      30-positive_targets[i]-(usable_targets[i]-5)] for i in range(3)]
        if any(min(budget) < 0 for budget in remaining):
            continue
        chosen, failed = [], set()
        def search(index):
            if index == len(multi):
                return True
            key = (index, tuple(tuple(v) for v in remaining))
            if key in failed:
                return False
            vector = vectors[index]
            tried = set()
            for block in range(3):
                signature = tuple(remaining[block])
                if signature in tried or any(vector[k] > remaining[block][k] for k in range(4)):
                    continue
                tried.add(signature)
                for k in range(4): remaining[block][k] -= vector[k]
                chosen.append(block)
                if search(index+1): return True
                chosen.pop()
                for k in range(4): remaining[block][k] += vector[k]
            failed.add(key)
            return False
        if search(0):
            solution = (chosen[:], remaining, usable_targets)
            break
    if solution is None:
        raise ValueError('No 30/30/30 grouped allocation with 6/6/5 positives is possible')
    chosen, remaining, usable_targets = solution
    assignments, group_ids = {}, {}
    for group, block in zip(multi, chosen):
        for case in group: assignments[case['id']] = block+1
    for cat, values in singles.items():
        offset = 0
        for block in range(3):
            count = remaining[block][cat]
            for case in values[offset:offset+count]: assignments[case['id']] = block+1
            offset += count
        if offset != len(values): raise ValueError('Singleton allocation mismatch')
    for group in groups:
        gid = digest(sorted(c['id'] for c in group))[:20]
        for case in group: group_ids[case['id']] = gid
    if len(assignments) != 90: raise ValueError('Missing assigned cases')
    return assignments, group_ids


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def jsonl(path, rows):
    path.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in rows), encoding='utf-8')


def prepare(source, out, seed=42):
    profile = json.loads((out / 'context_profile.json').read_text(encoding='utf-8'))
    payload = (source / 'all.jsonl').read_bytes()
    if hashlib.sha256(payload).hexdigest() != profile['source_data_sha256']:
        raise ValueError('Token profile and input data differ')
    rows = [json.loads(line) for line in payload.decode('utf-8').splitlines() if line.strip()]
    cases = json.loads((source / 'cases.json').read_text(encoding='utf-8'))
    lengths = profile['state_token_lengths']
    if len(rows) != 360 or {r['_meta']['id'] for r in rows} != set(lengths):
        raise ValueError('Audit all four original views of every case first')
    rejected = {r['_meta']['case_id'] for r in rows if lengths[r['_meta']['id']] + profile['head_max_len'] + profile['reserve'] > profile['max_len']}
    usable = {c['id'] for c in cases} - rejected
    assignments, group_ids = allocate(cases, usable, seed)
    experiment_id = digest({'assignments': assignments, 'groups': group_ids, 'seed': seed,
                            'context': {k: v for k, v in profile.items() if k != 'note'}})
    by_id = {c['id']: c for c in cases}
    enriched = []
    for source_row in rows:
        row = copy.deepcopy(source_row)
        meta = row['_meta']; cid = meta['case_id']
        meta.update(experiment_id=experiment_id, cv_block=assignments[cid], leakage_group=group_ids[cid],
                    context_eligible=cid in usable, **{'class': by_id[cid]['class'], 'method': by_id[cid]['declaration']})
        if meta['variant'] == 0: meta['id'] = cid
        enriched.append(row)
    source_manifest = json.loads((source / 'manifest.json').read_text(encoding='utf-8'))
    folds = {}
    for fold in range(1,4):
        folder = out / f'fold_{fold}'; folder.mkdir(parents=True, exist_ok=True)
        selected = copy.deepcopy([r for r in enriched if r['_meta']['cv_block'] != fold])
        test = copy.deepcopy([r for r in enriched if r['_meta']['cv_block'] == fold and r['_meta']['variant'] == 0])
        for row in selected: row['_meta']['split'] = 'train'
        for row in test: row['_meta']['split'] = 'test'
        train_original = [r for r in selected if r['_meta']['variant'] == 0]
        jsonl(folder / 'train.jsonl', selected)
        jsonl(folder / 'train_original.jsonl', train_original)
        jsonl(folder / 'test.jsonl', test)
        def counts(selected_rows):
            return dict(Counter(r['_meta']['label'] for r in selected_rows))
        train_groups = {r['_meta']['leakage_group'] for r in selected}
        test_groups = {r['_meta']['leakage_group'] for r in test}
        if not train_groups.isdisjoint(test_groups): raise ValueError('Leakage across a merge/duplicate group')
        folds[str(fold)] = {'fold': fold, 'train_case_ids': sorted(r['_meta']['case_id'] for r in train_original),
            'test_case_ids': sorted(r['_meta']['case_id'] for r in test),
            'usable_train_case_ids': sorted(r['_meta']['case_id'] for r in train_original if r['_meta']['context_eligible']),
            'usable_test_case_ids': sorted(r['_meta']['case_id'] for r in test if r['_meta']['context_eligible']),
            'train_groups': sorted(train_groups), 'test_groups': sorted(test_groups),
            'selected_train_labels': counts(train_original), 'selected_test_labels': counts(test),
            'usable_train_labels': counts([r for r in train_original if r['_meta']['context_eligible']]),
            'usable_test_labels': counts([r for r in test if r['_meta']['context_eligible']]),
            'file_sha256': {name: hashlib.sha256((folder / name).read_bytes()).hexdigest()
                            for name in ('train.jsonl', 'train_original.jsonl', 'test.jsonl')}}
        save(folder / 'fold_manifest.json', folds[str(fold)])
    manifest = {'experiment': 'mergedataset_cv3', 'experiment_id': experiment_id, 'n_splits': 3, 'seed': seed,
        'source_revision': source_manifest['source_revision'], 'base_model': BASE_MODEL, 'base_revision': BASE_REVISION,
        'selected_cases': 90, 'selected_labels': dict(Counter(c['label'] for c in cases)),
        'usable_case_ids': sorted(usable), 'context_excluded_case_ids': sorted(rejected),
        'usable_labels': dict(Counter(c['label'] for c in cases if c['id'] in usable)),
        'max_len': profile['max_len'], 'head_max_len': profile['head_max_len'], 'reserve': profile['reserve'],
        'tokenizer_sha256': profile['tokenizer_sha256'], 'question_sha256': digest(json.loads((source / 'questions.json').read_text(encoding='utf-8'))['semantic_interference']),
        'assignments': assignments, 'leakage_groups': group_ids, 'folds': folds,
        'threshold': 0.5, 'epochs': 4,
        'protocol': 'Three fresh original-base fine-tunes. Fixed 4 epochs, threshold .5, no temperature fitting or model selection on fold test. Four presentation orders only for train, one original view for test. Primary OOF evaluates each eligible case exactly once. Context exclusions fixed before allocation; no window labels or window-max primary metrics.',
        'allocation': 'Seeded grouped integer allocation: exactly 30 original cases per block with positive counts 6/6/5; exactly five context-eligible positive cases per test block. Remaining eligible size differences reflect intact merge groups. No previous predictions or losses used.',
        'limitations': 'Internal exploratory cross-validation on a corpus already examined. This is not a new external blind test; using outer test results to choose hyperparameters would require a separate/nested evaluation. Balancing positive counts across blocks does not balance positive versus negative sampling during training.'}
    save(out / 'manifest.json', manifest)
    for name in ('questions.json', 'project_questions.json', 'SOURCE_NOTICES.txt'):
        (out / name).write_bytes((source / name).read_bytes())
    with (out / 'blocos_cv3.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle); writer.writerow(['id','bloco','rotulo','cabe_no_contexto','projeto','merge','classe','metodo','grupo'])
        for case in cases:
            writer.writerow([case['id'],assignments[case['id']],case['label'],case['id'] in usable,
                case['project'],case['commit'],case['class'],case['declaration'],group_ids[case['id']]])
    print(json.dumps({'selected_cases':90,'usable_cases':len(usable),'excluded_cases':len(rejected),
        'blocks':{k:{'selected_test':v['selected_test_labels'],'usable_test':v['usable_test_labels'],
                    'usable_train':v['usable_train_labels']} for k,v in folds.items()}},indent=2),flush=True)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=ROOT/'laya_training_data/mergedataset_full_colab')
    parser.add_argument('--out', type=Path, default=ROOT/'laya_training_data/mergedataset_cv3')
    parser.add_argument('--seed', type=int, default=42)
    args = parser.parse_args(); prepare(args.source,args.out,args.seed)


if __name__ == '__main__': main()
