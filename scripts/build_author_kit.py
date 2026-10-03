#!/usr/bin/env python3
"""Build a small, versioned offline author engineering kit from maintained files."""
from __future__ import annotations

import argparse
import hashlib
import json
import stat
import zipfile
from pathlib import Path

from check_rl01_package import ENGINEERING_VERSION

FILES = (
    'scripts/check_rl01_package.py', 'scripts/check_rl01_archive.py',
    'scripts/render_rl01_config.py', 'scripts/author_engineering_smoke.py',
    'scripts/test_check_rl01_package.py', 'scripts/test_check_rl01_archive.py',
    'scripts/test_render_rl01_config.py',
    'assets/schemas/rubrics.schema.json', 'assets/schemas/task.schema.json',
    'assets/templates/task.toml', 'assets/templates/Dockerfile',
    'assets/templates/solve.sh', 'assets/templates/prompt.md',
    'assets/templates/test.sh', 'assets/templates/finalize.py',
    'references/web-author-engineering.md', 'references/rubrics-and-scoring.md',
    'references/rewardkit-delivery-contract.md', 'references/weakness-catalog.md',
    'references/submission-table-and-naming.md',
)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output_zip',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parent.parent
    prefix='rl01-author-engineering-'+ENGINEERING_VERSION
    manifest={'engineering_version':ENGINEERING_VERSION,'scope':'offline_author_engineering',
              'client_official_schema':False,'files':[]}
    entries=[]
    for name in FILES:
        path=root/name
        data=path.read_bytes()
        mode=stat.S_IMODE(path.stat().st_mode)
        manifest['files'].append({'path':name,'bytes':len(data),'sha256':hashlib.sha256(data).hexdigest(),'mode':mode})
        entries.append((name,data,mode))
    entries.append(('kit_manifest.json',(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode(),0o644))
    args.output_zip.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(args.output_zip,'w',zipfile.ZIP_DEFLATED) as output:
        for name,data,mode in entries:
            info=zipfile.ZipInfo(prefix+'/'+name,date_time=(2026,10,3,0,0,0))
            info.create_system=3
            info.external_attr=(stat.S_IFREG|mode)<<16
            info.compress_type=zipfile.ZIP_DEFLATED
            output.writestr(info,data)
    digest=hashlib.sha256(args.output_zip.read_bytes()).hexdigest()
    args.output_zip.with_suffix('.manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':True,'engineering_version':ENGINEERING_VERSION,'path':str(args.output_zip),
                      'sha256':digest,'files':len(entries)},ensure_ascii=False))


if __name__=='__main__':
    main()
