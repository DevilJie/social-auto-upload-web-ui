"""Check proposed additions without printing potentially sensitive contents.

Run after staging new files: python scripts/check_public_diff.py --base origin/master
This is a focused guard, not a replacement for reviewing the full diff.
"""
import argparse
from pathlib import PurePosixPath
import re
import subprocess
import sys


def git(*args):
    return subprocess.check_output(['git', *args]).decode('utf-8')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--base', default='HEAD')
    args = parser.parse_args()
    errors = []
    paths = git('diff', '--name-only', '-z', args.base).split('\0')
    for name in filter(None, paths):
        path = PurePosixPath(name)
        if (name.startswith(('data/', '.codex-backups/'))
                or path.suffix.lower() in ('.db', '.sqlite', '.sqlite3', '.log', '.har')
                or path.name in ('.env', 'storage_state.json')
                or 'node_modules' in path.parts or '.venv' in path.parts):
            errors.append(f'Runtime/private file in diff: {name}')
    patterns = {
        'machine-specific home/workspace path': r'(?i)[a-z]:[\\/](?:Users|Dev)[\\/]|/Users/[\w.-]+/|/home/[\w.-]+/',
        'private key': r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----',
        'GitHub credential': r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{40,})\b',
        'AWS access key': r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b',
    }
    added = '\n'.join(line[1:] for line in git('diff', '--no-ext-diff', '--unified=0', args.base).splitlines()
                      if line.startswith('+') and not line.startswith('+++'))
    for label, pattern in patterns.items():
        if re.search(pattern, added):
            errors.append(f'Potential {label} in added lines (contents withheld)')
    if errors:
        print('\n'.join(errors))
        return 1
    print('Public diff checks passed: no runtime files or known credential/path patterns.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
