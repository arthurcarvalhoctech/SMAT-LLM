"""Check 45/45 isolation, real-case augmentation and portable Colab artifacts."""
from collections import Counter
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile
import types
import contextlib
import io

from scripts.prepare_laya_45_45 import split_half, leakage_groups
from scripts.evaluate_laya_holdout import validate_holdout
from scripts.train_laya_45_45 import audit_rows
from scripts.build_laya_45_45_notebooks import EVAL_UPLOAD_CELL

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'laya_training_data/mergedataset_45_45'


class HalfSplitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cases = json.loads((ROOT / 'laya_training_data/mergedataset_full_colab/cases.json').read_text(encoding='utf-8'))
        cls.manifest = json.loads((DATA / 'manifest.json').read_text(encoding='utf-8'))
        cls.train = [json.loads(line) for line in (DATA / 'train.jsonl').read_text(encoding='utf-8').splitlines()]
        cls.test = [json.loads(line) for line in (DATA / 'holdout.jsonl').read_text(encoding='utf-8').splitlines()]

    def test_exact_stratified_reproducible_split(self):
        assignments, groups = split_half(self.cases)
        again, _ = split_half(list(reversed(self.cases)))
        self.assertEqual(assignments, again)
        self.assertEqual(Counter(assignments.values()), {'train': 45, 'test': 45})
        self.assertEqual(Counter(c['label'] for c in self.cases if assignments[c['id']] == 'train'), {'Yes': 9, 'No': 36})
        self.assertEqual(Counter(c['label'] for c in self.cases if assignments[c['id']] == 'test'), {'Yes': 8, 'No': 37})
        for component in leakage_groups(self.cases):
            self.assertEqual(len({assignments[c['id']] for c in component}), 1)

    def test_exact_duplicate_different_merges_stays_together(self):
        cases = copy.deepcopy(self.cases)
        first, second = cases[:2]
        second['versions'] = copy.deepcopy(first['versions'])
        second['project'], second['commit'] = 'other-project', 'other-merge'
        component = next(group for group in leakage_groups(cases) if first['id'] in {c['id'] for c in group})
        self.assertIn(second['id'], {c['id'] for c in component})

    def test_no_id_merge_or_semantic_duplicate_component_overlap(self):
        for key in ('case_id', 'group_id', 'leakage_group'):
            self.assertTrue({r['_meta'][key] for r in self.train}.isdisjoint({r['_meta'][key] for r in self.test}))
        self.assertEqual(Counter(r['_meta']['case_id'] for r in self.train), {case_id: 4 for case_id in self.manifest['train_case_ids']})
        self.assertEqual({r['_meta']['variant'] for r in self.test}, {0})
        self.assertEqual(len(self.test), 45)

    def test_states_and_labels_unchanged_from_real_sources(self):
        originals = {(r['_meta']['case_id'], r['_meta']['variant']): r for r in
            (json.loads(line) for line in (ROOT / 'laya_training_data/mergedataset_full_colab/all.jsonl').read_text(encoding='utf-8').splitlines())}
        for row in self.train + self.test:
            original = originals[row['_meta']['case_id'], row['_meta']['variant']]
            self.assertEqual(row['state'], original['state'])
            self.assertEqual(row['gold'], original['gold'])
            self.assertEqual(row['_meta']['source_sha256'], original['_meta']['source_sha256'])
            self.assertEqual(set(row['gold']), {'semantic_interference'})

    def test_training_package_physically_excludes_holdout_payloads(self):
        with zipfile.ZipFile(ROOT / 'notebooks/laya_45_treino_colab.zip') as archive:
            self.assertIsNone(archive.testzip())
            self.assertFalse(any('holdout' in name or name.endswith('test.jsonl') for name in archive.namelist()))
            self.assertEqual(archive.read('data/train.jsonl'), (DATA / 'train.jsonl').read_bytes())
            self.assertEqual(archive.read('train_laya_45_45.py'), (ROOT / 'scripts/train_laya_45_45.py').read_bytes())
            cases = json.loads(archive.read('data/train_cases.json'))
            self.assertEqual({c['id'] for c in cases}, set(self.manifest['train_case_ids']))
            self.assertEqual(len(cases), 45)
        with zipfile.ZipFile(ROOT / 'notebooks/laya_45_teste_reservado.zip') as archive:
            self.assertIsNone(archive.testzip())
            self.assertNotIn('data/train.jsonl', archive.namelist())
            self.assertEqual(archive.read('data/holdout.jsonl'), (DATA / 'holdout.jsonl').read_bytes())

    def test_manifest_fixes_training_and_holdout_payload_hashes(self):
        for name, expected in self.manifest['data_sha256'].items():
            self.assertEqual(hashlib.sha256((DATA / name).read_bytes()).hexdigest(), expected)

    def test_notebooks_compile_and_training_does_not_evaluate_test(self):
        for name in ('laya_45_45_colab.ipynb', 'laya_45_45_avaliacao_colab.ipynb'):
            notebook = json.loads((ROOT / 'notebooks' / name).read_text(encoding='utf-8'))
            self.assertEqual(notebook['nbformat'], 4)
            for index, cell in enumerate(notebook['cells']):
                if cell['cell_type'] == 'code':
                    compile(''.join(cell['source']), f'{name}:{index}', 'exec')
                    self.assertEqual(cell['outputs'], [])
                    self.assertIsNone(cell['execution_count'])
        source = (ROOT / 'scripts/train_laya_45_45.py').read_text(encoding='utf-8')
        self.assertIn('split_names = ("train",) if args.train_only', source)
        training_nb = json.loads((ROOT / 'notebooks/laya_45_45_colab.ipynb').read_text(encoding='utf-8'))
        code = '\n'.join(''.join(c['source']) for c in training_nb['cells'] if c['cell_type'] == 'code')
        self.assertNotIn('evaluate_laya_holdout.py', code)
        self.assertIn("'--train-only'", code)
        self.assertIn(self.manifest['base_revision'], code)

    def test_holdout_validator_rejects_old_checkpoint_overlap_and_changed_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            model = Path(tmp)
            (model / 'manifest.json').write_text(json.dumps(self.manifest), encoding='utf-8')
            config = {'training': {'experiment_id': self.manifest['experiment_id']}}
            (model / 'rl_agent_config.json').write_text(json.dumps(config))
            validate_holdout(model, DATA / 'holdout.jsonl', self.test)
            contaminated = copy.deepcopy(self.test)
            contaminated[0]['_meta']['case_id'] = self.manifest['train_case_ids'][0]
            with self.assertRaisesRegex(ValueError, 'overlap'):
                validate_holdout(model, DATA / 'holdout.jsonl', contaminated)
            changed = model / 'changed.jsonl'
            changed.write_bytes((DATA / 'holdout.jsonl').read_bytes() + b'\n')
            with self.assertRaisesRegex(ValueError, 'differs'):
                validate_holdout(model, changed, self.test)
            (model / 'rl_agent_config.json').write_text(json.dumps({'training': {}}))
            with self.assertRaisesRegex(ValueError, 'previous'):
                validate_holdout(model, DATA / 'holdout.jsonl', self.test)

    def test_context_filter_excludes_entire_case_not_individual_views(self):
        class Tokenizer:
            def encode(self, state, add_special_tokens=False): return range(len(state))
        rows = [{'state': state, '_meta': {'id': str(i), 'case_id': case}}
                for i, (state, case) in enumerate((('short', 'a'), ('x'*90, 'a'), ('short', 'b')))]
        kept, report = audit_rows(rows, Tokenizer(), 100, 10)
        self.assertEqual([r['_meta']['case_id'] for r in kept], ['b'])
        self.assertEqual(report['rejected_case_ids'], ['a'])

    def run_loader(self, root, uploads):
        module = types.ModuleType('google.colab')
        upload = unittest.mock.Mock(side_effect=uploads)
        module.files = types.SimpleNamespace(upload=upload)
        source = EVAL_UPLOAD_CELL.replace("Path('/content/laya_avaliacao_45')", f"Path({str(root / 'work')!r})")
        source = source.replace("Path('/content')", f"Path({str(root)!r})")
        with patch.dict('sys.modules', {'google.colab': module}), patch.object(Path, 'cwd', return_value=root), contextlib.redirect_stdout(io.StringIO()):
            scope = {}
            exec(compile(source, 'eval_upload', 'exec'), scope)
        return scope, upload

    def test_uploaded_checkpoint_is_reused_and_only_test_upload_is_requested(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            model = root / 'laya_semantic_45_45_checkpoint.zip'
            with zipfile.ZipFile(model, 'w') as archive:
                archive.writestr('model.safetensors', b'test-weights-placeholder')
            # The mock returns an explicitly selected file outside the auto-scan folder.
            test = root / 'upload' / 'laya_45_teste_reservado.zip'
            test.parent.mkdir()
            test.write_bytes((ROOT / 'notebooks/laya_45_teste_reservado.zip').read_bytes())
            scope, upload = self.run_loader(root, [{str(test): b'not-used'}])
            upload.assert_called_once()
            self.assertEqual(scope['loaded'], {'model', 'test'})
            self.assertTrue((scope['MODEL'] / 'model.safetensors').is_file())
            self.assertEqual((scope['TEST'] / 'data/holdout.jsonl').read_bytes(), (DATA / 'holdout.jsonl').read_bytes())
            self.assertNotIn('uploads', scope)

    def test_existing_archives_need_no_new_upload_and_support_colab_duplicate_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with zipfile.ZipFile(root / 'laya_semantic_45_45_checkpoint (1).zip', 'w') as archive:
                archive.writestr('model.safetensors', b'test-weights-placeholder')
            (root / 'laya_45_teste_reservado.zip').write_bytes((ROOT / 'notebooks/laya_45_teste_reservado.zip').read_bytes())
            scope, upload = self.run_loader(root, [])
            upload.assert_not_called()
            self.assertEqual(scope['loaded'], {'model', 'test'})

    def test_separate_uploads_on_first_run_and_zip_path_guard(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            selected = root / 'upload'
            selected.mkdir()
            model = selected / 'model.zip'
            test = selected / 'test.zip'
            with zipfile.ZipFile(model, 'w') as archive:
                archive.writestr('model.safetensors', b'test-weights-placeholder')
            test.write_bytes((ROOT / 'notebooks/laya_45_teste_reservado.zip').read_bytes())
            scope, upload = self.run_loader(root, [{str(model): b''}, {str(test): b''}])
            self.assertEqual(upload.call_count, 2)
            self.assertEqual(scope['loaded'], {'model', 'test'})
            with zipfile.ZipFile(model, 'w') as archive:
                archive.writestr('model.safetensors', b'test-weights-placeholder')
                archive.writestr('../outside', b'invalid-path')
            with self.assertRaisesRegex(AssertionError, 'Caminho'):
                self.run_loader(root, [{str(model): b''}])


if __name__ == '__main__':
    unittest.main()
