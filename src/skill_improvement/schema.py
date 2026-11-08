"""Stdlib validator for the small JSON Schema keyword set the #106 contract uses."""
import json
import re

SUPPORTED = {'$schema', '$id', 'title', 'description', '$defs', '$ref', 'type', 'const', 'enum',
             'required', 'properties', 'additionalProperties', 'items', 'minItems', 'maxItems',
             'uniqueItems', 'pattern', 'minLength', 'maxLength', 'minimum', 'maximum', 'oneOf'}
TYPES = {'object': dict, 'array': list, 'string': str, 'integer': int, 'boolean': bool,
         'null': type(None)}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()


def _same(left, right):
    return type(left) is type(right) and left == right


def errors(value, schema, root=None, path='$'):
    """Return a list of violations; an unsupported keyword is a contract error, not a pass."""
    root = schema if root is None else root
    unknown = set(schema) - SUPPORTED
    if unknown:
        raise ValueError(f'unsupported schema keyword at {path}: {sorted(unknown)}')
    if '$ref' in schema:
        return errors(value, root['$defs'][schema['$ref'].removeprefix('#/$defs/')], root, path)
    if 'oneOf' in schema:
        matched = sum(not errors(value, branch, root, path) for branch in schema['oneOf'])
        return [] if matched == 1 else [f'{path}: oneOf matched {matched}']
    found = []
    kind = schema.get('type')
    if kind and type(value) is not TYPES[kind]:
        return [f'{path}: expected {kind}']
    if 'const' in schema and not _same(value, schema['const']):
        found.append(f'{path}: const')
    if 'enum' in schema and not any(_same(value, item) for item in schema['enum']):
        found.append(f'{path}: enum')
    if kind == 'object':
        if schema.get('additionalProperties') is not False:
            raise ValueError(f'object schema must close additionalProperties at {path}')
        properties = schema.get('properties', {})
        missing = set(schema.get('required', [])) - set(value)
        extra = set(value) - set(properties)
        found += [f'{path}: missing {sorted(missing)}'] if missing else []
        found += [f'{path}: unexpected {sorted(extra)}'] if extra else []
        for name, item in value.items():
            if name in properties:
                found += errors(item, properties[name], root, f'{path}.{name}')
    if kind == 'array':
        if not schema.get('minItems', 0) <= len(value) <= schema.get('maxItems', len(value)):
            found.append(f'{path}: item count')
        if schema.get('uniqueItems') and len({canonical(item) for item in value}) != len(value):
            found.append(f'{path}: duplicate items')
        for index, item in enumerate(value):
            found += errors(item, schema['items'], root, f'{path}[{index}]')
    if kind == 'string':
        if 'pattern' in schema and not re.fullmatch(schema['pattern'], value):
            found.append(f'{path}: pattern')
        if not schema.get('minLength', 0) <= len(value) <= schema.get('maxLength', len(value)):
            found.append(f'{path}: length')
    if kind == 'integer' and not schema.get('minimum', value) <= value <= schema.get('maximum', value):
        found.append(f'{path}: range')
    return found
