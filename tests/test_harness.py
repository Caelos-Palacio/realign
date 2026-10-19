"""Executable acceptance scenarios: Given a project, When checked/repaired, Then..."""
import json
import pathlib
import tempfile
import unittest

from realign.harness import Harness, ConfigError


class CoherenceScenarios(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.write('package.json', '{"version":"1.2.0"}')
        self.write('README.md', '# Demo\n<!-- realign:version:start -->old<!-- realign:version:end -->\nHandwritten.\n')
        self.rule = {'id':'version','kind':'derived','source':'package.json','pointer':'/version','target':'README.md','template':'Version {value}'}

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def harness(self, rules=None):
        self.write('realign.json', json.dumps({'version':1,'rules':rules if rules is not None else [self.rule]}))
        return Harness(self.root)

    def test_given_stale_readme_when_fix_then_only_derived_block_changes(self):
        h = self.harness()
        self.assertEqual(h.check()['findings'][0]['code'], 'DRIFT')
        result = h.fix()
        self.assertEqual(result['status'], 'repaired')
        self.assertIn('Version 1.2.0', (self.root/'README.md').read_text())
        self.assertTrue((self.root/'README.md').read_text().endswith('Handwritten.\n'))
        self.assertEqual(h.fix()['status'], 'clean')

    def test_given_missing_markers_then_no_repair(self):
        self.write('README.md', 'Handwritten only')
        h = self.harness()
        self.assertEqual(h.check()['findings'][0]['code'], 'MARKERS')
        self.assertEqual(h.fix()['status'], 'blocked')
        self.assertEqual((self.root/'README.md').read_text(), 'Handwritten only')

    def test_given_contract_failure_then_no_partial_repairs(self):
        self.write('data.json', '{"count":"wrong"}')
        self.write('schema.json', '{"type":"object","properties":{"count":{"type":"integer"}},"required":["count"],"additionalProperties":false}')
        h = self.harness([self.rule, {'id':'data','kind':'contract','source':'data.json','schema':'schema.json'}])
        before = (self.root/'README.md').read_bytes()
        self.assertEqual(h.fix()['status'], 'blocked')
        self.assertEqual((self.root/'README.md').read_bytes(), before)

    def test_given_equal_json_values_then_clean(self):
        self.write('other.json', '{"release":"1.2.0"}')
        rule={'id':'same','kind':'equal','source':'package.json','pointer':'/version','target':'other.json','targetPointer':'/release'}
        self.assertEqual(self.harness([rule]).check()['status'], 'clean')
        self.write('other.json', '{"release":"2.0.0"}')
        self.assertEqual(self.harness([rule]).fix()['status'], 'blocked')

    def test_given_escape_path_then_rejected(self):
        self.rule['source']='../outside.json'
        with self.assertRaises(ConfigError): self.harness()

    def test_given_symlink_then_rejected(self):
        (self.root/'link.json').symlink_to(self.root/'package.json')
        self.rule['source']='link.json'
        with self.assertRaises(ConfigError): self.harness()

    def test_given_duplicate_rule_then_rejected(self):
        with self.assertRaises(ConfigError): self.harness([self.rule,self.rule])

    def test_given_unknown_schema_keyword_then_error_not_pass(self):
        self.write('data.json', '{}')
        self.write('schema.json', '{"type":"object","$ref":"other.json"}')
        report=self.harness([{'id':'data','kind':'contract','source':'data.json','schema':'schema.json'}]).check()
        self.assertEqual(report['status'], 'error')

    def test_given_boolean_where_integer_expected_then_rejected(self):
        self.write('data.json', 'true')
        self.write('schema.json', '{"type":"integer"}')
        report=self.harness([{'id':'data','kind':'contract','source':'data.json','schema':'schema.json'}]).check()
        self.assertEqual(report['findings'][0]['code'], 'CONTRACT')

    def test_given_changed_authority_then_repair_refused(self):
        h=self.harness()
        original=h._apply
        def concurrent(changes, fingerprints):
            self.write('package.json','{"version":"9.0.0"}')
            return original(changes,fingerprints)
        h._apply=concurrent
        self.assertEqual(h.fix()['status'], 'error')
        self.assertIn('old', (self.root/'README.md').read_text())

    def test_given_existing_lock_then_no_write(self):
        h=self.harness()
        self.write('.realign.lock','another writer')
        self.assertEqual(h.fix()['status'], 'error')
        self.assertEqual((self.root/'.realign.lock').read_text(),'another writer')

    def test_given_hook_then_check_only_and_ignores_stdin(self):
        from realign.cli import main
        self.harness()
        self.assertEqual(main(['hook','--root',str(self.root)]),1)
        self.assertIn('old',(self.root/'README.md').read_text())

    def test_given_unsupported_config_then_rejected(self):
        self.rule['command']='echo unsafe'
        with self.assertRaises(ConfigError): self.harness()

    def test_given_duplicate_json_keys_then_error(self):
        self.write('package.json','{"version":"1","version":"2"}')
        self.assertEqual(self.harness().check()['status'],'error')

    def test_given_same_file_two_blocks_then_both_repaired(self):
        self.write('README.md','<!-- realign:version:start -->x<!-- realign:version:end -->\n<!-- realign:other:start -->x<!-- realign:other:end -->')
        second={**self.rule,'id':'other'}
        h=self.harness([self.rule,second])
        self.assertEqual(h.fix()['status'],'repaired')
        self.assertEqual(h.check()['status'],'clean')

    def test_given_missing_secret_pointer_then_error_does_not_echo_name(self):
        self.rule['pointer'] = '/SECRET_SENTINEL'
        report = self.harness().check()
        # Config metadata remains visible; the diagnostic must not echo values.
        self.assertNotIn('SECRET_SENTINEL', report['findings'][0]['message'])

    def test_given_non_string_rule_kind_then_config_error(self):
        self.rule['kind'] = []
        with self.assertRaises(ConfigError):
            self.harness()

    def test_given_mutated_runtime_rule_then_no_write(self):
        h = self.harness()
        h.rules[0]['template'] = 'Changed {value}'
        self.assertEqual(h.fix()['status'], 'error')
        self.assertIn('old', (self.root/'README.md').read_text())

    def test_given_invalid_utf8_then_no_bytes_in_diagnostic(self):
        (self.root/'README.md').write_bytes(b'SECRET_SENTINEL\xff')
        report = self.harness().check()
        self.assertEqual(report['status'], 'error')
        self.assertNotIn('0xff', report['findings'][0]['message'])

    def test_given_lock_removed_by_other_writer_then_cleanup_does_not_raise(self):
        h = self.harness()
        original = h._apply
        def remove_lock(changes, fingerprints):
            (self.root/'.realign.lock').unlink()
            return original(changes, fingerprints)
        h._apply = remove_lock
        self.assertIn(h.fix()['status'], ('repaired', 'error'))

    def test_given_reserved_marker_value_then_no_write(self):
        self.write('package.json', json.dumps({'version':'<!-- realign:version:end -->'}))
        h = self.harness()
        before = (self.root/'README.md').read_bytes()
        self.assertEqual(h.fix()['status'], 'error')
        self.assertEqual((self.root/'README.md').read_bytes(), before)

    def test_given_replaced_lock_then_foreign_lock_is_preserved(self):
        h = self.harness()
        original = h._apply
        def replace_lock(changes, fingerprints):
            lock = self.root/'.realign.lock'
            replacement = self.root/'foreign-lock'
            replacement.write_text('foreign owner')
            replacement.replace(lock)
            return original(changes, fingerprints)
        h._apply = replace_lock
        self.assertEqual(h.fix()['status'], 'error')
        self.assertEqual((self.root/'.realign.lock').read_text(), 'foreign owner')
        self.assertIn('old', (self.root/'README.md').read_text())

    def test_given_second_target_conflicts_then_first_target_still_rolls_back(self):
        self.write('OTHER.md', '<!-- realign:other:start -->old<!-- realign:other:end -->')
        h = self.harness([self.rule, {**self.rule,'id':'other','target':'OTHER.md'}])
        before = (self.root/'README.md').read_bytes()
        def changed_during_postcheck():
            self.write('OTHER.md', 'external newer content')
            return {'status':'error','findings':[]}
        h.check = changed_during_postcheck
        self.assertEqual(h.fix()['status'], 'error')
        self.assertEqual((self.root/'README.md').read_bytes(), before)
        self.assertEqual((self.root/'OTHER.md').read_text(), 'external newer content')


if __name__ == '__main__': unittest.main()
