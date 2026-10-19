import json
import os
from pathlib import Path
import tempfile
import unittest
from realign.harness import Harness, ConfigError
from realign.evidence import capture_baseline, verify_baseline, build_evidence, write_artifact, verify_artifact


class EvidenceBoundaries(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        (self.root/'data.json').write_text('{"secret":"not-for-report"}')
        (self.root/'schema.json').write_text('{"type":"object"}')
        (self.root/'realign.json').write_text(json.dumps({'version':1,'rules':[{'id':'data','kind':'contract','source':'data.json','schema':'schema.json'}]}))
        self.h=Harness(self.root)

    def test_baseline_freezes_criteria_not_data(self):
        baseline=capture_baseline(self.h)
        (self.root/'data.json').write_text('{}')
        verify_baseline(self.h,baseline)
        (self.root/'schema.json').write_text('{"type":"string"}')
        with self.assertRaises(ConfigError):verify_baseline(self.h,baseline)

    def test_digest_detects_changes(self):
        baseline=capture_baseline(self.h)
        verify_artifact(baseline)
        baseline['kind']='altered'
        with self.assertRaises(ConfigError):verify_artifact(baseline)

    def test_evidence_omits_values_and_untrusted_messages(self):
        report={'status':'drift','findings':[{'id':'data','code':'CONTRACT','message':'not-for-report','actual':'not-for-report'}]}
        self.h.check()
        artifact=build_evidence(self.h,report)
        self.assertNotIn('not-for-report',json.dumps(artifact))
        self.assertIn('inputs',artifact)
        verify_artifact(artifact)

    def test_write_exclusive_private_and_cannot_overwrite_inputs(self):
        path=self.root/'evidence.json';data=capture_baseline(self.h)
        write_artifact(path,data,self.h)
        self.assertEqual(path.stat().st_mode & 0o777,0o600)
        with self.assertRaises(ConfigError):write_artifact(path,data,self.h)
        with self.assertRaises(ConfigError):write_artifact(self.root/'schema.json',data,self.h)

    def test_symlink_output_rejected(self):
        link=self.root/'link';link.symlink_to(self.root/'new')
        with self.assertRaises(ConfigError):write_artifact(link,capture_baseline(self.h),self.h)
