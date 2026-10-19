"""Offline checks and guarded repairs of declared project relationships."""
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile

from .schema import ConfigError, _json, _pointer, _same, _validate_schema, _matches
from .contracts import check_behavior


class Harness:
    MAX_BYTES = 2 * 1024 * 1024

    def __init__(self, root):
        self.root = Path(root).resolve(strict=True)
        self._lock_identity = None
        self._acceptance = {}
        self._observed = None
        self._coverage = []
        self.config_path = self._path('realign.json')
        self.config_bytes = self._read(self.config_path)
        config = _json(self.config_bytes)
        if not isinstance(config, dict) or set(config) != {'version', 'rules'} or type(config['version']) is not int or config['version'] != 1 or not isinstance(config['rules'], list):
            raise ConfigError('expected version 1 and rules array')
        self.rules = config['rules']
        if len(self.rules) > 1000:
            raise ConfigError('too many rules')
        self._rules_snapshot = json.dumps(self.rules, sort_keys=True)
        ids = set()
        for rule in self.rules:
            if not isinstance(rule, dict):
                raise ConfigError('rule must be object')
            kind = rule.get('kind')
            fields = {'derived': {'id', 'kind', 'source', 'pointer', 'target', 'template'},
                      'equal': {'id', 'kind', 'source', 'pointer', 'target', 'targetPointer'},
                      'contract': {'id', 'kind', 'source', 'schema'},
                      'behavior': {'id', 'kind', 'source', 'contract'}}
            if not isinstance(kind, str) or kind not in fields or set(rule) != fields[kind] or any(not isinstance(x, str) for x in rule.values()):
                raise ConfigError('unknown kind, field, or missing field')
            if not re.fullmatch(r'[A-Za-z0-9_-]+', rule['id']) or rule['id'] in ids:
                raise ConfigError('invalid or duplicate rule id')
            ids.add(rule['id'])
            for key in ('source', 'target', 'schema', 'contract'):
                if key in rule:
                    self._path(rule[key])
            for key in ('pointer', 'targetPointer'):
                if key in rule and rule[key]:
                    self._validate_pointer(rule[key])
            if kind == 'derived' and (rule['template'].count('{value}') != 1 or '{' in rule['template'].replace('{value}', '') or '}' in rule['template'].replace('{value}', '')):
                raise ConfigError('template must contain exactly one {value}')
        authorities = {self._path(r['source']) for r in self.rules} | {self._path(r['schema']) for r in self.rules if 'schema' in r} | {self._path(r['contract']) for r in self.rules if 'contract' in r} | {self.config_path, self.root / '.realign.lock'}
        if any(self._path(r['target']) in authorities for r in self.rules if r['kind'] == 'derived'):
            raise ConfigError('derived target cannot be an authority')

    def bind_acceptance(self, inputs):
        """Pin explicit criteria hashes across verification and later repair reads."""
        names = {'realign.json'}
        for rule in self.rules:
            names.update(rule[key] for key in ('schema', 'contract') if key in rule)
        if not isinstance(inputs, dict) or set(inputs) != names:
            raise ConfigError('acceptance baseline must cover exactly configured criteria')
        expected = {}
        for name, digest in inputs.items():
            if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
                raise ConfigError('invalid acceptance fingerprint')
            path = self._path(name)
            if path in expected and expected[path] != digest:
                raise ConfigError('conflicting acceptance fingerprints')
            if hashlib.sha256(self._read(path)).hexdigest() != digest:
                raise ConfigError('acceptance criteria changed; baseline mismatch')
            expected[path] = digest
        if self._acceptance and self._acceptance != expected:
            raise ConfigError('cannot replace a bound acceptance baseline')
        self._acceptance = expected

    @staticmethod
    def _validate_pointer(pointer):
        if not pointer.startswith('/') or re.search(r'~(?![01])', pointer):
            raise ConfigError('invalid JSON pointer')

    def _path(self, name):
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or not path.parts:
            raise ConfigError('path must remain within root')
        current = self.root
        for part in path.parts:
            current /= part
            if current.is_symlink():
                raise ConfigError('symlinks are not supported')
        if not current.is_file():
            raise ConfigError(f'not a regular file: {name}')
        if current.stat().st_nlink != 1:
            raise ConfigError('hardlinks are not supported')
        return current

    def _read(self, path):
        self._path(str(path.relative_to(self.root)))
        with path.open('rb') as file:
            data = file.read(self.MAX_BYTES + 1)
        if len(data) > self.MAX_BYTES:
            raise ConfigError('file exceeds size limit')
        return data

    def _evaluate(self):
        self._observed = None
        self._coverage = []
        if json.dumps(self.rules, sort_keys=True) != self._rules_snapshot:
            raise ConfigError('runtime configuration changed; create a new Harness')
        findings, changes, fingerprints, texts = [], {}, {}, {}
        def read(name):
            path = self._path(name)
            raw = self._read(path)
            digest = hashlib.sha256(raw).hexdigest()
            if path in self._acceptance and self._acceptance[path] != digest:
                raise ConfigError('acceptance criteria changed; baseline mismatch')
            if path in fingerprints and fingerprints[path] != digest:
                raise ConfigError('file changed during check')
            fingerprints[path] = digest
            return raw
        if read('realign.json') != self.config_bytes:
            raise ConfigError('configuration changed; create a new Harness')
        for rule in self.rules:
            identity = {'id': rule['id'], 'source': rule['source']}
            for field in ('pointer', 'target', 'targetPointer', 'schema', 'contract'):
                if field in rule:
                    identity[field] = rule[field]
            try:
                source = _json(read(rule['source']))
                if rule['kind'] == 'behavior':
                    contract = _json(read(rule['contract']))
                    failures = check_behavior(source, contract)
                    findings.extend({**identity, **failure} for failure in failures)
                    self._coverage.append({'id':rule['id'], 'kind':'behavior',
                                           'scenarioCount':len(contract['scenarios']), 'finiteDomain':True})
                elif rule['kind'] == 'contract':
                    schema = _json(read(rule['schema']))
                    _validate_schema(schema)
                    if not _matches(source, schema):
                        findings.append({**identity, 'code': 'CONTRACT', 'message': 'data does not satisfy declared schema'})
                elif rule['kind'] == 'equal':
                    target = _json(read(rule['target']))
                    expected_value = _pointer(source, rule['pointer'])
                    actual_value = _pointer(target, rule['targetPointer'])
                    if not _same(expected_value, actual_value):
                        findings.append({**identity, 'code': 'DRIFT', 'message': 'declared values differ',
                                         'expectedHash': self._value_hash(expected_value),
                                         'actualHash': self._value_hash(actual_value)})
                else:
                    name = rule['target']
                    raw = read(name).decode('utf-8')
                    current = texts.get(name, raw)
                    start, end = (f'<!-- realign:{rule["id"]}:{x} -->' for x in ('start', 'end'))
                    if current.count(start) != 1 or current.count(end) != 1 or current.index(start) >= current.index(end):
                        findings.append({**identity, 'code': 'MARKERS', 'message': 'missing, repeated, or reversed markers'})
                        continue
                    a, b = current.index(start) + len(start), current.index(end)
                    if '<!-- realign:' in current[a:b]:
                        findings.append({**identity, 'code': 'MARKERS', 'message': 'nested markers are unsupported'})
                        continue
                    value = _pointer(source, rule['pointer'])
                    rendered = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
                    expected = rule['template'].replace('{value}', rendered)
                    if '<!-- realign:' in expected:
                        raise ConfigError('rendered content contains reserved markers')
                    if current[a:b] != expected:
                        findings.append({**identity, 'code': 'DRIFT', 'message': 'derived block differs',
                                         'expectedHash': hashlib.sha256(expected.encode('utf-8')).hexdigest(),
                                         'actualHash': hashlib.sha256(current[a:b].encode('utf-8')).hexdigest()})
                        current = current[:a] + expected + current[b:]
                        texts[name] = current
                        encoded = current.encode('utf-8')
                        if len(encoded) > self.MAX_BYTES:
                            raise ConfigError('derived file exceeds size limit')
                        changes[self._path(name)] = encoded
            except (ValueError, OSError, KeyError, IndexError, TypeError, RecursionError) as exc:
                findings.append({**identity, 'code': 'ERROR', 'message': self._diagnostic(exc)})
        self._observed = dict(fingerprints)
        return findings, changes, fingerprints

    def observed_inputs(self):
        """Return hashes of bytes consumed by the last completed evaluation."""
        if self._observed is None:
            raise ConfigError('no completed evaluation is available for evidence')
        names = {'realign.json'}
        for rule in self.rules:
            names.update(rule[key] for key in ('source', 'target', 'schema', 'contract') if key in rule)
        result = {}
        for name in sorted(names):
            path = self._path(name)
            if path not in self._observed:
                raise ConfigError('evaluation did not observe every configured input')
            result[name] = self._observed[path]
        return result

    def validate_observed_inputs(self):
        """Refuse to attach old results to current, different input contents."""
        for name, digest in self.observed_inputs().items():
            if hashlib.sha256(self._read(self._path(name))).hexdigest() != digest:
                raise ConfigError('input changed after evaluation; evidence refused')

    @staticmethod
    def _diagnostic(exc):
        if isinstance(exc, UnicodeError):
            return 'input is not valid UTF-8'
        if isinstance(exc, (KeyError, IndexError, TypeError)):
            return 'JSON pointer cannot be resolved or input shape is invalid'
        if isinstance(exc, json.JSONDecodeError):
            return 'invalid JSON syntax'
        if isinstance(exc, OSError):
            return 'filesystem operation failed'
        if isinstance(exc, RecursionError):
            return 'input exceeds nesting limit'
        return str(exc)[:500]

    @staticmethod
    def _value_hash(value):
        canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(canonical.encode('utf-8')).hexdigest()

    def _report(self, status, findings):
        report = {'status':status, 'findings':findings}
        if self._coverage:
            report['coverage'] = [dict(row) for row in self._coverage]
        return report

    def check(self):
        try:
            findings, _, _ = self._evaluate()
            status = 'error' if any(f['code'] == 'ERROR' for f in findings) else 'drift' if findings else 'clean'
            return self._report(status, findings)
        except (ValueError, OSError, RecursionError) as exc:
            return self._report('error', [{'code':'ERROR', 'message':self._diagnostic(exc)}])

    def _replace(self, path, content):
        self._path(str(path.relative_to(self.root)))
        mode = path.stat().st_mode & 0o777
        fd, name = tempfile.mkstemp(prefix='.realign-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as file:
                file.write(content)
                file.flush()
                os.fsync(file.fileno())
            os.chmod(name, mode)
            os.replace(name, path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def _verify_lock(self):
        if self._lock_identity is None:
            raise ConfigError('repair requires an owned cooperative lock')
        try:
            current = (self.root / '.realign.lock').lstat()
        except OSError:
            raise ConfigError('repair lock disappeared') from None
        if (current.st_dev, current.st_ino) != self._lock_identity:
            raise ConfigError('repair lock ownership changed')

    def _apply(self, changes, fingerprints):
        self._verify_lock()
        for path, expected in fingerprints.items():
            if hashlib.sha256(self._read(path)).hexdigest() != expected:
                raise ConfigError('input changed before repair')
        originals = {path: self._read(path) for path in changes}
        written = []
        try:
            for path, content in changes.items():
                self._verify_lock()
                # Recheck all inputs immediately before each replacement.
                for authority, expected in fingerprints.items():
                    expected_content = changes[authority] if authority in written else None
                    digest = hashlib.sha256(expected_content).hexdigest() if expected_content is not None else expected
                    if hashlib.sha256(self._read(authority)).hexdigest() != digest:
                        raise ConfigError('input changed during repair')
                self._replace(path, content)
                written.append(path)
            if self.check()['status'] != 'clean':
                raise ConfigError('post-repair verification failed')
        except Exception:
            conflicts = False
            for path in reversed(written):
                try:
                    if self._read(path) != changes[path]:
                        conflicts = True
                        continue
                    self._replace(path, originals[path])
                except (OSError, ValueError):
                    conflicts = True
            if conflicts:
                raise ConfigError('rollback incomplete; external content was preserved')
            raise

    def fix(self):
        lock = self.root / '.realign.lock'
        descriptor = None
        inode = None
        try:
            descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            lock_stat = os.fstat(descriptor)
            inode = lock_stat.st_ino
            self._lock_identity = (lock_stat.st_dev, inode)
            findings, changes, fingerprints = self._evaluate()
            if any(f['code'] == 'ERROR' for f in findings):
                return self._report('error', findings)
            repairable = {r['id'] for r in self.rules if r['kind'] == 'derived'}
            if any(f['code'] != 'DRIFT' or f['id'] not in repairable for f in findings):
                return self._report('blocked', findings)
            if not findings:
                return self._report('clean', [])
            self._apply(changes, fingerprints)
            return self._report('repaired', findings)
        except (ValueError, OSError, RecursionError) as exc:
            return self._report('error', [{'code':'ERROR', 'message':self._diagnostic(exc)}])
        finally:
            if descriptor is not None:
                os.close(descriptor)
                self._lock_identity = None
                try:
                    if lock.lstat().st_ino == inode:
                        lock.unlink()
                except FileNotFoundError:
                    pass
