"""Intentionally incomplete PUBLIC baseline; evaluate only inside fixed Docker."""
import json
import re
import sys
from helpers import accumulate

try:
    value = json.load(sys.stdin)
    if type(value) is not dict or set(value) != {'events'} or type(value['events']) is not list:
        raise ValueError()
    for event in value['events']:
        if (type(event) is not dict or set(event) != {'category', 'status'}
                or type(event['category']) is not str or not re.fullmatch('[a-z0-9]{1,16}', event['category'])
                or event['status'] not in ('ok', 'failed')):
            raise ValueError()
    print(json.dumps({'counts': accumulate(value['events'])}))
except (ValueError, KeyError, TypeError):
    print('{"error":"INVALID_INPUT"}')
    sys.exit(2)
