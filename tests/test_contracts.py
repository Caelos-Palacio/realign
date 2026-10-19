"""Finite behavior contracts: observations, never executable actions."""
import copy
import hashlib
import json
import pathlib
import tempfile
import unittest

from realign.harness import ConfigError, Harness
from realign.contracts import check_behavior, evaluate_policy, evaluate_mutations, validate_contract, validate_policy


def outcome(decision, trace=None, effects=None):
    return {'decision': decision, 'trace': trace or [], 'effects': effects or []}


def rule(identity, condition, decision='allow'):
    return {'id': identity, 'when': condition, 'outcome': outcome(decision, [identity])}


class BehaviorScenarios(unittest.TestCase):
    def setUp(self):
        self.policy = {'version':1, 'rules':[
            rule('revoked', {'op':'eq','pointer':'/revoked','value':True}, 'deny'),
            rule('approved', {'op':'all','args':[
                {'op':'eq','pointer':'/approved','value':True},
                {'op':'gte','pointer':'/age','value':18},
                {'op':'not','arg':{'op':'eq','pointer':'/suspended','value':True}}
            ]})], 'default':outcome('clarify')}
        self.contract = {'version':1,'scenarios':[
            {'id':'adult','requirementId':'REQ-PERMISSION','given':{'approved':True,'age':18,'suspended':False},'expected':outcome('allow',['approved'])},
            {'id':'revoke','requirementId':'REQ-REVOKE','given':{'approved':True,'age':30,'revoked':True},'expected':outcome('deny',['revoked'])},
            {'id':'missing','requirementId':'REQ-UNKNOWN','given':{},'expected':outcome('clarify')}]}

    def test_given_finite_scenarios_when_checked_then_no_difference(self):
        self.assertEqual(check_behavior(self.policy, self.contract), [])

    def test_given_threshold_mutation_then_boundary_witness_without_values(self):
        self.policy['rules'][1]['when']['args'][1]['op'] = 'gt'
        findings = check_behavior(self.policy, self.contract)
        self.assertEqual(findings[0]['scenarioId'], 'adult')
        self.assertEqual(findings[0]['differences'], ['/decision','/trace'])
        expected = self.contract['scenarios'][0]['expected']
        canonical = json.dumps(expected, sort_keys=True, ensure_ascii=False, separators=(',',':')).encode()
        self.assertEqual(findings[0]['expectedHash'], hashlib.sha256(canonical).hexdigest())
        self.assertNotIn('given', findings[0])
        self.assertNotIn('expected', findings[0])

    def test_given_boolean_age_then_numeric_comparison_does_not_allow(self):
        self.assertEqual(evaluate_policy(self.policy, {'approved':True,'age':True})['decision'], 'clarify')

    def test_given_missing_pointer_ne_then_false_not_implicit_permission(self):
        policy = {'version':1,'rules':[rule('neq',{'op':'ne','pointer':'/missing','value':False})],'default':outcome('clarify')}
        self.assertEqual(evaluate_policy(policy, {})['decision'], 'clarify')

    def test_given_null_then_exists_and_escaped_pointer_are_exact(self):
        policy = {'version':1,'rules':[rule('exists',{'op':'exists','pointer':'/a~1b/~0x'})],'default':outcome('deny')}
        self.assertEqual(evaluate_policy(policy, {'a/b':{'~x':None}})['decision'], 'allow')

    def test_given_any_not_combination_then_truth_table(self):
        policy = {'version':1,'rules':[rule('guard',{'op':'not','arg':{'op':'any','args':[
            {'op':'eq','pointer':'/a','value':True},{'op':'eq','pointer':'/b','value':True}]}})],'default':outcome('deny')}
        for a in (False, True):
            for b in (False, True):
                self.assertEqual(evaluate_policy(policy, {'a':a,'b':b})['decision'], 'deny' if a or b else 'allow')

    def test_given_unknown_op_in_unreached_branch_then_config_error(self):
        self.policy['rules'].append(rule('bad',{'op':'exec','command':'echo secret'}))
        with self.assertRaises(ConfigError):
            evaluate_policy(self.policy, {'revoked':True})

    def test_given_empty_corpus_or_missing_provenance_then_rejected(self):
        for contract in ({'version':1,'scenarios':[]}, {'version':1,'scenarios':[{'id':'a','given':{},'expected':outcome('allow')}]}):
            with self.assertRaises(ConfigError):
                validate_contract(contract)

    def test_given_effects_commands_then_returned_as_data_without_execution(self):
        self.policy['default'] = outcome('clarify', effects=[{'command':'touch /tmp/realign-should-never-execute'}])
        result = evaluate_policy(self.policy, {})
        result['effects'][0]['command'] = 'mutated'
        self.assertEqual(self.policy['default']['effects'][0]['command'], 'touch /tmp/realign-should-never-execute')

    def test_given_duplicate_ids_and_unknown_fields_then_rejected(self):
        for mutate in (lambda p:p['rules'].append(copy.deepcopy(p['rules'][0])), lambda p:p.update({'script':'x'}), lambda p:p['default'].update({'extra':True})):
            policy = copy.deepcopy(self.policy)
            mutate(policy)
            with self.assertRaises(ConfigError): validate_policy(policy)

    def test_given_harness_behavior_drift_then_repairs_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root/'policy.json').write_text(json.dumps(self.policy))
            self.contract['scenarios'][0]['expected']['decision'] = 'deny'
            (root/'contract.json').write_text(json.dumps(self.contract))
            (root/'realign.json').write_text(json.dumps({'version':1,'rules':[{'id':'permissions','kind':'behavior','source':'policy.json','contract':'contract.json'}]}))
            h = Harness(root)
            self.assertEqual(h.check()['status'], 'drift')
            self.assertEqual(h.fix()['status'], 'blocked')
            self.assertEqual(h.check()['findings'][0]['code'], 'BEHAVIOR')

    def test_given_bounded_conditions_then_too_deep_rejected(self):
        condition = {'op':'exists','pointer':'/x'}
        for _ in range(40): condition = {'op':'not','arg':condition}
        self.policy['rules'][0]['when'] = condition
        with self.assertRaises(ConfigError): validate_policy(self.policy)

    def test_given_mutation_corpus_then_killed_survived_invalid_are_separate(self):
        mutations = {'version':1,'mutations':[
            {'id':'boundary','pointer':'/rules/1/when/args/1/op','value':'gt'},
            {'id':'same','pointer':'/rules/1/when/args/1/op','value':'gte'},
            {'id':'unknown','pointer':'/rules/1/when/args/1/op','value':'eval'},
            {'id':'absent','pointer':'/rules/900/id','value':'x'}]}
        original_policy = copy.deepcopy(self.policy)
        original_contract = copy.deepcopy(self.contract)
        result = evaluate_mutations(self.policy, self.contract, mutations)
        self.assertEqual([m['status'] for m in result['mutations']], ['killed','survived','invalid','invalid'])
        self.assertTrue(result['finiteDomain'])
        self.assertEqual(result['mutations'][0]['findings'][0]['scenarioId'], 'adult')
        self.assertEqual(self.policy, original_policy)
        self.assertEqual(self.contract, original_contract)

    def test_given_failing_baseline_then_mutation_score_refused(self):
        self.policy['rules'][1]['when']['args'][1]['op'] = 'gt'
        with self.assertRaises(ConfigError):
            evaluate_mutations(self.policy, self.contract, {'version':1,'mutations':[{'id':'same','pointer':'/version','value':1}]})

    def test_given_invalid_mutation_corpus_then_rejected_before_interpreting(self):
        for entries in ([], [{'id':'x','pointer':'','value':1}],
                        [{'id':'x','pointer':'/version','value':1,'command':'ignored'}],
                        [{'id':'x','pointer':'/version','value':1}]*2):
            with self.assertRaises(ConfigError):
                evaluate_mutations(self.policy, self.contract, {'version':1,'mutations':entries})

    def test_given_missing_and_type_mismatched_numeric_comparisons_then_false(self):
        for op in ('eq','ne','gt','gte','lt','lte'):
            policy = {'version':1,'rules':[rule('test',{'op':op,'pointer':'/n','value':1})], 'default':outcome('clarify')}
            self.assertEqual(evaluate_policy(policy,{})['decision'],'clarify')
        for value in ('100', True, None, [], {}):
            for op in ('gt','gte','lt','lte'):
                policy = {'version':1,'rules':[rule('test',{'op':op,'pointer':'/n','value':1})], 'default':outcome('clarify')}
                self.assertEqual(evaluate_policy(policy,{'n':value})['decision'],'clarify')

    def test_given_effect_order_difference_then_observable_failure(self):
        self.contract['scenarios'][0]['expected']['effects'] = [{'action':'write'},{'action':'notify'}]
        self.policy['rules'][1]['outcome']['effects'] = [{'action':'notify'},{'action':'write'}]
        findings = check_behavior(self.policy,self.contract)
        self.assertEqual(findings[0]['differences'], ['/effects/0','/effects/1'])

    def test_given_secret_effect_keys_then_only_fixed_paths_are_exposed(self):
        self.contract['scenarios'][0]['expected']['effects'] = [{'SECRET_KEY':'SECRET_VALUE'}]
        result = check_behavior(self.policy,self.contract)
        self.assertNotIn('SECRET',json.dumps(result))
        self.assertEqual(result[0]['differences'], ['/effects'])

    def test_given_invalid_late_scenario_then_no_partial_results(self):
        self.contract['scenarios'].append({'id':'late','requirementId':'R','given':{},'expected':{'decision':'allow','trace':[],'effects':[],'command':'x'}})
        with self.assertRaises(ConfigError): check_behavior(self.policy,self.contract)

    def test_given_harness_behavior_pass_then_finite_coverage_is_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root/'policy.json').write_text(json.dumps(self.policy))
            (root/'contract.json').write_text(json.dumps(self.contract))
            (root/'realign.json').write_text(json.dumps({'version':1,'rules':[{'id':'b','kind':'behavior','source':'policy.json','contract':'contract.json'}]}))
            report = Harness(root).check()
            self.assertEqual(report['status'],'clean')
            self.assertEqual(report['coverage'],[{'id':'b','kind':'behavior','scenarioCount':3,'finiteDomain':True}])

    def test_given_bound_criteria_changed_before_check_then_no_new_oracle_accepted(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root/'policy.json').write_text(json.dumps(self.policy))
            (root/'contract.json').write_text(json.dumps(self.contract))
            (root/'realign.json').write_text(json.dumps({'version':1,'rules':[{'id':'b','kind':'behavior','source':'policy.json','contract':'contract.json'}]}))
            h = Harness(root)
            hashes = {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('realign.json','contract.json')}
            h.bind_acceptance(hashes)
            changed = copy.deepcopy(self.contract)
            changed['scenarios'][0]['expected']['decision'] = 'deny'
            (root/'contract.json').write_text(json.dumps(changed))
            self.assertEqual(h.check()['status'],'error')
            self.assertEqual(h.fix()['status'],'error')

    def test_given_bound_criteria_then_implementation_may_change_but_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root/'policy.json').write_text(json.dumps(self.policy))
            (root/'contract.json').write_text(json.dumps(self.contract))
            (root/'realign.json').write_text(json.dumps({'version':1,'rules':[{'id':'b','kind':'behavior','source':'policy.json','contract':'contract.json'}]}))
            h = Harness(root)
            hashes = {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ('realign.json','contract.json')}
            h.bind_acceptance(hashes)
            self.policy['rules'][1]['when']['args'][1]['op'] = 'gt'
            (root/'policy.json').write_text(json.dumps(self.policy))
            self.assertEqual(h.check()['status'],'drift')

    def test_given_source_changes_after_evaluation_then_evidence_validation_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for name,value in [('policy.json',self.policy),('contract.json',self.contract),('realign.json',{'version':1,'rules':[{'id':'b','kind':'behavior','source':'policy.json','contract':'contract.json'}]})]:
                (root/name).write_text(json.dumps(value))
            h = Harness(root)
            self.assertEqual(h.check()['status'],'clean')
            observed = h.observed_inputs()
            self.assertEqual(observed['policy.json'],hashlib.sha256((root/'policy.json').read_bytes()).hexdigest())
            observed['policy.json'] = 'f'*64
            self.assertNotEqual(h.observed_inputs()['policy.json'],'f'*64)
            (root/'policy.json').write_text('{}')
            with self.assertRaises(ConfigError): h.validate_observed_inputs()

    def test_given_no_evaluation_then_evidence_fingerprints_are_unavailable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root/'realign.json').write_text('{"version":1,"rules":[]}')
            with self.assertRaises(ConfigError): Harness(root).observed_inputs()

    def test_given_fix_with_behavior_then_every_status_retains_finite_coverage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            (root/'policy.json').write_text(json.dumps(self.policy))
            (root/'contract.json').write_text(json.dumps(self.contract))
            (root/'v.json').write_text('{"v":"new"}')
            (root/'README.md').write_text('<!-- realign:v:start -->old<!-- realign:v:end -->')
            (root/'realign.json').write_text(json.dumps({'version':1,'rules':[
                {'id':'b','kind':'behavior','source':'policy.json','contract':'contract.json'},
                {'id':'v','kind':'derived','source':'v.json','pointer':'/v','target':'README.md','template':'{value}'}]}))
            h = Harness(root)
            report = h.fix()
            self.assertEqual(report['status'],'repaired')
            self.assertEqual(report['coverage'][0]['scenarioCount'],3)
            self.assertEqual(h.fix()['coverage'][0]['scenarioCount'],3)
            self.policy['rules'][1]['when']['args'][1]['op'] = 'gt'
            (root/'policy.json').write_text(json.dumps(self.policy))
            report = h.fix()
            self.assertEqual(report['status'],'blocked')
            self.assertEqual(report['coverage'][0]['scenarioCount'],3)


if __name__ == '__main__':
    unittest.main()
