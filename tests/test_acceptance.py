"""Independent adversarial acceptance scenarios for repair boundaries."""
import contextlib
import io
import json
import os
import pathlib
import tempfile
import unittest

from realign.harness import ConfigError, Harness


class RepairBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.write('source.json', '{"version":"1.0"}')
        self.write('README.md', 'before\n<!-- realign:v:start -->old<!-- realign:v:end -->\nafter\n')
        self.rule = dict(id='v', kind='derived', source='source.json', pointer='/version', target='README.md', template='{value}')

    def write(self, path, contents):
        (self.root / path).write_text(contents)

    def harness(self, rules=None):
        self.write('realign.json', json.dumps({'version': 1, 'rules': rules or [self.rule]}))
        return Harness(self.root)

    def test_given_unknown_keyword_in_absent_property_then_schema_errors(self):
        self.write('data.json', '{}')
        self.write('schema.json', '{"type":"object","properties":{"absent":{"format":"email"}}}')
        h = self.harness([dict(id='data', kind='contract', source='data.json', schema='schema.json')])
        self.assertEqual(h.check()['status'], 'error')

    def test_given_hardlinked_target_then_no_external_alias_mutation(self):
        alias = self.root / 'alias.md'
        os.link(self.root / 'README.md', alias)
        before = alias.read_bytes()
        with self.assertRaises(ConfigError):
            self.harness()
        self.assertEqual(alias.read_bytes(), before)

    def test_given_repeated_markers_then_repair_is_blocked(self):
        block = '<!-- realign:v:start -->old<!-- realign:v:end -->'
        self.write('README.md', block + '\n' + block)
        before = (self.root / 'README.md').read_bytes()
        h = self.harness()
        self.assertEqual(h.fix()['status'], 'blocked')
        self.assertEqual((self.root / 'README.md').read_bytes(), before)

    def test_given_postverification_failure_then_original_bytes_restored(self):
        h = self.harness()
        before = (self.root / 'README.md').read_bytes()
        h.check = lambda: {'status': 'error', 'findings': [{'code': 'ERROR'}]}
        self.assertEqual(h.fix()['status'], 'error')
        self.assertEqual((self.root / 'README.md').read_bytes(), before)
        self.assertFalse((self.root / '.realign.lock').exists())

    def test_given_large_json_integer_then_number_contract_does_not_crash(self):
        self.write('data.json', '1' + '0' * 400)
        self.write('schema.json', '{"type":"number"}')
        h = self.harness([dict(id='data', kind='contract', source='data.json', schema='schema.json')])
        self.assertEqual(h.check()['status'], 'clean')

    def test_given_overflowing_json_number_then_error_not_false_equality(self):
        self.write('source.json', '{"version":1e999}')
        self.write('other.json', '{"version":1e999}')
        rule = dict(id='equal', kind='equal', source='source.json', pointer='/version', target='other.json', targetPointer='/version')
        self.assertEqual(self.harness([rule]).check()['status'], 'error')

    def test_given_invalid_config_when_cli_json_then_structured_error_and_exit_two(self):
        from realign.cli import main
        self.write('realign.json', '{"version":99,"rules":[]}')
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(['check', '--root', str(self.root), '--json'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['status'], 'error')


if __name__ == '__main__':
    unittest.main()
