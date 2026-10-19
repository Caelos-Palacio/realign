"""Independent regression and safety probes using isolated repositories."""
import contextlib
import io
import json
import pathlib
import tempfile
import unittest

from realign.harness import Harness


class QualityBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.write('source.json', '{"v":"new"}')
        self.write('README.md', 'before\r\n<!-- realign:v:start -->old<!-- realign:v:end -->\r\nafter\r\n')
        self.rule = dict(id='v', kind='derived', source='source.json', pointer='/v', target='README.md', template='{value}')

    def write(self, path, contents):
        (self.root / path).write_bytes(contents.encode('utf-8'))

    def harness(self, rules=None):
        self.write('realign.json', json.dumps(dict(version=1, rules=rules or [self.rule])))
        return Harness(self.root)

    def test_decimal_precision_loss_is_error_never_false_equality(self):
        self.write('source.json', '{"v":9007199254740992.0}')
        self.write('target.json', '{"v":9007199254740993.0}')
        rule = dict(id='numeric', kind='equal', source='source.json', pointer='/v', target='target.json', targetPointer='/v')
        self.assertEqual(self.harness([rule]).check()['status'], 'error')

    def test_nested_enum_distinguishes_booleans_and_integers(self):
        self.write('source.json', '{"allowed":[1]}')
        self.write('schema.json', '{"enum":[{"allowed":[true]}]}')
        rule = dict(id='contract', kind='contract', source='source.json', schema='schema.json')
        self.assertEqual(self.harness([rule]).check()['status'], 'drift')

    def test_nested_integer_contract_does_not_accept_boolean(self):
        self.write('source.json', '{"items":[{"count":true}]}')
        self.write('schema.json', '{"type":"object","properties":{"items":{"type":"array","items":{"type":"object","properties":{"count":{"type":"integer"}},"required":["count"]}}}}')
        rule = dict(id='contract', kind='contract', source='source.json', schema='schema.json')
        self.assertEqual(self.harness([rule]).check()['status'], 'drift')

    def test_deep_config_returns_structured_cli_error_without_crash(self):
        from realign.cli import main
        self.write('realign.json', '[' * 1500 + '0' + ']' * 1500)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            code = main(['check', '--root', str(self.root), '--json'])
        self.assertEqual(code, 2)
        self.assertEqual(json.loads(output.getvalue())['status'], 'error')

    def test_marker_injection_never_writes(self):
        self.write('source.json', json.dumps({'v': '<!-- realign:evil:start -->payload'}))
        h = self.harness()
        before = (self.root / 'README.md').read_bytes()
        self.assertEqual(h.fix()['status'], 'error')
        self.assertEqual((self.root / 'README.md').read_bytes(), before)

    def test_generated_output_size_is_bounded_without_write(self):
        h = self.harness()
        self.write('source.json', json.dumps({'v': 'a' * (h.MAX_BYTES - 20)}))
        before = (self.root / 'README.md').read_bytes()
        self.assertEqual(h.fix()['status'], 'error')
        self.assertEqual((self.root / 'README.md').read_bytes(), before)

    def test_repair_preserves_crlf_and_file_mode_and_authority(self):
        h = self.harness()
        target = self.root / 'README.md'
        target.chmod(0o640)
        source = (self.root / 'source.json').read_bytes()
        before = target.read_bytes()
        self.assertEqual(h.fix()['status'], 'repaired')
        self.assertEqual(target.read_bytes(), before.replace(b'>old<', b'>new<'))
        self.assertEqual(target.stat().st_mode & 0o777, 0o640)
        self.assertEqual((self.root / 'source.json').read_bytes(), source)
        self.assertEqual(h.check()['status'], 'clean')

    def test_second_file_write_failure_restores_first(self):
        self.write('SECOND.md', '<!-- realign:b:start -->old<!-- realign:b:end -->')
        second = {**self.rule, 'id': 'b', 'target': 'SECOND.md'}
        h = self.harness([self.rule, second])
        first_before = (self.root / 'README.md').read_bytes()
        second_before = (self.root / 'SECOND.md').read_bytes()
        original = h._replace
        def fail_second(path, content):
            if path.name == 'SECOND.md':
                raise OSError('simulated disk write failure')
            original(path, content)
        h._replace = fail_second
        self.assertEqual(h.fix()['status'], 'error')
        self.assertEqual((self.root / 'README.md').read_bytes(), first_before)
        self.assertEqual((self.root / 'SECOND.md').read_bytes(), second_before)
        self.assertFalse((self.root / '.realign.lock').exists())


if __name__ == '__main__':
    unittest.main()
