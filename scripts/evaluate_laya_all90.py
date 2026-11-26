"""Complete the real-corpus evaluation using Laya's official long-text scan.

Full-state predictions and windowed predictions remain distinguishable. Window
max scores are exploratory: reading every token in some window does not ensure
that distant B/L/R/M evidence was compared together.
"""
import argparse
from collections import Counter
import importlib.metadata
import json
import math
import os
from pathlib import Path
import time

try:
    from scripts.evaluate_laya_mergedataset import prepare_rows, partition_results, ROOT
    from scripts.evaluate_laya_synthetic import binary_metrics, roc_curve, sha256_file, write_outputs
except ModuleNotFoundError:
    from evaluate_laya_mergedataset import prepare_rows, partition_results, ROOT
    from evaluate_laya_synthetic import binary_metrics, roc_curve, sha256_file, write_outputs


def validated_cache(report, rows, identity):
    for key, value in identity.items():
        if report.get(key) != value:
            raise ValueError(f"Cached report differs in {key}; refusing to reuse predictions")
    expected = {row['_meta']['id']: row['_meta'] for row in rows}
    if len(report['predictions']) != len(expected) or {p['id'] for p in report['predictions']} != set(expected):
        raise ValueError('Cached report must contain exactly the same original cases')
    cached = {}
    for prediction in report['predictions']:
        meta = expected[prediction['id']]
        if (prediction['gold'] != (meta['label'] == 'Yes') or
                any(prediction[key] != meta[key] for key in ('split', 'exposure', 'class')) or
                prediction['method'] != meta['method']):
            raise ValueError('Cached case metadata differs')
        if prediction['status'] == 'ok':
            score = prediction['probability']
            if not isinstance(score, (float, int)) or not math.isfinite(score) or not 0 <= score <= 1:
                raise ValueError('Invalid cached score')
            if prediction.get('usage', {}).get('truncated'):
                raise ValueError('Cannot reuse a truncated prediction')
            cached[prediction['id']] = {
                **prediction, 'inference_method': prediction.get('inference_method', 'full_state'),
                'window_count': prediction.get('window_count', 1), 'reused_prediction': True}
    return cached


def long_prediction(agent, row):
    meta = row['_meta']
    tokens = len(agent.tok.encode(row['state'], add_special_tokens=False))
    print(f"[scan] {meta['id']}: {tokens} source tokens; scanning all windows", flush=True)
    start = time.perf_counter()
    # max_len/head_max_len come from the checkpoint cfg; this API does not
    # accept those keyword arguments. Batch size 1 bounds CPU memory usage.
    out = agent.predict_long(row['state'], row['questions'], batch_size=1)
    usage = out.get('usage', {})
    answer = out['answers']['semantic_interference']
    score = float(answer['noul'])
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError('Invalid long-text score')
    if usage.get('truncated') or usage.get('state_tokens_dropped', 0):
        raise ValueError(f"Unexpected truncation in long-text scan: {meta['id']}")
    count = usage.get('windows', 0)
    if count < 1:
        raise ValueError('Long-text scan evaluated no windows')
    if count > 1 and not answer.get('window'):
        raise ValueError('Missing deciding-window attribution')
    result = {'id': meta['id'], 'class': meta['class'], 'method': meta['method'],
              'gold': meta['label'] == 'Yes', 'probability': score, 'status': 'ok',
              'latency_ms': 1000 * (time.perf_counter() - start), 'usage': usage,
              'split': meta['split'], 'exposure': meta['exposure'], 'source_tokens': tokens,
              'inference_method': 'sliding_windows' if count > 1 else 'full_state',
              'window_count': count, 'deciding_window': answer.get('window'),
              'reused_prediction': False}
    print(f"[done] {meta['id']}: score={score:.6f}; windows={count}; no truncation", flush=True)
    return result


def describe_scores(metrics, predictions):
    if any(p.get('inference_method') == 'sliding_windows' for p in predictions if p['status'] == 'ok'):
        # A max across windows is not a calibrated whole-case probability.
        metrics['brier'] = None
        metrics['brier_note'] = 'Not reported for mixed whole-state probabilities and uncalibrated window-max scores.'
    return metrics


