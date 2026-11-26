"""CV invariants: no leakage, honest augmentation, balanced positives and OOF."""
from collections import Counter, defaultdict
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
import zipfile

from scripts.prepare_laya_cv3 import allocate
from scripts.prepare_laya_45_45 import leakage_groups
from scripts.train_laya_cv3 import read_fold, aggregate, recipe
from scripts.evaluate_laya_synthetic import binary_metrics,roc_curve

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'laya_training_data/mergedataset_cv3'


class CrossValidationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest=json.loads((DATA/'manifest.json').read_text(encoding='utf-8'))
        cls.cases=json.loads((ROOT/'laya_training_data/mergedataset_full_colab/cases.json').read_text(encoding='utf-8'))

    def test_equal_blocks_near_equal_total_positives_exact_usable_positives(self):
        total=Counter(); primary=Counter(); seen=set()
        for fold in (1,2,3):
            _,plan,train,original,test=read_fold(DATA,fold)
            self.assertEqual(len(train),240)
            self.assertEqual(len(original),60)
            self.assertEqual(len(test),30)
            labels=Counter(r['_meta']['label'] for r in test)
            total[fold]=labels['Yes']
            usable=[r for r in test if r['_meta']['context_eligible']]
            primary[fold]=sum(r['_meta']['label']=='Yes' for r in usable)
            self.assertEqual(plan['usable_train_labels']['Yes'],10)
            self.assertFalse(seen&{r['_meta']['case_id'] for r in test})
            seen.update(r['_meta']['case_id'] for r in test)
        self.assertEqual(total,{1:6,2:6,3:5})
        self.assertEqual(primary,{1:5,2:5,3:5})
        self.assertEqual(len(seen),90)
        self.assertEqual(len(self.manifest['usable_case_ids']),78)

    def test_group_and_duplicate_closure_prevents_leakage(self):
        mapping=self.manifest['assignments']
        for group in leakage_groups(self.cases):
            self.assertEqual(len({mapping[c['id']] for c in group}),1)
        for fold in (1,2,3):
            _,_,train,_,test=read_fold(DATA,fold)
            for field in ('case_id','group_id','leakage_group'):
                self.assertTrue({r['_meta'][field] for r in train}.isdisjoint({r['_meta'][field] for r in test}))

    def test_reproducible_assignment_without_previous_predictions(self):
        mapping,groups=allocate(self.cases,set(self.manifest['usable_case_ids']),42)
        self.assertEqual(mapping,self.manifest['assignments'])
        self.assertEqual(groups,self.manifest['leakage_groups'])
        reordered,_=allocate(list(reversed(self.cases)),set(self.manifest['usable_case_ids']),42)
        self.assertEqual(mapping,reordered)

    def test_all_original_code_and_gold_preserved(self):
        source={(r['_meta']['case_id'],r['_meta']['variant']):r for r in
            (json.loads(s) for s in (ROOT/'laya_training_data/mergedataset_full_colab/all.jsonl').read_text(encoding='utf-8').splitlines())}
        for fold in (1,2,3):
            _,_,train,_,test=read_fold(DATA,fold)
            for row in train+test:
                meta=row['_meta']; original=source[meta['case_id'],meta['variant']]
                self.assertEqual(row['state'],original['state'])
                self.assertEqual(row['gold'],original['gold'])
                self.assertEqual(meta['source_sha256'],original['_meta']['source_sha256'])
            self.assertEqual({r['_meta']['variant'] for r in test},{0})
            self.assertEqual(set(Counter(r['_meta']['case_id'] for r in train).values()),{4})

    def test_notebook_and_zip_complete_clean_and_syntactically_valid(self):
        nb=json.loads((ROOT/'notebooks/laya_validacao_cruzada_3fold_colab.ipynb').read_text(encoding='utf-8'))
        for i,cell in enumerate(nb['cells']):
            if cell['cell_type']=='code':
                compile(''.join(cell['source']),f'cv3:{i}','exec')
                self.assertEqual(cell['outputs'],[])
                self.assertIsNone(cell['execution_count'])
        with zipfile.ZipFile(ROOT/'notebooks/laya_cv3_colab.zip') as archive:
            self.assertIsNone(archive.testzip())
            self.assertFalse(any('model.safetensors' in n or '.env' in n.split('/') for n in archive.namelist()))
            for script in ('train_laya_cv3.py','train_laya_colab.py','evaluate_laya_synthetic.py'):
                self.assertEqual(archive.read(script),(ROOT/'scripts'/script).read_bytes())
            for fold in (1,2,3):
                for name in ('train.jsonl','train_original.jsonl','test.jsonl'):
                    relative=f'fold_{fold}/{name}'
                    self.assertEqual(archive.read('data/'+relative),(DATA/relative).read_bytes())

    def fake_completed_reports(self,out):
        """Perfect artificial scores only to test aggregation, never real outputs."""
        for fold in (1,2,3):
            manifest,plan,_,_,rows=read_fold(DATA,fold)
            predictions=[]
            for row in rows:
                m=row['_meta']; ok=m['context_eligible']; gold=m['label']=='Yes'
                predictions.append({'id':m['case_id'],'class':m['class'],'method':m['method'],
                    'fold':fold,'cv_block':fold,'gold':gold,'status':'ok' if ok else 'context_excluded',
                    'probability':(.9 if gold else .1) if ok else None,'prediction':gold if ok else None,
                    'usage':{'truncated':0,'state_tokens_dropped':0}})
            report={'experiment_id':manifest['experiment_id'],'fold':fold,'fold_complete':True,
                'recipe':recipe(manifest,4,42,False),'threshold':.5,'environment':{'fixture':True},
                'fold_file_sha256':plan['file_sha256'],'predictions':predictions,
                'metrics':binary_metrics(predictions,.5),'roc':roc_curve(predictions),
                'train_metrics':{},'history':[0.1],'summary':{},'model_sha256':str(fold)*64}
            folder=out/f'fold_{fold}';folder.mkdir()
            (folder/'evaluation.json').write_text(json.dumps(report),encoding='utf-8')

    def test_oof_scored_once_and_confusions_reconcile(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);self.fake_completed_reports(out)
            with contextlib.redirect_stdout(io.StringIO()): result=aggregate(DATA,out)
            self.assertEqual(len(result['predictions']),90)
            self.assertEqual(result['metrics']['n'],78)
            self.assertEqual(result['metrics']['tp'],15)
            self.assertEqual(result['metrics']['tn'],63)
            self.assertEqual(result['metrics']['fp']+result['metrics']['fn'],0)
            self.assertEqual(result['metrics']['f1'],1.)
            self.assertEqual(result['fold_mean_std']['f1']['sample_std'],0.)
            self.assertEqual(result['metrics']['coverage'],78/90)

    def test_aggregate_rejects_mixed_hyperparameters(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp);self.fake_completed_reports(out)
            path=out/'fold_2/evaluation.json'; report=json.loads(path.read_text())
            report['recipe']['epochs']=12;path.write_text(json.dumps(report))
            with self.assertRaisesRegex(ValueError,'same recipe'):
                aggregate(DATA,out)

    def test_aggregate_rejects_misreported_metrics_and_changed_coverage(self):
        for defect in ('metrics','coverage'):
            with self.subTest(defect=defect),tempfile.TemporaryDirectory() as tmp:
                out=Path(tmp);self.fake_completed_reports(out)
                path=out/'fold_1/evaluation.json'; report=json.loads(path.read_text())
                if defect=='metrics': report['metrics']['tp']=999
                else: report['predictions'][0]['status']='context_excluded' if report['predictions'][0]['status']=='ok' else 'ok'
                path.write_text(json.dumps(report))
                with self.assertRaises(ValueError): aggregate(DATA,out)


if __name__=='__main__': unittest.main()
