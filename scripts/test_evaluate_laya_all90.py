"""Protocol checks for the optional long-context evaluation."""
import contextlib
import io
import unittest
from scripts.evaluate_laya_all90 import validated_cache, long_prediction, build_report


class LongEvaluationTests(unittest.TestCase):
    def setUp(self):
        self.meta = {'id': 'case', 'class': 'C', 'method': 'm()', 'label': 'Yes',
                     'split': 'test', 'exposure': 'not_used_due_to_context'}
        self.row = {'_meta': self.meta, 'state': 'B/L/R/M', 'questions': {'semantic_interference': {}}}

    def test_cache_rejects_different_inputs_or_labels(self):
        prediction = {'id': 'case', 'class': 'C', 'method': 'm()', 'gold': True,
            'split': 'test', 'exposure': 'not_used_due_to_context', 'status': 'ok', 'probability': .8}
        report = {'model_sha256': 'same', 'predictions': [prediction]}
        cached = validated_cache(report, [self.row], {'model_sha256': 'same'})
        self.assertEqual(cached['case']['inference_method'], 'full_state')
        with self.assertRaisesRegex(ValueError, 'model_sha256'):
            validated_cache(report, [self.row], {'model_sha256': 'changed'})
        prediction['gold'] = False
        with self.assertRaisesRegex(ValueError, 'metadata'):
            validated_cache(report, [self.row], {'model_sha256': 'same'})

    def test_long_scan_keeps_attribution_and_rejects_any_dropped_tokens(self):
        class Tokenizer:
            def encode(inner, *args, **kwargs): return [1] * 100
        class Agent:
            tok = Tokenizer()
            dropped = 0
            def predict_long(inner, state, questions, batch_size):
                self.assertEqual(state, self.row['state'])
                self.assertEqual(batch_size, 1)
                return {'answers': {'semantic_interference': {'noul': .8,
                    'window': {'index': 1, 'token_start': 30, 'token_end': 100, 'count': 2}}},
                    'usage': {'windows': 2, 'truncated': 0, 'state_tokens_dropped': inner.dropped}}
        agent = Agent()
        with contextlib.redirect_stdout(io.StringIO()):
            result = long_prediction(agent, self.row)
        self.assertEqual(result['inference_method'], 'sliding_windows')
        self.assertEqual(result['deciding_window']['index'], 1)
        agent.dropped = 1
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(ValueError, 'truncation'):
            long_prediction(agent, self.row)

    def test_report_never_calls_window_max_a_calibrated_probability(self):
        prediction = {**{k: self.meta[k] for k in ('id', 'class', 'method', 'split', 'exposure')},
            'gold': True, 'status': 'ok', 'probability': .8, 'inference_method': 'sliding_windows'}
        report = build_report({}, [self.row], {'case': prediction}, .5)
        self.assertTrue(report['complete'])
        self.assertEqual(report['metrics']['tp'], 1)
        self.assertIsNone(report['metrics']['brier'])
        self.assertIsNone(report['partitions']['test']['metrics']['brier'])
        pending = build_report({}, [self.row], {}, .5)
        self.assertFalse(pending['complete'])
        self.assertEqual(pending['metrics']['coverage'], 0)


if __name__ == '__main__':
    unittest.main()
