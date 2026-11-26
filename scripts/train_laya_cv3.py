"""One fresh-base CV fold, or aggregate three completed out-of-fold reports."""
import argparse
from collections import Counter
import gc
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import random
import statistics
import time

try:
    from scripts.train_laya_colab import read_rows, audit_rows
    from scripts.evaluate_laya_synthetic import binary_metrics, roc_curve, run_evaluation, write_outputs, sha256_file
except ModuleNotFoundError:
    from train_laya_colab import read_rows, audit_rows
    from evaluate_laya_synthetic import binary_metrics, roc_curve, run_evaluation, write_outputs, sha256_file

BASE = 'convaiinnovations/laya-multilingual'
BASE_REV = '1720e3e3357cfe1e281542e223f8273b0890ca34'


def read_fold(data, fold):
    manifest = json.loads((data / 'manifest.json').read_text(encoding='utf-8'))
    if manifest['experiment'] != 'mergedataset_cv3' or manifest['n_splits'] != 3:
        raise ValueError('Not the frozen three-fold dataset')
    if (manifest['base_model'], manifest['base_revision']) != (BASE, BASE_REV):
        raise ValueError('Original base revision differs')
    plan = manifest['folds'][str(fold)]
    folder = data / f'fold_{fold}'
    for name, expected in plan['file_sha256'].items():
        if sha256_file(folder/name) != expected:
            raise ValueError('A frozen fold file has changed: ' + name)
    train, original, test = [read_rows(folder/name) for name in ('train.jsonl','train_original.jsonl','test.jsonl')]
    if len(original) != 60 or len(train) != 240 or len(test) != 30:
        raise ValueError('Expected 60 train cases with four views and 30 original test cases')
    ids = lambda rows: {r['_meta']['case_id'] for r in rows}
    groups = lambda rows: {r['_meta']['leakage_group'] for r in rows}
    questions = json.loads((data/'questions.json').read_text(encoding='utf-8'))
    question_digest = hashlib.sha256(json.dumps(questions['semantic_interference'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    if question_digest != manifest['question_sha256']:
        raise ValueError('The frozen global question has changed')
    if ids(train) != set(plan['train_case_ids']) or ids(test) != set(plan['test_case_ids']):
        raise ValueError('Fold IDs differ')
    if ids(train)&ids(test) or groups(train)&groups(test):
        raise ValueError('Train/test group leakage')
    if set(Counter(r['_meta']['case_id'] for r in train).values()) != {4}:
        raise ValueError('Every train case needs exactly four presentation views')
    for rows, role in ((train,'train'), (original,'train'), (test,'test')):
        for row in rows:
            meta = row['_meta']
            if meta['experiment_id'] != manifest['experiment_id'] or meta['split'] != role:
                raise ValueError('Experiment/role mismatch')
            if (meta['cv_block'] == fold) != (role == 'test'):
                raise ValueError('Test block was included in training')
            if set(row['gold']) != {'semantic_interference'}:
                raise ValueError('Only genuine global Yes/No labels may be supervised')
            if row['questions']['semantic_interference'] != questions['semantic_interference']:
                raise ValueError('Train and test must ask exactly the same frozen question')
    return manifest, plan, train, original, test


def recipe(manifest, epochs, seed, freeze_encoder):
    return {'base_model':BASE, 'base_revision':BASE_REV, 'epochs':epochs, 'seed':seed,
        'max_len':manifest['max_len'], 'head_max_len':manifest['head_max_len'],
        'micro_batch':1,'grad_accum':8,'encoder_lr':1e-5,'head_lr':1e-4,'loss':'rlcd',
        'freeze_encoder':freeze_encoder,'threshold':.5,'calibration':'Original base temperatures retained; no new fitting',
        'selection':'Fixed final epoch; no selection or threshold fitting on the outer test block'}


def score_originals(agent, rows, questions, manifest):
    usable = set(manifest['usable_case_ids'])
    selected = [r for r in rows if r['_meta']['case_id'] in usable]
    actual = run_evaluation(agent, selected, questions, manifest['max_len'], manifest['head_max_len'])
    if any(r['status'] != 'ok' or r.get('usage',{}).get('state_tokens_dropped',0) for r in actual):
        raise ValueError('Unexpected inference truncation')
    by_id = {r['id']:r for r in actual}
    result = []
    for row in rows:
        meta = row['_meta']; cid = meta['case_id']
        prediction = by_id.get(cid, {'id':cid,'class':meta['class'],'method':meta['method'],
            'gold':meta['label']=='Yes','status':'context_excluded','probability':None,
            'reason':'Whole case excluded by the fixed pre-split context audit; no windows or inference.'})
        result.append({**prediction, 'prediction':prediction['probability'] >= .5 if prediction['status']=='ok' else None,
                       'cv_block':meta['cv_block']})
    return result


def train_fold(data, output, fold, epochs, seed, freeze_encoder, audit_only=False, skip_completed=False):
    manifest, plan, train, original, test = read_fold(data, fold)
    settings = recipe(manifest, epochs, seed, freeze_encoder)
    dest = output / f'fold_{fold}'
    result_path = dest/'evaluation.json'
    if skip_completed and result_path.is_file():
        saved = json.loads(result_path.read_text(encoding='utf-8'))
        if (saved.get('experiment_id') != manifest['experiment_id'] or saved.get('recipe') != settings or
                saved.get('fold_file_sha256') != plan['file_sha256'] or saved.get('fold') != fold):
            raise ValueError('Completed output belongs to another configuration; use another output folder')
        if not saved.get('fold_complete'):
            raise ValueError('Existing output is incomplete')
        if sha256_file(dest/'checkpoint/model.safetensors') != saved['model_sha256']:
            raise ValueError('Existing model weights differ from the completed fold report')
        print(f'Fold {fold} already complete with the same recipe; reused without retraining.',flush=True)
        return saved
    import numpy as np
    import torch
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer
    from laya.agent import _fix_tokenizer_config
    from laya.train import TrainConfig,load_checkpoint,items_from_rows,train_model,save_checkpoint,optimizer_updates
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed)
    dest.mkdir(parents=True,exist_ok=True)
    base_dir = Path(snapshot_download(BASE, revision=BASE_REV))
    _fix_tokenizer_config(str(base_dir))
    base_tokenizer_sha256 = sha256_file(base_dir/'tokenizer/tokenizer.json')
    tok = AutoTokenizer.from_pretrained(base_dir/'tokenizer')
    usable = set(manifest['usable_case_ids'])
    kept, audit = audit_rows(train,tok,manifest['max_len'],manifest['head_max_len'])
    checked_test, test_audit = audit_rows(test,tok,manifest['max_len'],manifest['head_max_len'])
    if (set(audit['rejected_case_ids']) != set(plan['train_case_ids'])-set(plan['usable_train_case_ids']) or
            set(test_audit['rejected_case_ids']) != set(plan['test_case_ids'])-set(plan['usable_test_case_ids'])):
        raise ValueError('Context eligibility changed; do not change the measured cohort during CV')
    items, skipped = items_from_rows(tok,kept,manifest['max_len'],manifest['head_max_len'])
    if skipped or len(items)!=len(kept):
        raise ValueError('Unexpected canonical preprocessing skips: '+str(skipped))
    if ({r['_meta']['case_id'] for r in kept} != set(plan['usable_train_case_ids']) or
            {r['_meta']['case_id'] for r in checked_test} != set(plan['usable_test_case_ids'])):
        raise ValueError('Eligible IDs differ from the frozen fold')
    summary = {'fold':fold,'selected_train_cases':60,'selected_test_cases':30,
        'effective_train_cases':len(plan['usable_train_case_ids']),
        'effective_test_cases':len(plan['usable_test_case_ids']),
        'train_labels':plan['usable_train_labels'],'test_labels':plan['usable_test_labels'],
        'base_tokenizer_sha256':base_tokenizer_sha256,
        'preflight_tokenizer_sha256':manifest['tokenizer_sha256'],
        'training_presentations':len(kept),'canonical_skipped':skipped,
        'optimizer_updates':optimizer_updates(len(items),1,8,epochs)}
    (dest/'context_audit.json').write_text(json.dumps({'summary':summary,'train':audit,'test':test_audit},indent=2))
    print(json.dumps(summary,indent=2),flush=True)
    if audit_only: return summary
    if not torch.cuda.is_available(): raise RuntimeError('Enable a Colab GPU before training')
    model,tok,cfg = load_checkpoint(str(base_dir))
    capacity = model.encoder.config.max_position_embeddings
    if manifest['max_len'] > capacity: raise ValueError('Context exceeds the original encoder capacity')
    device=torch.device('cuda'); model.to(device)
    cfg=dict(cfg,max_len=manifest['max_len'],head_max_len=manifest['head_max_len'],
             gradient_checkpointing=True,max_tokens_per_batch=manifest['max_len'])
    config=TrainConfig(epochs=epochs,micro_batch=1,grad_accum=8,encoder_lr=1e-5,head_lr=1e-4,
        loss='rlcd',max_len=manifest['max_len'],head_max_len=manifest['head_max_len'],
        amp=True,gradient_checkpointing=True,freeze_encoder=freeze_encoder,seed=seed,
        log_every=10,calib_frac=0,calib_max=0)
    print(f'Fold {fold}: fresh original base loaded. Outer test is not used by the optimizer.',flush=True)
    start=time.perf_counter()
    history=train_model(model,tok,items,config,device,manifest['max_len'],manifest['head_max_len'])
    cfg['fine_tuned']=True
    cfg['training']={'experiment':'mergedataset_cv3','experiment_id':manifest['experiment_id'],
        'fold':fold,'recipe':settings,'selected_real_cases':60,'effective_real_cases':summary['effective_train_cases'],
        'supervised_questions':{'semantic_interference':len(items)},
        'note':'Fresh base for this fold. Four train views; fixed final epoch. Outer test not used for gradient updates, calibration or parameter selection.'}
    checkpoint=dest/'checkpoint'; save_checkpoint(model,tok,cfg,str(checkpoint))
    for name in ('questions.json','project_questions.json','manifest.json'):
        (checkpoint/name).write_bytes((data/name).read_bytes())
    training_seconds=time.perf_counter()-start
    del model,items; gc.collect(); torch.cuda.empty_cache()
    import laya
    agent=laya.Agent(str(checkpoint),device='cuda')
    questions=json.loads((data/'questions.json').read_text(encoding='utf-8'))
    q={'semantic_interference':questions['semantic_interference']}
    train_predictions=score_originals(agent,original,q,manifest)
    test_predictions=score_originals(agent,test,q,manifest)
    report={'experiment_id':manifest['experiment_id'],'fold':fold,'fold_complete':True,'recipe':settings,
        'summary':summary,'history':history,'training_seconds':training_seconds,'threshold':.5,
        'fold_file_sha256':plan['file_sha256'],'model_sha256':sha256_file(checkpoint/'model.safetensors'),
        'train_metrics':binary_metrics(train_predictions,.5),'train_predictions':train_predictions,
        'metrics':binary_metrics(test_predictions,.5),'roc':roc_curve(test_predictions),
        'predictions':[{**r,'fold':fold} for r in test_predictions],
        'environment':{p:importlib.metadata.version(p) for p in ('laya','torch','transformers')},
        'note':'Train metrics are resubstitution diagnostics, not held-out estimates. Test metrics use only this outer block; no tuning on it. Context exclusions count in coverage.'}
    write_outputs(result_path,report,extra_fields=('fold','cv_block'))
    del agent; gc.collect(); torch.cuda.empty_cache()
    print(json.dumps({'fold':fold,'train_metrics':report['train_metrics'],'test_metrics':report['metrics'],'test_roc_auc':report['roc']['auc']},indent=2),flush=True)
    return report


def aggregate(data,output):
    manifest=json.loads((data/'manifest.json').read_text(encoding='utf-8'))
    reports=[]; predictions=[]; seen=set(); settings=None; environment=None
    for fold in range(1,4):
        _,plan,_,_,test=read_fold(data,fold)
        report=json.loads((output/f'fold_{fold}/evaluation.json').read_text(encoding='utf-8'))
        if report.get('experiment_id')!=manifest['experiment_id'] or report.get('fold')!=fold or not report.get('fold_complete'):
            raise ValueError('Missing or mismatched completed fold')
        if report.get('fold_file_sha256')!=plan['file_sha256']:
            raise ValueError('Fold report refers to other inputs')
        if settings is None: settings=report['recipe']; environment=report['environment']
        if settings!=report['recipe'] or environment!=report['environment']:
            raise ValueError('All folds must use the same recipe and software environment')
        expected={r['_meta']['case_id']:r for r in test}
        actual=report['predictions']
        if len(actual)!=30 or {r['id'] for r in actual}!=set(expected) or seen&set(expected):
            raise ValueError('Each original case must have exactly one OOF prediction row')
        for row in actual:
            cid=row['id']
            if row['gold']!=(expected[cid]['_meta']['label']=='Yes') or row.get('fold')!=fold:
                raise ValueError('OOF label/fold mismatch')
            if (row['status']=='ok')!=(cid in plan['usable_test_case_ids']):
                raise ValueError('OOF coverage differs from the frozen context cohort')
            if row['status']=='ok' and (row.get('usage',{}).get('truncated') or row.get('usage',{}).get('state_tokens_dropped',0)):
                raise ValueError('A truncated state was included in OOF results')
        if report.get('threshold')!=.5 or report['recipe'].get('threshold')!=.5:
            raise ValueError('The outer test threshold must remain fixed at .5')
        recalculated=binary_metrics(actual,.5)
        for name,value in recalculated.items():
            measured=report['metrics'].get(name)
            if (value is None and measured is not None) or (value is not None and (measured is None or not math.isclose(value,measured,rel_tol=1e-9,abs_tol=1e-12))):
                raise ValueError('Fold metrics do not match the recorded predictions')
        if not math.isclose(roc_curve(actual)['auc'],report['roc']['auc'],rel_tol=1e-9):
            raise ValueError('Fold AUC does not match the recorded predictions')
        seen.update(expected); predictions.extend(actual); reports.append(report)
    if len(seen)!=90: raise ValueError('Incomplete OOF coverage')
    distributions={}
    for name in ('precision','recall','f1','accuracy','brier','roc_auc'):
        values=[r['roc']['auc'] if name=='roc_auc' else r['metrics'][name] for r in reports]
        distributions[name]={'values':values,'mean':statistics.mean(values),
                              'sample_std':statistics.stdev(values),
                              'note':'Variation across three folds, not a confidence interval'}
    result={'experiment_id':manifest['experiment_id'],'all_folds_complete':True,'n_splits':3,
        'selected_cases':90,'threshold':.5,'recipe':settings,'environment':environment,
        'metrics':binary_metrics(predictions,.5),'roc':roc_curve(predictions),'predictions':predictions,
        'fold_mean_std':distributions,
        'folds':[{'fold':r['fold'],'summary':r['summary'],'metrics':r['metrics'],
                  'roc_auc':r['roc']['auc'],'train_metrics':r['train_metrics'],'history':r['history'],
                  'model_sha256':r['model_sha256']} for r in reports],
        'note':'OOF: each eligible case was scored by a model trained without its entire merge/duplicate group. 90 selected cases, fixed context exclusions remain visible. Pooled OOF metrics and mean fold metrics are different summaries; pooled ROC mixes scores from three models, not one deployed model. No external blind test and no guarantee of performance improvement. Outer test blocks must not select epochs, thresholds or hyperparameters.'}
    write_outputs(output/'cross_validation_results.json',result,extra_fields=('fold','cv_block'))
    print(json.dumps({'oof_metrics':result['metrics'],'oof_roc_auc':result['roc']['auc'],
                     'fold_mean_std':distributions},indent=2),flush=True)
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-dir',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--fold',type=int,choices=(1,2,3))
    parser.add_argument('--epochs',type=int,default=4)
    parser.add_argument('--seed',type=int,default=42)
    parser.add_argument('--freeze-encoder',action='store_true')
    parser.add_argument('--audit-only',action='store_true')
    parser.add_argument('--skip-completed',action='store_true')
    parser.add_argument('--aggregate',action='store_true')
    args=parser.parse_args()
    if args.aggregate:
        aggregate(args.data_dir,args.out)
    elif args.fold:
        train_fold(args.data_dir,args.out,args.fold,args.epochs,args.seed,args.freeze_encoder,args.audit_only,args.skip_completed)
    else: parser.error('Choose --fold or --aggregate')


if __name__=='__main__': main()
