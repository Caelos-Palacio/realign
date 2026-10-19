"""Git hook checks the staged snapshot without changing the index."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


class StagedHookScenarios(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='realign hook ')
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1] / 'src'), REALIGN_PYTHON=sys.executable)
        self.git('init', '-q')
        rule = {'id':'v','kind':'derived','source':'source file.json','pointer':'/version','target':'README file.md','template':'{value}'}
        (self.root/'realign.json').write_text(json.dumps({'version':1,'rules':[rule]}))
        (self.root/'source file.json').write_text('{"version":"1"}')
        shutil.copy(Path(__file__).resolve().parents[1]/'hooks/pre-commit', self.root/'.git/hooks/pre-commit')

    def git(self, *args):
        return subprocess.run(['git','-C',str(self.root),*args],capture_output=True,check=True)

    def target(self, value):
        (self.root/'README file.md').write_text(f'<!-- realign:v:start -->{value}<!-- realign:v:end -->')

    def hook(self):
        before=self.git('ls-files','--stage','-z').stdout
        result=subprocess.run([str(self.root/'.git/hooks/pre-commit')],cwd=self.root,env=self.env,capture_output=True,text=True,timeout=10)
        self.assertEqual(self.git('ls-files','--stage','-z').stdout,before)
        return result

    def test_stale_index_clean_worktree_is_blocked(self):
        self.target('old')
        self.git('add','.')
        self.target('1')
        self.assertEqual(self.hook().returncode,1)

    def test_clean_index_stale_worktree_is_allowed(self):
        self.target('1')
        self.git('add','.')
        self.target('old')
        self.assertEqual(self.hook().returncode,0)

    def test_untracked_configuration_cannot_approve_commit(self):
        self.target('1')
        self.git('add','source file.json','README file.md')
        self.assertEqual(self.hook().returncode,2)

    def test_unrelated_symlink_does_not_block_declared_checks(self):
        self.target('1')
        (self.root/'unrelated-link').symlink_to('/tmp')
        self.git('add','.')
        self.assertEqual(self.hook().returncode,0)

    def test_declared_symlink_is_rejected_without_following(self):
        self.target('1')
        (self.root/'source file.json').unlink()
        (self.root/'source file.json').symlink_to('/tmp/missing-secret')
        self.git('add','.')
        self.assertEqual(self.hook().returncode,2)

    def test_behavior_contract_is_read_from_index_not_worktree(self):
        policy={'version':1,'rules':[],'default':{'decision':'deny','trace':[],'effects':[]}}
        contract={'version':1,'scenarios':[{'id':'c','requirementId':'R','given':{},'expected':policy['default']}]}
        (self.root/'policy.json').write_text(json.dumps(policy))
        (self.root/'contract.json').write_text(json.dumps(contract))
        (self.root/'realign.json').write_text(json.dumps({'version':1,'rules':[{'id':'behavior','kind':'behavior','source':'policy.json','contract':'contract.json'}]}))
        self.git('add','.')
        contract['scenarios'][0]['expected']={'decision':'allow','trace':[],'effects':[]}
        (self.root/'contract.json').write_text(json.dumps(contract))
        self.assertEqual(self.hook().returncode,0)
        self.git('add','contract.json')
        self.assertEqual(self.hook().returncode,1)

    def test_deep_staged_config_returns_error_without_traceback(self):
        (self.root/'realign.json').write_text('['*2000+'0'+']'*2000)
        self.git('add','realign.json')
        result=self.hook()
        self.assertEqual(result.returncode,2)
        self.assertNotIn('Traceback',result.stderr)
