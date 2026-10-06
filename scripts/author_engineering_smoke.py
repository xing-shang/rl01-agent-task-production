#!/usr/bin/env python3
"""Exercise the local author toolchain using synthetic format fixtures only."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import tomllib
import zipfile
from pathlib import Path

from check_rl01_archive import check_archive
from check_rl01_package import ENGINEERING_VERSION, validate
from render_rl01_config import render_spec
from test_check_rl01_package import write_package_fixture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_dir',type=Path)
    args=parser.parse_args()
    args.output_dir.mkdir(parents=True,exist_ok=True)
    receipt={'ok':False,'engineering_version':ENGINEERING_VERSION,'scope':'synthetic_format_smoke_only',
             'business_task_created':False,'models_or_docker_executed':False,'files_verified':[], 'negative_controls':[]}
    code_root=Path(__file__).resolve().parent.parent
    manifest_path=code_root/'kit_manifest.json'
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text())
        for item in manifest['files']:
            path=code_root/item['path']
            actual=hashlib.sha256(path.read_bytes()).hexdigest()
            if actual!=item['sha256']:
                raise ValueError('kit hash mismatch: '+item['path'])
            receipt['files_verified'].append({'path':item['path'],'sha256':actual})
    receipt['checker_hashes']={name:hashlib.sha256((code_root/'scripts'/name).read_bytes()).hexdigest()
                               for name in ('check_rl01_package.py','check_rl01_archive.py','check_rl01_evidence.py')}
    with tempfile.TemporaryDirectory(prefix='rl01-author-smoke-') as temporary:
        batch=Path(temporary)/'format-smoke'
        task=batch/'FIN-QA-001'
        write_package_fixture(task)
        spec={'task':tomllib.loads((task/'task.toml').read_text()),'rubrics':json.loads((task/'rubrics.json').read_text())}
        spec['rubrics']['items'][0].update(type='Gradient',levels={'0':'零','0.25':'少','0.5':'半','0.75':'多','1':'全'})
        spec['deliverables_to_inspect']={x['id']:['output/report.txt'] for x in spec['rubrics']['items']}
        generated,_=render_spec(spec,task.name)
        for name,content in generated.items():
            (task/name).write_text(content,encoding='utf-8',newline='\n')
        checker=code_root/'scripts/check_rl01_package.py'
        command=[sys.executable,'-B',str(checker),str(task)]
        directory_run=subprocess.run(command,capture_output=True,text=True,check=False)
        receipt['directory_check']={'command':command,'exit_code':directory_run.returncode,'stdout':json.loads(directory_run.stdout),'stderr':directory_run.stderr}
        (batch/'交付文档.md').write_text('仅供工程格式测试的合成夹具，不是业务题或A3验收。\n',encoding='utf-8')
        staging_manifest=args.output_dir/'staging-manifest.json'
        manifest_command=[sys.executable,'-B',str(code_root/'scripts/check_rl01_archive.py'),str(batch),
                          '--write-manifest',str(staging_manifest)]
        manifest_run=subprocess.run(manifest_command,capture_output=True,text=True,check=False)
        receipt['staging_manifest']={'command':manifest_command,'exit_code':manifest_run.returncode,
                                     'stdout':json.loads(manifest_run.stdout),'stderr':manifest_run.stderr}
        archive=args.output_dir/'format-smoke.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as output:
            for path in sorted(batch.rglob('*')):
                if path.is_file():
                    output.write(path,path.relative_to(batch.parent).as_posix())
        archive_command=[sys.executable,'-B',str(code_root/'scripts/check_rl01_archive.py'),str(archive),
                         '--expected-manifest',str(staging_manifest)]
        archive_run=subprocess.run(archive_command,capture_output=True,text=True,check=False)
        receipt['archive_check']={'command':archive_command,'exit_code':archive_run.returncode,'stdout':json.loads(archive_run.stdout),'stderr':archive_run.stderr}
        for label, levels in (
            ('ADU_endpoint_keys',{'0.0':'零','0.25':'少','0.5':'半','0.75':'多','1.0':'全'}),
            ('BSI_levels_array',[{'value':v,'description':'判据'} for v in (0,.25,.5,.75,1)]),
        ):
            mutated=copy.deepcopy(spec['rubrics'])
            mutated['items'][0]['levels']=levels
            (task/'rubrics.json').write_text(json.dumps(mutated,ensure_ascii=False))
            issues,_=validate(task)
            receipt['negative_controls'].append({'case':label,'blocked':any(x['rule']=='rubric-levels' for x in issues),'issues':issues})
        (task/'rubrics.json').write_text(generated['rubrics.json'])
        (task/'task.toml').write_text(generated['task.toml'].replace('local-validation-fixture','python:3.12-slim; pending confirmation'))
        issues,_=validate(task)
        receipt['negative_controls'].append({'case':'CSE_pending_template','blocked':any(x['detail']=='metadata.environment_template is unresolved' for x in issues),'issues':issues})
        receipt['ok']=(directory_run.returncode==0 and manifest_run.returncode==0 and archive_run.returncode==0
                       and all(x['blocked'] for x in receipt['negative_controls']))
    receipt_path=args.output_dir/'smoke-receipt.json'
    receipt_path.write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':receipt['ok'],'engineering_version':ENGINEERING_VERSION,'receipt':str(receipt_path),'archive':str(archive)},ensure_ascii=False))
    return 0 if receipt['ok'] else 1


if __name__=='__main__':
    raise SystemExit(main())
