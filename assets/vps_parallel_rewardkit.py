#!/usr/bin/env python3
"""Bounded, isolated individual AgentJudge calls for the approved VPS runtime.

The pinned RewardKit still builds prompts, calls Claude, parses scores and
aggregates in original criterion order. Only its individual-call scheduler and
Claude's filesystem view are adapted; this file is outside delivered task files.
"""
from __future__ import annotations

import asyncio
import contextvars
import importlib.metadata
import json
import os
from pathlib import Path
import runpy
import shutil
import tempfile
import time

SCOPE = contextvars.ContextVar('rl01_judge_scope', default=None)


def sandbox_command(command: list[str], workspace: Path, private: Path) -> list[str]:
    """Provide private scratch/home/tmp while sharing immutable input bytes."""
    if not shutil.which('bwrap'):
        raise RuntimeError('Parallel Judge requires bubblewrap; cannot silently use a shared workspace')
    app, home, config = private / 'app', private / 'home', private / 'config'
    for path in (app, home, config):
        path.mkdir(mode=0o700)
    original_config = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(Path.home() / '.claude')))
    settings = original_config / 'settings.json'
    if settings.is_file():
        shutil.copy2(settings, config / 'settings.json')
    # Copy only configuration, never earlier sessions, history or credentials.
    metadata = Path.home() / '.claude.json'
    if metadata.is_file():
        value = json.loads(metadata.read_text())
        selected = {key: value[key] for key in ('hasCompletedOnboarding', 'theme', 'customApiKeyResponses')
                    if key in value}
        (home / '.claude.json').write_text(json.dumps(selected))
    args = ['bwrap', '--die-with-parent', '--new-session', '--unshare-pid',
            '--ro-bind', '/', '/', '--proc', '/proc', '--dev', '/dev',
            '--tmpfs', '/tmp', '--tmpfs', '/run', '--bind', str(home), str(Path.home()),
            '--bind', str(config), str(Path.home() / '.claude'),
            '--bind', str(app), str(workspace)]
    for child in sorted(workspace.iterdir()):
        # Preserve absolute and relative paths without duplicating large inputs.
        target = app / child.name
        if child.is_dir():
            target.mkdir()
        else:
            target.touch()
        args += ['--ro-bind', str(child), str(workspace / child.name)]
    args += ['--setenv', 'CLAUDE_CONFIG_DIR', str(Path.home() / '.claude'),
             '--setenv', 'TMPDIR', '/tmp', '--setenv', 'TMP', '/tmp', '--setenv', 'TEMP', '/tmp',
             '--setenv', 'XDG_CONFIG_HOME', str(Path.home() / '.config'),
             '--setenv', 'XDG_CACHE_HOME', str(Path.home() / '.cache'),
             '--cap-drop', 'ALL', '--chdir', str(workspace), '--', *command]
    return args


def install(workers: int, audit: Path):
    if importlib.metadata.version('harbor-rewardkit') != '0.1.7':
        raise RuntimeError('Parallel adapter is validated only for harbor-rewardkit 0.1.7')
    if not 1 <= workers <= 2:
        raise ValueError('This 2 GiB runtime supports one or two criterion workers')
    import rewardkit.agents as agents
    import rewardkit.judges as judges
    original_get_agent = agents.get_agent
    original_spawn = asyncio.create_subprocess_exec
    original_call = judges._arun_agent_call
    original_individual = judges._arun_agent_individual
    semaphore = asyncio.Semaphore(workers)

    def get_agent(name):
        backend = original_get_agent(name)
        scope = SCOPE.get()
        if scope is not None:
            if name != 'claude-code':
                raise ValueError('Parallel adapter supports the prescribed Claude Code AgentJudge only')
            build = backend.build_command
            def scoped_build(*args, **kwargs):
                return sandbox_command(build(*args, **kwargs), scope['workspace'], scope['private'])
            backend.build_command = scoped_build
        return backend

    async def spawn(*args, **kwargs):
        process = await original_spawn(*args, **kwargs)
        scope = SCOPE.get()
        if scope is not None:
            scope['processes'].append(process)
        return process

    async def individual(judge, criteria, weights, workspace, system_prompt):
        if judge.cwd is not None and Path(judge.cwd).resolve() != Path(workspace).resolve():
            raise ValueError('Custom Judge cwd needs explicit isolation support')
        if judge.mcp_servers:
            raise ValueError('MCP Judge is not covered by this isolated parallel adapter')
        results = [None] * len(criteria)
        audit.parent.mkdir(parents=True, exist_ok=True)

        async def score(index, criterion):
            async with semaphore:
                with tempfile.TemporaryDirectory(prefix='rl01-criterion-') as temporary:
                    private = Path(temporary)
                    scope = {'private': private, 'workspace': Path(workspace).resolve(), 'processes': []}
                    token = SCOPE.set(scope)
                    record = {'id': criterion.id, 'name': criterion.name, 'started': time.time(),
                              'criterion_workers': workers, 'isolation': 'bubblewrap', 'status': 'FAILED'}
                    try:
                        results[index] = await original_call(
                            judge, [criterion], [weights[index]] if weights else None, workspace, system_prompt)
                        record['status'] = 'COMPLETED'
                    finally:
                        for process in scope['processes']:
                            if process.returncode is None:
                                process.kill()
                                await process.communicate()
                        SCOPE.reset(token)
                        record['ended'] = time.time()
                        with audit.open('a') as handle:
                            handle.write(json.dumps(record, ensure_ascii=False) + '\n')

        async with asyncio.TaskGroup() as group:
            for index, criterion in enumerate(criteria):
                group.create_task(score(index, criterion))
        scores, outputs, warnings = [], [], []
        for criterion, (scored, raw, warned) in zip(criteria, results):
            scores.extend(scored)
            outputs.append(f'--- {criterion.name} ---\n{raw}')
            warnings.extend(warned)
        return scores, '\n\n'.join(outputs), warnings

    agents.get_agent = get_agent
    asyncio.create_subprocess_exec = spawn
    judges._arun_agent_individual = individual
    return lambda: (setattr(agents, 'get_agent', original_get_agent),
                    setattr(asyncio, 'create_subprocess_exec', original_spawn),
                    setattr(judges, '_arun_agent_individual', original_individual))


def main():
    workers = int(os.environ.get('RL01_CRITERION_WORKERS', '2'))
    if workers == 1:
        runpy.run_module('rewardkit', run_name='__main__')
        return
    restore = install(workers, Path('/logs/verifier/criterion-runtime.jsonl'))
    try:
        runpy.run_module('rewardkit', run_name='__main__')
    finally:
        restore()


if __name__ == '__main__':
    main()
