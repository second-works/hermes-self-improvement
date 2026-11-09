"""Shared command-line helpers for the skill improvement scripts."""
import argparse
import json
import re
import sys


class QuietParser(argparse.ArgumentParser):
    """argparse errors normally repeat the offending value; this one never echoes input values."""

    def error(self, message):
        # Never rebuild the message from input: only text taken from this parser's own definitions.
        detail = 'invalid arguments; see --help'
        named = re.match(r'argument ([^:]+):', message)
        if message.startswith('the following arguments are required:'):
            required = message.split(':', 1)[1].split(',')
            known = {option for action in self._actions for option in action.option_strings}
            names = [item.strip() for item in required if item.strip() in known]
            detail = 'missing required arguments: ' + ', '.join(names) if names else detail
        elif named and named.group(1) in {'/'.join(action.option_strings) for action in self._actions}:
            detail = f'invalid value for {named.group(1)}; see --help'
        print(json.dumps({'error': 'ARGUMENTS_INVALID', 'detail': detail}, ensure_ascii=False), file=sys.stderr)
        sys.exit(2)
