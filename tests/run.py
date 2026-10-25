#!/usr/bin/env python3
"""Run clean-checkout tests; optional private-source integration must be explicit."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


def cases(suite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from cases(item)
        else:
            yield item


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--integration-source', type=Path)
    parser.add_argument('--require-integration', action='store_true')
    parser.add_argument('--require-system-tests', action='store_true')
    args = parser.parse_args()
    sys.dont_write_bytecode = True
    os.environ['PYTHONDONTWRITEBYTECODE'] = '1'
    source = args.integration_source or (Path(os.environ['T3_PLANNER_EXECUTOR_TEST_SOURCE']) if os.environ.get('T3_PLANNER_EXECUTOR_TEST_SOURCE') else None)
    include = source is not None or args.require_integration
    if include:
        if source is None or not source.is_dir():
            parser.error('private integration requires --integration-source pointing to the clean pinned Planner-Executor checkout')
        expected = json.loads((ROOT / 'config/features.json').read_text())['install-t3-planner-executor.sh']['pin']
        revision = subprocess.run(['git', '-C', str(source), 'rev-parse', 'HEAD'], capture_output=True, text=True)
        dirty = subprocess.run(['git', '-C', str(source), 'status', '--porcelain', '--untracked-files=all'], capture_output=True, text=True)
        if revision.returncode or dirty.returncode or revision.stdout.strip() != expected or dirty.stdout.strip():
            parser.error('integration source must be clean and at the exact registry pin ' + expected)
        os.environ['T3_PLANNER_EXECUTOR_TEST_SOURCE'] = str(source.resolve())
    collected = []
    excluded = 0
    for directory in ('tests', 'steam', 'github', 't3', 'gaming', 'gaming/denuvowo'):
        suite = unittest.TestLoader().discover(str(ROOT / directory), pattern='test_*.py')
        for case in cases(suite):
            if case.__class__.__module__ == 'test_t3_planner_executor' and not include:
                excluded += 1
            else:
                collected.append(case)
    if excluded:
        print(f'Explicitly not selected: {excluded} private-source integration tests. Use --require-integration --integration-source PATH for release acceptance.', flush=True)
    result = unittest.TextTestRunner(verbosity=1).run(unittest.TestSuite(collected))
    if args.require_system_tests and result.skipped:
        print('Required system tests were skipped; install the documented Lutris/Lua dependencies.', file=sys.stderr)
        return 1
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
