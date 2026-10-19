"""Independent semantic acceptance corpus; outcomes are fixed before interpreter execution."""
import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from realign.contracts import check_behavior, evaluate_policy, evaluate_mutations
from realign.harness import Harness, ConfigError


CORPUS = Path(__file__).resolve().parents[1] / 'examples' / 'behavior'


class SemanticQuality(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((CORPUS / 'policy.json').read_text())
        self.contract = json.loads((CORPUS / 'contract.json').read_text())

    def test_independent_corpus_matches_decisions_traces_and_effects(self):
        self.assertEqual(check_behavior(self.policy, self.contract), [])
        for scenario in self.contract['scenarios']:
            with self.subTest(scenario=scenario['id']):
                self.assertEqual(evaluate_policy(self.policy, scenario['given']), scenario['expected'])

    def test_negation_mutant_is_detected(self):
        mutant = copy.deepcopy(self.policy)
        mutant['rules'][2]['when']['args'][2] = mutant['rules'][2]['when']['args'][2]['arg']
        self.assertTrue(check_behavior(mutant, self.contract))

    def test_all_to_any_mutant_is_detected(self):
        mutant = copy.deepcopy(self.policy)
        mutant['rules'][2]['when']['op'] = 'any'
        self.assertTrue(check_behavior(mutant, self.contract))

    def test_threshold_mutant_is_detected(self):
        mutant = copy.deepcopy(self.policy)
        mutant['rules'][2]['when']['args'][3]['op'] = 'gt'
        self.assertTrue(check_behavior(mutant, self.contract))

    def test_deny_everything_is_not_success(self):
        mutant = copy.deepcopy(self.policy)
        mutant['rules'] = []
        self.assertTrue(check_behavior(mutant, self.contract))

    def test_trace_order_mutant_is_detected_even_with_same_effects(self):
        mutant = copy.deepcopy(self.policy)
        mutant['rules'][2]['outcome']['trace'] = ['validate', 'write', 'authorize']
        findings = check_behavior(mutant, self.contract)
        self.assertTrue(findings)
        self.assertTrue(any(any(path.startswith('/trace') for path in finding['differences']) for finding in findings))

    def test_declarative_mutation_corpus_reports_killed_surviving_and_invalid(self):
        mutations = json.loads((CORPUS / 'mutations.json').read_text())
        before = copy.deepcopy(self.policy)
        report = evaluate_mutations(self.policy, self.contract, mutations)
        results = {entry['id']: entry['status'] for entry in report['mutations']}
        self.assertEqual(results['equivalent-numeric-threshold'], 'survived')
        self.assertEqual(results['invalid-operator'], 'invalid')
        self.assertEqual(sum(status == 'killed' for status in results.values()), 7)
        self.assertEqual(len(results), 9)
        self.assertEqual(self.policy, before)

    def test_mutation_analysis_refuses_already_failing_original(self):
        mutations = json.loads((CORPUS / 'mutations.json').read_text())
        self.policy['rules'][2]['when']['args'][3]['op'] = 'gt'
        with self.assertRaises(ConfigError):
            evaluate_mutations(self.policy, self.contract, mutations)

    def test_acceptance_change_after_baseline_verification_cannot_authorize_fix(self):
        from realign import cli
        from realign.evidence import capture_baseline, verify_baseline, write_artifact
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            allow = {'decision': 'allow', 'trace': [], 'effects': []}
            deny = {'decision': 'deny', 'trace': [], 'effects': []}
            policy = {'version': 1, 'rules': [], 'default': allow}
            contract = {'version': 1, 'scenarios': [dict(id='case', requirementId='R', given={}, expected=deny)]}
            (root / 'policy.json').write_text(json.dumps(policy))
            (root / 'contract.json').write_text(json.dumps(contract))
            (root / 'source.json').write_text('{"v":"new"}')
            (root / 'README.md').write_text('<!-- realign:v:start -->old<!-- realign:v:end -->')
            config = {'version': 1, 'rules': [
                dict(id='v', kind='derived', source='source.json', pointer='/v', target='README.md', template='{value}'),
                dict(id='behavior', kind='behavior', source='policy.json', contract='contract.json'),
            ]}
            (root / 'realign.json').write_text(json.dumps(config))
            baseline = root / 'baseline.json'
            write_artifact(baseline, capture_baseline(Harness(root)))
            before = (root / 'README.md').read_bytes()
            def change_after_verification(harness, artifact):
                verify_baseline(harness, artifact)
                contract['scenarios'][0]['expected'] = allow
                (root / 'contract.json').write_text(json.dumps(contract))
            output = io.StringIO()
            with mock.patch.object(cli, 'verify_baseline', change_after_verification), contextlib.redirect_stdout(output):
                code = cli.main(['fix', '--root', str(root), '--baseline', str(baseline), '--json'])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())['status'], 'error')
            self.assertEqual((root / 'README.md').read_bytes(), before)

    def test_evidence_does_not_attach_clean_result_to_changed_inputs(self):
        from realign import cli
        from realign.evidence import build_evidence
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'source.json').write_text('{"v":1}')
            (root / 'target.json').write_text('{"v":1}')
            (root / 'realign.json').write_text(json.dumps({'version': 1, 'rules': [
                dict(id='same', kind='equal', source='source.json', pointer='/v', target='target.json', targetPointer='/v')
            ]}))
            destination = root / 'evidence.json'
            def change_after_check(harness, report, before=None):
                (root / 'source.json').write_text('{"v":2}')
                return build_evidence(harness, report, before)
            output = io.StringIO()
            with mock.patch.object(cli, 'build_evidence', change_after_check), contextlib.redirect_stdout(output):
                code = cli.main(['check', '--root', str(root), '--evidence', str(destination), '--json'])
            self.assertEqual(code, 2)
            self.assertEqual(json.loads(output.getvalue())['status'], 'error')
            self.assertFalse(destination.exists())

    def test_behavior_failure_blocks_derived_fix_without_touching_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mutant = copy.deepcopy(self.policy)
            mutant['rules'][2]['when']['args'][3]['op'] = 'gt'
            (root / 'policy.json').write_text(json.dumps(mutant))
            (root / 'contract.json').write_bytes((CORPUS / 'contract.json').read_bytes())
            (root / 'source.json').write_text('{"v":"new"}')
            (root / 'README.md').write_text('<!-- realign:v:start -->old<!-- realign:v:end -->')
            config = {'version': 1, 'rules': [
                dict(id='v', kind='derived', source='source.json', pointer='/v', target='README.md', template='{value}'),
                dict(id='behavior', kind='behavior', source='policy.json', contract='contract.json'),
            ]}
            (root / 'realign.json').write_text(json.dumps(config))
            before = {path.name: path.read_bytes() for path in root.iterdir()}
            self.assertEqual(Harness(root).fix()['status'], 'blocked')
            self.assertEqual({path.name: path.read_bytes() for path in root.iterdir()}, before)


if __name__ == '__main__':
    unittest.main()
