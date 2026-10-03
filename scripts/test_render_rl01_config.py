import copy
import json
import tempfile
import tomllib
import unittest
from pathlib import Path

from check_rl01_package import audit_likert_anchors, validate
from render_rl01_config import render_spec
from test_check_rl01_package import rubric_fixture, write_package_fixture


class ConfigurationGenerationTests(unittest.TestCase):
    def spec(self, root):
        write_package_fixture(root)
        rubric = rubric_fixture()
        rubric['items'][0].update(type='Gradient', levels={"0": "零", "0.25": "少", "0.5": "半", "0.75": "多", "1": "全"})
        rubric['items'][-1].update(type='Gradient', levels={"0": "无违规", "0.25": "少量违规", "0.5": "半数违规", "0.75": "多数违规", "1": "全部违规"})
        return {'task': tomllib.loads((root/'task.toml').read_text()), 'rubrics': rubric,
                'deliverables_to_inspect': {x['id']: ['output/report.txt'] for x in rubric['items']}}

    def test_same_spec_preserves_positive_and_negative_level_meanings(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'FIN-QA-001'
            spec=self.spec(root)
            original=copy.deepcopy(spec)
            files, _=render_spec(spec,root.name)
            self.assertEqual(original,spec)
            for name, content in files.items():
                (root/name).write_text(content)
            self.assertFalse(validate(root)[0])
            generated=tomllib.loads(files['tests/rubrics.toml'])['criterion']
            for original_item, item in zip(spec['rubrics']['items'],generated):
                self.assertEqual(abs(original_item['weight']),item['weight'])
                self.assertEqual(original_item['negate'],item['negate'])
                self.assertFalse(audit_likert_anchors(item,original_item))
            self.assertIn('1: 无违规',generated[-1]['description'])
            self.assertIn('5: 全部违规',generated[-1]['description'])
            self.assertTrue(generated[-1]['negate'])
            self.assertIn('score=yes',generated[1]['description'])

    def test_adu_and_bsi_forms_are_rejected_before_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'FIN-QA-001'
            good=self.spec(root)
            bad_levels=({'0.0':'零','0.25':'少','0.5':'半','0.75':'多','1.0':'全'},
                        [{'value':v,'description':'判据'} for v in (0,.25,.5,.75,1)])
            for levels in bad_levels:
                spec=copy.deepcopy(good)
                spec['rubrics']['items'][0]['levels']=levels
                with self.assertRaises(ValueError):
                    render_spec(spec,root.name)

    def test_future_domain_does_not_need_a_finance_or_medical_enum(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)/'FIN-QA-001'
            spec=self.spec(root)
            spec['task']['metadata']['domain']='未来领域'
            spec['task']['task']['keywords']=['new-domain','office','A3']
            files,_=render_spec(spec,root.name)
            self.assertEqual(['new-domain','office','A3'],tomllib.loads(files['task.toml'])['task']['keywords'])


if __name__=='__main__':
    unittest.main()
