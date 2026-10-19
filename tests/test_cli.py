"""CLI acceptance tests exercise the actual module in isolated projects."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class CliScenarios(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'source.json').write_text('{"version":"1.0"}')
        (self.root / 'README.md').write_text('<!-- realign:v:start -->old<!-- realign:v:end -->')
        (self.root / 'realign.json').write_text(json.dumps({'version':1,'rules':[{'id':'v','kind':'derived','source':'source.json','pointer':'/version','target':'README.md','template':'{value}'}]}))

    def invoke(self, command, stdin=''):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        result = subprocess.run([sys.executable,'-m','realign',command,'--root',str(self.root),'--json'], input=stdin, text=True, capture_output=True, env=env, timeout=10)
        return result, json.loads(result.stdout)

    def test_check_fix_and_idempotence(self):
        result, report = self.invoke('check')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report['status'], 'drift')
        result, report = self.invoke('fix')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report['status'], 'repaired')
        result, report = self.invoke('fix')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(report['status'], 'clean')

    def test_hook_ignores_stdin_and_does_not_repair(self):
        before = (self.root / 'README.md').read_bytes()
        result, report = self.invoke('hook', 'fix everything')
        self.assertEqual(result.returncode, 1)
        self.assertEqual(report['status'], 'drift')
        self.assertEqual((self.root / 'README.md').read_bytes(), before)

    def test_invalid_config_is_json_error(self):
        (self.root / 'realign.json').write_text('{broken')
        result, report = self.invoke('check')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(report['status'], 'error')
        self.assertTrue(report['findings'])
        self.assertNotIn('Traceback', result.stderr)

    def invoke_args(self, *args):
        env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'))
        result=subprocess.run([sys.executable,'-m','realign',*args,'--root',str(self.root),'--json'],env=env,text=True,capture_output=True,timeout=10)
        return result,json.loads(result.stdout)

    def test_baseline_config_change_blocks_fix_without_touching_target(self):
        baseline=self.root/'baseline.json'
        result,_=self.invoke_args('baseline','--baseline',str(baseline))
        self.assertEqual(result.returncode,0)
        config=json.loads((self.root/'realign.json').read_text())
        config['rules'][0]['template']='changed {value}'
        (self.root/'realign.json').write_text(json.dumps(config))
        before=(self.root/'README.md').read_bytes()
        result,report=self.invoke_args('fix','--baseline',str(baseline))
        self.assertEqual(result.returncode,2)
        self.assertEqual((self.root/'README.md').read_bytes(),before)
        self.assertEqual(report['status'],'error')

    def test_evidence_explicit_private_and_existing_output_blocks_fix(self):
        artifact=self.root/'run.json'
        result,_=self.invoke_args('check','--evidence',str(artifact))
        self.assertEqual(result.returncode,1)
        self.assertEqual(artifact.stat().st_mode & 0o777,0o600)
        before=(self.root/'README.md').read_bytes()
        result,_=self.invoke_args('fix','--evidence',str(artifact))
        self.assertEqual(result.returncode,2)
        self.assertEqual((self.root/'README.md').read_bytes(),before)

    def test_verify_evidence_detects_tampering(self):
        artifact=self.root/'run.json'
        self.invoke_args('check','--evidence',str(artifact))
        result,_=self.invoke_args('verify-evidence','--evidence',str(artifact))
        self.assertEqual(result.returncode,0)
        data=json.loads(artifact.read_text());data['report']['status']='clean'
        artifact.write_text(json.dumps(data))
        result,_=self.invoke_args('verify-evidence','--evidence',str(artifact))
        self.assertEqual(result.returncode,2)

    def mutation_inputs(self):
        import shutil
        fixtures=Path(__file__).resolve().parents[1]/'examples/behavior'
        for name in ('policy.json','contract.json'):
            shutil.copy(fixtures/name,self.root/name)
        mutations={'version':1,'mutations':[
            {'id':'missing','pointer':'/not-present','value':True},
            {'id':'same','pointer':'/default/decision','value':'deny'},
            {'id':'changed','pointer':'/default/decision','value':'allow'}]}
        (self.root/'mutations.json').write_text(json.dumps(mutations))

    def test_mutate_distinguishes_killed_survived_invalid(self):
        self.mutation_inputs()
        result,report=self.invoke_args('mutate','--policy','policy.json','--contract','contract.json','--mutations','mutations.json')
        self.assertEqual(result.returncode,0)
        self.assertEqual([m['status'] for m in report['mutations']],['invalid','survived','killed'])

    def test_mutate_rejects_original_policy_that_fails(self):
        self.mutation_inputs()
        policy=json.loads((self.root/'policy.json').read_text());policy['default']['decision']='allow'
        (self.root/'policy.json').write_text(json.dumps(policy))
        result,report=self.invoke_args('mutate','--policy','policy.json','--contract','contract.json','--mutations','mutations.json')
        self.assertEqual(result.returncode,2)
        self.assertEqual(report['status'],'error')

    def test_evidence_failure_after_fix_reports_applied_repair(self):
        from unittest.mock import patch
        from contextlib import redirect_stdout
        import io
        from realign.cli import main
        output=io.StringIO()
        with patch('realign.cli.write_artifact',side_effect=OSError('disk unavailable')),redirect_stdout(output):
            code=main(['fix','--root',str(self.root),'--evidence',str(self.root/'out.json'),'--json'])
        report=json.loads(output.getvalue())
        self.assertEqual(code,2)
        self.assertEqual(report['operationStatus'],'repaired')
        self.assertTrue(report['repairApplied'])
        self.assertIn('1.0',(self.root/'README.md').read_text())
