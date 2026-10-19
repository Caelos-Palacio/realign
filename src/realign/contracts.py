"""Finite policy contracts: declarative observations, with no action execution."""
import copy
import hashlib
import json
import math
import re

from .schema import ConfigError, _pointer, _same

MAX_RULES = 256
MAX_SCENARIOS = 256
MAX_CONDITION_DEPTH = 32
MAX_NODES = 8192
MAX_DIFFERENCES = 16
MAX_MUTATIONS = 128
_ID = re.compile(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}\Z')


def _shape(value, fields, label):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ConfigError(f'invalid {label} fields')


def _version(value):
    if type(value) is not int or value != 1:
        raise ConfigError('unsupported behavior version')


def _identity(value):
    if not isinstance(value, str) or not _ID.fullmatch(value):
        raise ConfigError('invalid behavior identifier')


def _bounded_json(value):
    """Bound work even for Python callers bypassing the file-size guard."""
    stack, count = [(value, 0)], 0
    while stack:
        node, depth = stack.pop()
        count += 1
        if count > MAX_NODES or depth > 64:
            raise ConfigError('behavior document exceeds structural limit')
        if node is None or type(node) in (bool, int):
            continue
        if isinstance(node, str):
            if len(node) > 16384:
                raise ConfigError('behavior string exceeds limit')
            try:
                node.encode('utf-8')
            except UnicodeError:
                raise ConfigError('behavior strings must be valid UTF-8') from None
        elif type(node) is float:
            if not math.isfinite(node):
                raise ConfigError('behavior numbers must be finite')
        elif isinstance(node, list):
            stack.extend((child, depth + 1) for child in node)
        elif isinstance(node, dict):
            if any(not isinstance(k, str) for k in node):
                raise ConfigError('behavior object keys must be strings')
            stack.extend((child, depth + 1) for pair in node.items() for child in pair)
        else:
            raise ConfigError('behavior document must contain only JSON data')


def _json_pointer(pointer, allow_root=True):
    if not isinstance(pointer, str) or len(pointer) > 1024 or (not allow_root and not pointer):
        raise ConfigError('invalid behavior JSON pointer')
    if pointer and not pointer.startswith('/') or re.search(r'~(?![01])', pointer):
        raise ConfigError('invalid behavior JSON pointer')


def _outcome(value):
    _shape(value, ('decision', 'trace', 'effects'), 'outcome')
    if not isinstance(value['decision'], str) or value['decision'] not in ('allow', 'deny', 'clarify'):
        raise ConfigError('unsupported behavior decision')
    if not isinstance(value['trace'], list) or len(value['trace']) > 128 or any(not isinstance(x, str) for x in value['trace']):
        raise ConfigError('trace must be a bounded list of strings')
    if not isinstance(value['effects'], list) or len(value['effects']) > 128 or any(not isinstance(x, dict) for x in value['effects']):
        raise ConfigError('effects must be a bounded list of JSON objects')


def _condition(condition, depth=0):
    if depth > MAX_CONDITION_DEPTH or not isinstance(condition, dict):
        raise ConfigError('invalid condition or condition depth')
    op = condition.get('op')
    if not isinstance(op, str):
        raise ConfigError('invalid condition operator')
    if op in ('all', 'any'):
        _shape(condition, ('op', 'args'), 'logical condition')
        args = condition['args']
        if not isinstance(args, list) or not args or len(args) > 128:
            raise ConfigError('logical args must be a nonempty bounded list')
        for child in args:
            _condition(child, depth + 1)
    elif op == 'not':
        _shape(condition, ('op', 'arg'), 'negation')
        _condition(condition['arg'], depth + 1)
    elif op == 'exists':
        _shape(condition, ('op', 'pointer'), 'existence condition')
        _json_pointer(condition['pointer'])
    elif op in ('eq', 'ne', 'gt', 'gte', 'lt', 'lte'):
        _shape(condition, ('op', 'pointer', 'value'), 'comparison')
        _json_pointer(condition['pointer'])
        if op in ('gt', 'gte', 'lt', 'lte') and type(condition['value']) not in (int, float):
            raise ConfigError('ordered comparison requires a numeric value')
    else:
        raise ConfigError('unsupported condition operator')


def validate_policy(policy):
    _bounded_json(policy)
    _shape(policy, ('version', 'rules', 'default'), 'policy')
    _version(policy['version'])
    rules = policy['rules']
    if not isinstance(rules, list) or len(rules) > MAX_RULES:
        raise ConfigError('policy rules must be a bounded list')
    ids = set()
    for rule in rules:
        _shape(rule, ('id', 'when', 'outcome'), 'policy rule')
        _identity(rule['id'])
        if rule['id'] in ids:
            raise ConfigError('duplicate policy rule id')
        ids.add(rule['id'])
        _condition(rule['when'])
        _outcome(rule['outcome'])
    _outcome(policy['default'])