def build_report(base, rows, by_id, threshold):
    predictions = []
    for row in rows:
        meta = row['_meta']
        prediction = by_id.get(meta['id'], {'id': meta['id'], 'class': meta['class'],
            'method': meta['method'], 'gold': meta['label'] == 'Yes', 'split': meta['split'],
            'exposure': meta['exposure'], 'status': 'pending', 'probability': None})
        prediction = {**prediction, 'prediction': prediction['probability'] >= threshold
                      if prediction['status'] == 'ok' else None}
        predictions.append(prediction)
    partitions = partition_results(predictions, threshold)
    for split, part in partitions.items():
        selected = [p for p in predictions if p['split'] == split]
        describe_scores(part['metrics'], selected)
        part['methods'] = dict(Counter(p.get('inference_method', 'pending') for p in selected))
    by_method = {}
    for method in ('full_state', 'sliding_windows'):
        selected = [p for p in predictions if p.get('inference_method') == method]
        by_method[method] = {'metrics': describe_scores(binary_metrics(selected, threshold), selected),
                             'roc': roc_curve(selected)}
    return {**base, 'predictions': predictions,
            'metrics': describe_scores(binary_metrics(predictions, threshold), predictions),
            'roc': roc_curve(predictions), 'partitions': partitions, 'by_inference_method': by_method,
            'complete': all(p['status'] == 'ok' for p in predictions)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', type=Path, default=ROOT / 'laya_checkpoints/laya_semantic_global')
    parser.add_argument('--data-dir', type=Path, default=ROOT / 'laya_training_data/mergedataset_full_colab')
    parser.add_argument('--reuse-report', type=Path, default=ROOT / 'mergedataset-full/resultados/laya_semantic_global_eval.json')
    parser.add_argument('--out', type=Path, default=ROOT / 'mergedataset-full/resultados/laya_semantic_global_all90.json')
    parser.add_argument('--device', choices=['cpu', 'cuda'], default='cpu')
    args = parser.parse_args()
    rows, questions, cfg, threshold, threshold_source = prepare_rows(args.data_dir, args.model)
    identity = {'model_sha256': sha256_file(args.model / 'model.safetensors'),
                'data_sha256': sha256_file(args.data_dir / 'all.jsonl'),
                'question': 'semantic_interference', 'threshold': threshold,
                'max_len': cfg['max_len'], 'head_max_len': cfg['head_max_len']}
    cache_report = json.loads(args.reuse_report.read_text(encoding='utf-8'))
    cached = validated_cache(cache_report, rows, identity)
    import laya
    import torch
    environment = {p: importlib.metadata.version(p) for p in ('laya', 'torch', 'transformers')}
    if environment != cache_report['environment']:
        raise ValueError('Runtime differs from cached inference environment')
    torch.set_num_threads(max(1, min(4, os.cpu_count() or 1)))
    agent = laya.Agent(str(args.model), device=args.device)
    base = {**identity, 'cases': len(rows), 'labels': dict(Counter(r['_meta']['label'] for r in rows)),
            'threshold_source': threshold_source, 'environment': environment,
            'reused_report_sha256': sha256_file(args.reuse_report), 'reused_cases': len(cached),
            'long_text_protocol': {'api': 'laya.Agent.predict_long', 'aggregate': 'auto (noul=max)',
                'window': 'checkpoint default, capped to actual question budget',
                'stride': 'default: 50% overlap', 'batch_size': 1,
                'source': 'https://github.com/NandhaKishorM/laya/blob/b8a0f0991d95a953411f2e16f91bddc2ffdaf79a/laya/agent.py'},
            'note': 'Exploratory hybrid evaluation. Whole-state predictions are reused only after model/data/config/runtime checks. Previously oversized inputs use the official overlapping-window scan; every source token is covered by a window, but distant B/L/R/M evidence may never occur together. Window maxima are not calibrated whole-case probabilities and can increase false positives as window count grows. The threshold remains fixed; no training, calibration or threshold search. Pooled metrics include training data; only the original test split was reserved from weight fitting and calibration. This is not execution of the production .env or a benchmark of separately supervised C1/C2/C3.'}
    def save():
        report = build_report(base, rows, cached, threshold)
        write_outputs(args.out, report, extra_fields=('split', 'exposure', 'source_tokens',
                      'inference_method', 'window_count', 'reused_prediction'))
        return report
    save()
    for row in rows:
        case_id = row['_meta']['id']
        if case_id in cached:
            continue
        # Only the trained question is scored, as in the 78 cached predictions.
        cached[case_id] = long_prediction(agent, {**row, 'questions': questions})
        save()
    report = save()
    if not report['complete'] or len(report['predictions']) != 90:
        raise SystemExit('Evaluation incomplete; inspect saved report')
    print(json.dumps({'complete': report['complete'], 'pooled_diagnostic': report['metrics'],
        'partitions': {s: p['metrics'] for s, p in report['partitions'].items()},
        'methods': {m: p['metrics'] for m, p in report['by_inference_method'].items()}}, indent=2), flush=True)


if __name__ == '__main__':
    main()
