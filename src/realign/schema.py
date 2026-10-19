"""Strict bounded JSON primitives and the supported schema subset."""
from decimal import Decimal
import json
import math
import re


class ConfigError(ValueError):
    pass


def _pairs(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ConfigError('duplicate JSON key')
        out[key] = value
    return out


def _finite_float(value):
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ConfigError('non-finite JSON number')
    if Decimal(str(parsed)) != Decimal(value):
        raise ConfigError('JSON number loses decimal precision')
    return parsed


def _json(raw):
    try:
        return json.loads(raw, object_pairs_hook=_pairs, parse_float=_finite_float,
                          parse_constant=lambda x: (_ for _ in ()).throw(ConfigError(f'invalid number {x}')))
    except RecursionError:
        raise ConfigError('input exceeds JSON decoder nesting limit') from None


def _pointer(value, pointer):
    if not isinstance(pointer, str) or (pointer and not pointer.startswith('/')):
        raise ConfigError('invalid JSON pointer')
    for part in pointer.split('/')[1:] if pointer else []:
        if re.search(r'~(?![01])', part):
            raise ConfigError('invalid JSON pointer escape')
        part = part.replace('~1', '/').replace('~0', '~')
        if isinstance(value, list):
            if not re.fullmatch(r'0|[1-9][0-9]*', part):
                raise ConfigError('invalid array index')
            value = value[int(part)]
        else:
            value = value[part]
    return value


_TYPES = {'object': lambda x: isinstance(x, dict), 'array': lambda x: isinstance(x, list),
          'string': lambda x: isinstance(x, str), 'integer': lambda x: type(x) is int,
          'number': lambda x: type(x) is int or (type(x) is float and math.isfinite(x)),
          'boolean': lambda x: type(x) is bool, 'null': lambda x: x is None}


def _validate_schema(schema, depth=0):
    if depth > 64:
        raise ConfigError('schema exceeds nesting limit')
    allowed = {'type', 'required', 'properties', 'additionalProperties', 'enum', 'items',
               'minimum', 'maximum', 'minLength', 'maxLength'}
    if not isinstance(schema, dict) or set(schema) - allowed:
        raise ConfigError('unsupported schema keyword or schema shape')
    if 'type' in schema and (not isinstance(schema['type'], str) or schema['type'] not in _TYPES):
        raise ConfigError('unsupported schema type')
    if 'required' in schema and (not isinstance(schema['required'], list) or
            any(not isinstance(x, str) for x in schema['required'])):
        raise ConfigError('required must be an array of names')
    if 'properties' in schema:
        if not isinstance(schema['properties'], dict):
            raise ConfigError('properties must be an object')
        for child in schema['properties'].values():
            _validate_schema(child, depth + 1)
    if 'additionalProperties' in schema and type(schema['additionalProperties']) is not bool:
        raise ConfigError('additionalProperties must be boolean')
    if 'enum' in schema and (not isinstance(schema['enum'], list) or not schema['enum']):
        raise ConfigError('enum must be nonempty array')
    if 'items' in schema:
        _validate_schema(schema['items'], depth + 1)
    for name in ('minimum', 'maximum'):
        if name in schema and type(schema[name]) not in (int, float):
            raise ConfigError(f'{name} must be numeric')
    for name in ('minLength', 'maxLength'):
        if name in schema and (type(schema[name]) is not int or schema[name] < 0):
            raise ConfigError(f'{name} must be nonnegative integer')


def _same(a, b):
    if type(a) is not type(b):
        return False
    if isinstance(a, dict):
        return a.keys() == b.keys() and all(_same(v, b[k]) for k, v in a.items())
    if isinstance(a, list):
        return len(a) == len(b) and all(_same(x, y) for x, y in zip(a, b))
    return a == b


def _matches(value, schema):
    if 'type' in schema and not _TYPES[schema['type']](value):
        return False
    if 'enum' in schema and not any(_same(value, x) for x in schema['enum']):
        return False
    if isinstance(value, dict):
        props = schema.get('properties', {})
        if any(k not in value for k in schema.get('required', [])):
            return False
        if schema.get('additionalProperties') is False and set(value) - set(props):
            return False
        if any(not _matches(value[k], s) for k, s in props.items() if k in value):
            return False
    if isinstance(value, list) and 'items' in schema and not all(_matches(x, schema['items']) for x in value):
        return False
    if type(value) in (int, float):
        if value < schema.get('minimum', -math.inf) or value > schema.get('maximum', math.inf):
            return False
    if isinstance(value, str) and not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', math.inf):
        return False
    return True
