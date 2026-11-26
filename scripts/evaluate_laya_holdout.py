"""Evaluate only the 45 frozen holdout cases after the new model is finalized."""
import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import time

try:
    from scripts.evaluate_laya_synthetic import load_inputs, binary_metrics, roc_curve, write_outputs, sha256_file
except ModuleNotFoundError:
    from evaluate_laya_synthetic import load_inputs, binary_metrics, roc_curve, write_outputs, sha256_file


def validate_holdout(model, data, rows):
    manifest = json.loads((model / 'manifest.json').read_text(encoding='utf-8'))
    cfg = json.loads((model / 'rl_agent_config.json').read_text(encoding='utf-8'))
    if manifest.get('experiment') != 'mergedataset_45_45' or cfg.get('training', {}).get('experiment_id') != manifest['experiment_id']:
        raise ValueError('Use the new 45/45 checkpoint, not the previous model')
    if sha256_file(data) != manifest['data_sha256']['holdout.jsonl']:
        raise ValueError('Holdout file differs from the frozen split')
    if len(rows) != 45 or len({r['_meta']['case_id'] for r in rows}) != 45:
        raise ValueError('Exactly 45 unique holdout cases are required')
    train_ids, train_groups = set(manifest['train_case_ids']), set(manifest['train_leakage_groups'])
    for row in rows:
        meta = row['_meta']
        if (meta['split'] != 'test' or meta['variant'] != 0 or meta['experiment_id'] != manifest['experiment_id'] or
                meta['case_id'] in train_ids or meta['leakage_group'] in train_groups):
            raise ValueError('Train/test overlap or a mismatched experiment')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, required=True)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cuda')
    parser.add_argument('--long-context', action='store_true', help='Exploratory window-max scores for the oversized cases')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    rows, questions, cfg, threshold, _ = load_inputs(args.model, args.data, threshold=.5)
    manifest = validate_holdout(args.model, args.data, rows)
    if args.dry_run:
        print(json.dumps({'holdout_cases': len(rows), 'labels': dict(Counter(r['_meta']['label'] for r in rows)),
                          'threshold': threshold, 'train_overlap': False}, indent=2))
        return
    import laya
    import torch
    if args.device == 'cpu':
        torch.set_num_threads(4)
    agent = laya.Agent(str(args.model), device=args.device)
    predictions = []
    for i, row in enumerate(rows, 1):
        meta = row['_meta']
        tokens = len(agent.tok.encode(row['state'], add_special_tokens=False))
        fits = tokens + int(cfg['head_max_len']) + 32 <= int(cfg['max_len'])
        result = {'id': meta['case_id'], 'class': meta['class'], 'method': meta['method'],
                  'gold': meta['label'] == 'Yes', 'source_tokens': tokens,
                  'inference_method': 'full_state' if fits else 'sliding_windows',
                  'status': 'context_excluded', 'probability': None, 'prediction': None}
        if fits or args.long_context:
            start = time.perf_counter()
            output = (agent.predict(row['state'], questions, max_len=int(cfg['max_len']), head_max_len=int(cfg['head_max_len']))
                      if fits else agent.predict_long(row['state'], questions, batch_size=1))
            usage = output.get('usage', {})
            if usage.get('truncated') or usage.get('state_tokens_dropped', 0):
                raise ValueError('Unexpected truncation; do not include a partial state in metrics')
            answer = output['answers']['semantic_interference']
            score = float(answer['noul'])
            if not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('Invalid score')
            result.update(status='ok', probability=score, prediction=score >= threshold, usage=usage,
                latency_ms=(time.perf_counter() - start)*1000, deciding_window=answer.get('window'),
                window_count=usage.get('windows', 1))
        predictions.append(result)
        print(f"[{i}/{len(rows)}] {result['id']}: {result['status']}; score={result['probability']}", flush=True)
    whole = [r for r in predictions if r['inference_method'] == 'full_state']
    metrics = binary_metrics(predictions, threshold)
    if any(r['status'] == 'ok' and r['inference_method'] == 'sliding_windows' for r in predictions):
        metrics['brier'] = None
    report = {'experiment_id': manifest['experiment_id'], 'cases': 45, 'threshold': threshold,
        'metrics': metrics, 'roc': roc_curve(predictions), 'predictions': predictions,
        'primary_full_state_metrics': binary_metrics(whole, threshold), 'primary_full_state_roc': roc_curve(whole),
        'full_state_coverage_of_45': len(whole)/45,
        'model_sha256': sha256_file(args.model / 'model.safetensors'), 'data_sha256': sha256_file(args.data),
        'note': 'Only the 45 cases reserved from this new fine-tune. Fixed threshold; no calibration or model selection here. Oversized cases remain excluded unless --long-context was explicitly chosen. Window-max scores are exploratory and may separate distant B/L/R/M evidence. The corpus was examined in earlier experiments and is not a new external blind dataset.'}
    write_outputs(args.out, report, extra_fields=('inference_method', 'source_tokens', 'window_count'))
    print(json.dumps({'metrics': metrics, 'full_state_coverage_of_45': report['full_state_coverage_of_45']}, indent=2))


if __name__ == '__main__':
    main()
