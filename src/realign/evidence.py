"""Explicit acceptance snapshots and content-addressed, value-free evidence."""
import hashlib
import json
import os
from pathlib import Path
import tempfile

from . import __version__
from .harness import ConfigError, _json

MAX_ARTIFACT = 2 * 1024 * 1024


def _canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def seal(payload):
    result = dict(payload)
    result['digest'] = hashlib.sha256(_canonical(payload)).hexdigest()
    return result


def verify_artifact(artifact):
    if not isinstance(artifact, dict) or 'digest' not in artifact:
        raise ConfigError('missing artifact digest')
    if type(artifact.get('version')) is not int or artifact['version'] != 1 or artifact.get('kind') not in {'acceptance-baseline','coherence-evidence'}:
        raise ConfigError('unsupported artifact format')
    payload = {k:v for k,v in artifact.items() if k != 'digest'}
    if artifact['digest'] != hashlib.sha256(_canonical(payload)).hexdigest():
        raise ConfigError('artifact digest mismatch')
    return artifact


def input_hashes(harness, acceptance=False):
    names = {'realign.json'}
    for rule in harness.rules:
        keys = ('schema', 'contract') if acceptance else ('source', 'target', 'schema', 'contract')
        names.update(rule[k] for k in keys if k in rule)
    return {name:hashlib.sha256(harness._read(harness._path(name))).hexdigest() for name in sorted(names)}


def capture_baseline(harness):
    return seal({'version':1, 'kind':'acceptance-baseline', 'inputs':input_hashes(harness, acceptance=True)})


def verify_baseline(harness, baseline):
    verify_artifact(baseline)
    if set(baseline) != {'version','kind','inputs','digest'} or type(baseline['version']) is not int or baseline['version'] != 1 or baseline['kind'] != 'acceptance-baseline':
        raise ConfigError('invalid acceptance baseline')
    if baseline['inputs'] != input_hashes(harness, acceptance=True):
        raise ConfigError('acceptance criteria changed; baseline mismatch')
    harness.bind_acceptance(baseline['inputs'])


def read_artifact(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ConfigError('artifact symlinks are unsupported')
    with path.open('rb') as stream:
        raw = stream.read(MAX_ARTIFACT + 1)
    if len(raw) > MAX_ARTIFACT:
        raise ConfigError('artifact too large')
    return verify_artifact(_json(raw))


def build_evidence(harness, report, before=None):
    harness.validate_observed_inputs()
    observed = harness.observed_inputs()
    safe_findings = []
    for finding in report.get('findings', []):
        safe_findings.append({k:v for k,v in finding.items() if k in {'id','code','expectedHash','actualHash'} and isinstance(v,str)})
    kinds = sorted({rule['kind'] for rule in harness.rules})
    return seal({'version':1, 'kind':'coherence-evidence', 'tool':{'name':'realign','version':__version__},
                 'inputs':observed, 'beforeInputs':before or {},
                 'coverage':{'ruleTypes':kinds,'ruleCount':len(harness.rules),
                             'scope':'declared files and explicit behavior scenarios only',
                             'behavior':[ {k:v for k,v in row.items() if k in {'id','kind','scenarioCount','finiteDomain'}}
                                          for row in report.get('coverage', []) ]},
                 'report':{'status':report['status'],'findings':safe_findings}})


def validate_destination(path, harness=None, forbidden=()):
    path = Path(path).absolute()
    if any(p.is_symlink() for p in (path, *path.parents)):
        raise ConfigError('artifact symlinks are unsupported')
    blocked = {Path(p).resolve() for p in forbidden}
    if harness is not None:
        blocked.update(harness._path(name) for name in input_hashes(harness))
        blocked.add(harness.root / '.realign.lock')
    if path.resolve() in blocked or path.exists():
        raise ConfigError('artifact destination exists or collides with an input')
    return path


def write_artifact(path, artifact, harness=None, forbidden=()):
    """Publish a complete 0600 file atomically, without replacing any pathname."""
    path = validate_destination(path, harness, forbidden)
    raw = _canonical(artifact) + b'\n'
    if len(raw) > MAX_ARTIFACT:
        raise ConfigError('artifact too large')
    fd, temporary = tempfile.mkstemp(prefix='.realign-artifact-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError as exc:
            raise ConfigError('artifact destination already exists') from exc
    finally:
        os.unlink(temporary)