def validate_contract(contract):
    _bounded_json(contract)
    _shape(contract, ('version', 'scenarios'), 'behavior contract')
    _version(contract['version'])
    scenarios = contract['scenarios']
    if not isinstance(scenarios, list) or not scenarios or len(scenarios) > MAX_SCENARIOS:
        raise ConfigError('scenarios must be a nonempty bounded list')
    ids = set()
    for scenario in scenarios:
        _shape(scenario, ('id', 'requirementId', 'given', 'expected'), 'scenario')
        _identity(scenario['id'])
        _identity(scenario['requirementId'])
        if scenario['id'] in ids:
            raise ConfigError('duplicate scenario id')
        ids.add(scenario['id'])
        if not isinstance(scenario['given'], dict):
            raise ConfigError('scenario given must be a JSON object')
        _outcome(scenario['expected'])


def _test(condition, given):
    op = condition['op']
    if op == 'all':
        return all(_test(child, given) for child in condition['args'])
    if op == 'any':
        return any(_test(child, given) for child in condition['args'])
    if op == 'not':
        return not _test(condition['arg'], given)
    try:
        value = _pointer(given, condition['pointer'])
    except (KeyError, IndexError, TypeError, ConfigError):
        return False
    if op == 'exists':
        return True
    expected = condition['value']
    if op == 'eq':
        return _same(value, expected)
    if op == 'ne':
        return not _same(value, expected)
    if type(value) not in (int, float):
        return False
    if op == 'gt':
        return value > expected
    if op == 'gte':
        return value >= expected
    if op == 'lt':
        return value < expected
    return value <= expected


def _evaluate(policy, given):
    for rule in policy['rules']:
        if _test(rule['when'], given):
            return rule['outcome']
    return policy['default']


def evaluate_policy(policy, given):
    validate_policy(policy)
    _bounded_json(given)
    if not isinstance(given, dict):
        raise ConfigError('policy input must be a JSON object')
    return copy.deepcopy(_evaluate(policy, given))


def _hash(value):
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(encoded).hexdigest()


def _differences(expected, actual):
    # Report only fixed outcome fields and array positions, never data keys/values.
    differences = []
    for field in ('decision', 'trace', 'effects'):
        left, right = expected[field], actual[field]
        if _same(left, right):
            continue
        if field == 'decision' or len(left) != len(right):
            differences.append('/' + field)
        else:
            for index, (a, b) in enumerate(zip(left, right)):
                if not _same(a, b):
                    differences.append(f'/{field}/{index}')
                    if len(differences) >= MAX_DIFFERENCES:
                        return differences
    return differences[:MAX_DIFFERENCES]


def _check(policy, contract):
    findings = []
    for scenario in contract['scenarios']:
        actual = _evaluate(policy, scenario['given'])
        expected = scenario['expected']
        if not _same(actual, expected):
            findings.append({'code':'BEHAVIOR', 'scenarioId':scenario['id'],
                             'requirementId':scenario['requirementId'],
                             'message':'finite behavior scenario differs',
                             'expectedHash':_hash(expected), 'actualHash':_hash(actual),
                             'differences':_differences(expected, actual)})
    return findings


def check_behavior(policy, contract):
    validate_policy(policy)
    validate_contract(contract)
    return _check(policy, contract)


def _replace_value(policy, pointer, value):
    _json_pointer(pointer, allow_root=False)
    # Resolve original first: mutants cannot add fields or append array entries.
    try:
        _pointer(policy, pointer)
        parent_pointer, _, leaf = pointer.rpartition('/')
        parent = _pointer(policy, parent_pointer)
        leaf = leaf.replace('~1', '/').replace('~0', '~')
        if isinstance(parent, list):
            parent[int(leaf)] = copy.deepcopy(value)
        elif isinstance(parent, dict):
            parent[leaf] = copy.deepcopy(value)
        else:
            raise ConfigError('mutation parent must be a container')
    except (KeyError, IndexError, TypeError, ValueError):
        raise ConfigError('mutation must replace an existing policy value') from None


def evaluate_mutations(policy, contract, mutations):
    validate_policy(policy)
    validate_contract(contract)
    if _check(policy, contract):
        raise ConfigError('mutation baseline must satisfy every declared scenario')
    _bounded_json(mutations)
    _shape(mutations, ('version', 'mutations'), 'mutation corpus')
    _version(mutations['version'])
    entries = mutations['mutations']
    if not isinstance(entries, list) or not entries or len(entries) > MAX_MUTATIONS:
        raise ConfigError('mutations must be a nonempty bounded list')
    ids = set()
    # Validate the whole corpus before interpreting any mutant.
    for entry in entries:
        _shape(entry, ('id', 'pointer', 'value'), 'mutation')
        _identity(entry['id'])
        _json_pointer(entry['pointer'], allow_root=False)
        if entry['id'] in ids:
            raise ConfigError('duplicate mutation id')
        ids.add(entry['id'])
    results = []
    for entry in entries:
        mutant = copy.deepcopy(policy)
        try:
            _replace_value(mutant, entry['pointer'], entry['value'])
            validate_policy(mutant)
            findings = _check(mutant, contract)
            results.append({'id':entry['id'], 'status':'killed' if findings else 'survived', 'findings':findings})
        except ConfigError:
            results.append({'id':entry['id'], 'status':'invalid', 'findings':[]})
    return {'status':'complete', 'baseline':'clean', 'finiteDomain':True, 'mutations':results}
