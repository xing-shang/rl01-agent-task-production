"""Criterion scheduling regressions. Providers are never contacted."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest import mock

location = Path(__file__).parents[1] / 'assets/vps_parallel_rewardkit.py'
spec = importlib.util.spec_from_file_location('rl01_parallel_test', location)
driver = importlib.util.module_from_spec(spec)
spec.loader.exec_module(driver)


@unittest.skipUnless(importlib.util.find_spec('rewardkit'), 'Pinned RewardKit is tested on the VPS')
class ParallelTests(unittest.TestCase):
    def exercise(self, call, count=5):
        import rewardkit.judges as judges
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'app').mkdir()
            judge = SimpleNamespace(cwd=None, mcp_servers=[])
            criteria = [SimpleNamespace(id=f'R{i}', name=f'R{i}') for i in range(count)]
            with mock.patch.object(judges, '_arun_agent_call', side_effect=call):
                restore = driver.install(2, root / 'audit.jsonl')
                try:
                    result = asyncio.run(judges._arun_agent_individual(judge, criteria,
                                                list(range(1, count + 1)), root / 'app', 'same prompt'))
                finally:
                    restore()
            records = [json.loads(line) for line in (root / 'audit.jsonl').read_text().splitlines()]
            return result, records

    def test_out_of_order_finishes_preserve_ids_weights_and_original_order(self):
        stats = {'active': 0, 'peak': 0, 'private': set(), 'seen': []}
        async def call(judge, criteria, weights, workspace, prompt):
            scope = driver.SCOPE.get()
            stats['private'].add(str(scope['private']))
            stats['active'] += 1
            stats['peak'] = max(stats['peak'], stats['active'])
            index = int(criteria[0].id[1:])
            await asyncio.sleep(0.04 if index % 2 == 0 else 0.01)
            stats['active'] -= 1
            stats['seen'].append(index)
            return [{'id': criteria[0].id, 'weight': weights[0]}], f'output {index}', []
        (scores, output, warnings), audit = self.exercise(call)
        self.assertEqual(stats['peak'], 2)
        self.assertNotEqual(stats['seen'], sorted(stats['seen']))
        self.assertEqual(len(stats['private']), 5)
        self.assertEqual([score['id'] for score in scores], [f'R{i}' for i in range(5)])
        self.assertEqual([score['weight'] for score in scores], list(range(1, 6)))
        self.assertEqual(output.split('\n\n'), [f'--- R{i} ---\noutput {i}' for i in range(5)])
        self.assertEqual(warnings, [])
        self.assertEqual({record['status'] for record in audit}, {'COMPLETED'})
        self.assertTrue(all(not Path(path).exists() for path in stats['private']))

    def test_one_failure_cancels_and_reaps_live_sibling_process(self):
        children = []
        async def call(judge, criteria, weights, workspace, prompt):
            if criteria[0].id == 'R0':
                child = await asyncio.create_subprocess_exec(
                    sys.executable, '-c', 'import time; time.sleep(30)', stdout=asyncio.subprocess.PIPE)
                children.append(child)
                await child.wait()
            else:
                while not children:
                    await asyncio.sleep(0)
                raise ValueError('Synthetic criterion failure')
        started = time.monotonic()
        with self.assertRaises(ExceptionGroup):
            self.exercise(call, count=2)
        self.assertLess(time.monotonic() - started, 3)
        self.assertEqual(len(children), 1)
        self.assertIsNotNone(children[0].returncode)

    def test_multiple_reward_groups_share_the_same_two_process_budget(self):
        import rewardkit.judges as judges
        stats = {'active': 0, 'peak': 0}
        async def call(judge, criteria, weights, workspace, prompt):
            stats['active'] += 1
            stats['peak'] = max(stats['peak'], stats['active'])
            await asyncio.sleep(0.02)
            stats['active'] -= 1
            return [criteria[0].id], 'same response', []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            judge = SimpleNamespace(cwd=None, mcp_servers=[])
            groups = [[SimpleNamespace(id=f'R{group}-{i}', name=f'R{group}-{i}') for i in range(3)]
                      for group in range(2)]
            with mock.patch.object(judges, '_arun_agent_call', side_effect=call):
                restore = driver.install(2, root / 'audit.jsonl')
                async def evaluate():
                    return await asyncio.gather(*(judges._arun_agent_individual(judge, criteria,
                                                [1] * 3, root, 'same prompt') for criteria in groups))
                try:
                    results = asyncio.run(evaluate())
                finally:
                    restore()
        self.assertEqual(stats['peak'], 2)
        self.assertEqual([result[0] for result in results], [[c.id for c in group] for group in groups])

    def test_claude_prompt_and_schema_are_preserved_in_private_filesystem(self):
        import rewardkit.agents as agents
        original = agents.get_agent('claude-code').build_command('exact prompt', {'type': 'object'})
        commands = []
        async def call(judge, criteria, weights, workspace, prompt):
            with mock.patch.object(driver.shutil, 'which', return_value='/usr/bin/bwrap'):
                commands.append(agents.get_agent('claude-code').build_command('exact prompt', {'type': 'object'}))
            return [criteria[0].id], 'synthetic result', []
        self.exercise(call, count=2)
        for command in commands:
            self.assertEqual(command[command.index('--') + 1:], original)
            self.assertIn('--ro-bind', command)
            self.assertIn('--unshare-pid', command)
            self.assertIn('--cap-drop', command)
        self.assertNotEqual(commands[0], commands[1])


if __name__ == '__main__':
    unittest.main()
