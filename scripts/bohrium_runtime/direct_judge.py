#!/usr/bin/env python3
"""Use RewardKit's original scoring with isolated, two-at-a-time CLI calls."""
from __future__ import annotations

import argparse
import asyncio
import contextvars
import importlib.metadata
import json
import os
from pathlib import Path
import time

from direct_isolation import PREFIX, Stage

SCOPE = contextvars.ContextVar('criterion_scope', default=None)


def install(tests: Path, audit: Path, *, workers=2, upstream=None, upstream_token=None):
    if importlib.metadata.version('harbor-rewardkit') != '0.1.7':
        raise RuntimeError('this adapter requires RewardKit 0.1.7')
    if workers not in (1, 2):
        raise ValueError('supported criterion concurrency is 1 or 2')
    import rewardkit.judges as judges
    original_spawn = asyncio.create_subprocess_exec
    original_individual = judges._arun_agent_individual
    original_call = judges._arun_agent_call
    semaphore = asyncio.Semaphore(workers)
    records = []

    async def spawn(*argv, **kwargs):
        scope = SCOPE.get()
        if scope is None:
            return await original_spawn(*argv, **kwargs)
        stage = Stage('judge-'+str(scope['criterion'].id or scope['criterion'].name),
                      scope['workspace'], tests=tests, model=scope['model'],
                      upstream=upstream, upstream_token=upstream_token, effort=None)
        scope['stages'].append(stage)
        # Preserve RewardKit's prompt/schema/model; add only runtime controls.
        command = list(argv) + ['--permission-mode', 'bypassPermissions', '--tools', 'Bash,Read,Glob,Grep', '--max-turns', '100',
                                '--setting-sources', '', '--no-session-persistence']
        kwargs.update(cwd=None, env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'},
                      user=stage.uid, group=stage.uid, extra_groups=[], start_new_session=True)
        process = await original_spawn(*stage.command(command, aliases=(scope['workspace'],)), **kwargs)
        stage.monitor(process)
        communicate = process.communicate
        async def logged_communicate(*args, **kw):
            stdout, stderr = await communicate(*args, **kw)
            (stage.root/'stdout.txt').write_bytes(stdout or b'')
            (stage.root/'stderr.txt').write_bytes(stderr or b'')
            return stdout, stderr
        process.communicate = logged_communicate
        return process

    async def individual(judge, criteria, weights, workspace, system_prompt):
        if judge.agent != 'claude-code' or judge.mcp_servers:
            raise ValueError('only the prescribed Claude Code judge without MCP is supported')
        if not judge.model:
            raise ValueError('judge model must be explicit')
        result = [None] * len(criteria)
        async def score(index, criterion):
            async with semaphore:
                scope = {'criterion': criterion, 'workspace': Path(workspace).resolve(),
                         'model': judge.model, 'stages': []}
                token = SCOPE.set(scope)
                record = {'id': criterion.id, 'name': criterion.name, 'started': time.time(),
                          'workers': workers, 'status': 'FAILED', 'stages': []}
                try:
                    result[index] = await original_call(judge, [criterion],
                        [weights[index]] if weights else None, workspace, system_prompt)
                    scores, raw, warnings = result[index]
                    if warnings or any(value.error is not None for value in scores):
                        raise RuntimeError('criterion unavailable: '+str(warnings))
                    record['status'] = 'COMPLETED'
                finally:
                    SCOPE.reset(token)
                    for stage in scope['stages']:
                        receipt = await asyncio.to_thread(stage.close)
                        record['stages'].append(receipt)
                    record['ended'] = time.time()
                    records.append(record)
                    with audit.open('a') as handle:
                        handle.write(json.dumps(record, ensure_ascii=False)+'\n')
        async with asyncio.TaskGroup() as group:
            for index, criterion in enumerate(criteria):
                group.create_task(score(index, criterion))
        scores, outputs, warnings = [], [], []
        for criterion, (scored, raw, warned) in zip(criteria, result):
            scores.extend(scored)
            outputs.append(f'--- {criterion.name} ---\n{raw}')
            warnings.extend(warned)
        return scores, '\n\n'.join(outputs), warnings

    asyncio.create_subprocess_exec = spawn
    judges._arun_agent_individual = individual
    def restore():
        asyncio.create_subprocess_exec = original_spawn
        judges._arun_agent_individual = original_individual
    return restore, records


def grade(tests: Path, app: Path, output: Path, *, workers=2, upstream=None, upstream_token=None):
    from rewardkit.runner import run
    output.parent.mkdir(parents=True, exist_ok=True)
    os.environ['PATH'] = f'{PREFIX}/bin:{PREFIX}/venv/bin:'+os.environ.get('PATH', '')
    restore, records = install(tests, output.parent/'criterion-runtime.jsonl',
                              workers=workers, upstream=upstream, upstream_token=upstream_token)
    try:
        scores = run(tests, workspace=app, output=output,
                     max_concurrent_programmatic=1, max_concurrent_llm=1, max_concurrent_agent=1)
        if not records or any(record['status'] != 'COMPLETED' for record in records):
            raise RuntimeError('not all criteria completed')
        events = [(record['started'], 1) for record in records] + [(record['ended'], -1) for record in records]
        active = peak = 0
        for _, delta in sorted(events):
            active += delta
            peak = max(peak, active)
        receipt = {'status': 'VALID', 'scores': scores, 'criteria_counted': len(records),
                   'criterion_concurrency_peak': peak, 'workers': workers,
                   'rewardkit_version': importlib.metadata.version('harbor-rewardkit')}
        (output.parent/'grade-receipt.json').write_text(json.dumps(receipt, indent=2))
        return receipt
    except BaseException as exc:
        (output.parent/'grade-receipt.json').write_text(json.dumps({
            'status': 'VERIFIER_UNAVAILABLE', 'error_type': type(exc).__name__,
            'criteria_counted': sum(record['status']=='COMPLETED' for record in records)}, indent=2))
        raise
    finally:
        restore()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--tests', type=Path, required=True)
    parser.add_argument('--app', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=2)
    args = parser.parse_args()
    print(json.dumps(grade(args.tests, args.app, args.output, workers=args.workers), indent=2))


if __name__ == '__main__':
    main()
