# Rewardkit Delivery Contract

This reference uses the S03 PDF text and S12 original Markdown, `sources/12_rewardkit_feishu_20260913.md`. S12 supplies the exact fenced code-block bytes for the fixed verifier templates. It is combined with the RL0-1 guideline and construction plan; do not replace the full snapshots with this summary.

## One Task Per Directory

Use the task ID as the directory name. The standard root contains:

```text
<task-id>/
├── instruction.md
├── task.toml
├── rubrics.json
├── environment/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── skills/
│   │   └── <skill-name>/
│   │       ├── SKILL.md
│   │       ├── scripts/
│   │       └── references/
│   └── input_files/
├── solution/
│   ├── solve.sh
│   └── golden_output/
└── tests/
    ├── test.sh
    ├── finalize.py
    ├── rubrics.toml
    ├── prompt.md
    ├── __golden_output/
    └── __assets/
```

Required components:

- `instruction.md`, task prompt, size at most 1 MiB.
- `task.toml`, Harbor configuration and metadata, size at most 1 MiB.
- `rubrics.json`, original scoring rules.
- `environment/Dockerfile` and `environment/requirements.txt`; `requirements.txt` must exist even if empty.
- `environment/input_files/`, all real task inputs, included in the 20 GB batch limit.
- `environment/skills/` when a task declares a Skill; it must correspond to `metadata.skill_set` and include `SKILL.md`, scripts, and reference material as needed.
- `solution/solve.sh`, executable Oracle entrypoint.
- `solution/golden_output/`, expert standard answer.
- `tests/test.sh` and `tests/finalize.py`, fixed appendix templates copied byte-for-byte.
- `tests/rubrics.toml`, scoring rubric, size at most 2 MiB.
- `tests/prompt.md`, judge prompt with a `{criteria}` placeholder.
- `tests/__golden_output/`, a byte-identical copy of `solution/golden_output/`.
- `tests/__assets/`, optional scoring assets.

Container visibility:

| Source | Container path | Visibility |
| --- | --- | --- |
| `instruction.md` | Prompt | Agent-visible |
| `environment/input_files/` | `/app/input_files/` | Agent-visible, read-only |
| `environment/skills/` | Location declared by Dockerfile and instruction | Agent-visible |
| Agent output | `/app/output/` | Agent-visible and writable; sole delivery directory |
| Agent logs | `/logs/agent/` | Visible but not deliverables |
| `solution/` | `/solution` | Oracle stage only, not agent-visible |
| `tests/` | `/tests` | Scoring stage only, not agent-visible |

Default limits:

- `[agent].timeout_sec = 72000.0` (1200 minutes), raise for long tasks as needed.
- `[verifier].timeout_sec = 18000.0`, must exceed one judge session timeout.
- User-selected defaults for new tasks: 2 CPUs, 2048 MiB memory, 30720 MiB storage. The client S03 example uses 8192 MiB; the user changed the local default to 2048 MiB on 2026-10-01 after measuring existing financial runs. Record the resource choice and its evidence; larger tasks can use an explicitly justified higher limit. See [VPS runtime resources](vps-harbor.md).
- Agent output total at most 2 GB.
- Entire batch ZIP at most 20 GB, including inputs and Golden outputs.

## Instruction.md

The prompt must be self-contained. It may reference only the input materials and container-preinstalled tools/skills; it may not rely on hidden context or external links. It must:

- Limit source files to `/app/input_files/`.
- Limit deliverables to `/app/output/`.
- List every source file and explain fields, units, versions, and reconciliation rules.
- List all available Skill names, applicability, container path to `SKILL.md`, and the base directory for scripts when Skill-dependent.
- Give exact deliverable names and formats.
- Align every explicit rubric requirement with an instruction requirement and cover every hard instruction requirement with a criterion.
- Avoid rubric wording, Golden content, scoring hints, expected conclusions, and phrases like "评分将检查".

The Skill instruction must not reveal whether a skill is necessary, an interference item, or a member of `expected_skill_dependencies`.

## Task TOML

`schema_version` and `artifacts` must come first, then `[metadata]`, then `[[metadata.deliverables]]`, `[agent]`, `[verifier]`, and `[environment]`.

Use the current reference shape:

```toml
schema_version = "1.4"

artifacts = [
  "/app/output/<exact-file-1>",
  "/app/output/<exact-file-2>",
]

[task]
name = "work/<normalized-task-id>"
version = "1.0.0"
description = "<one-sentence task description>"
keywords = ["<domain-english>", "office", "<A1|A2|A3>"]

[metadata]
task_id = "<exact task-id>"
author_organization = "<supplier-name>"
category = "<skill-dependency | workflow-execution | weakness-driven | ...>"
domain = "<domain>"
domain_l2 = "<second-level label>"
domain_l3 = "<third-level label>"
domain_l4 = "<fourth-level scenario label>"
capabilities = "<evaluated capabilities>"
difficulty = "A1 | A2 | A3"
vl_dependency = "是 | 否"
source_note = "<task source and authenticity>"
tools = "<Word/Excel/PPT/Python/etc.>"
domain_knowledge = "<optional domain knowledge>"
expected_pass_rate = 0.0
task_complexity = "C1 | C2 | C3 | C4 | C5"
weakness_tag = ["<at least one tag>"]
environment_template = "<platform-confirmed environment template>"
tool_set = ["<actual available tools>"]
skill_set = ["<installed skill directory names>"]
expected_tool_dependencies = ["<actual required tools>"]
expected_skill_dependencies = ["<subset of skill_set>"]
tags = ["<task keywords>"]

[[metadata.deliverables]]
path = "<exact basename or relative path under /app/output/>"
required = true
desc = "<one-sentence description>"

[agent]
timeout_sec = 72000.0

[verifier]
timeout_sec = 18000.0
user = "root"

[verifier.env]
JUDGE_API_KEY = "${JUDGE_API_KEY:-}"
JUDGE_BASE_URL = "${JUDGE_BASE_URL:-}"
JUDGE_MODEL = "${JUDGE_MODEL:-qwen3.7-plus}"
JUDGE_PROVIDER = "${JUDGE_PROVIDER:-anthropic}"
JUDGE_API_PROTOCOL = "${JUDGE_API_PROTOCOL:-anthropic}"
EVAL_API_KEY = "${EVAL_API_KEY:-}"
EVAL_API_BASE = "${EVAL_API_BASE:-}"
LITELLM_DROP_PARAMS = "true"

[environment]
os = "linux"
build_timeout_sec = 18000.0
network_mode = "public"
cpus = 2
memory_mb = 2048
storage_mb = 30720
```

Field constraints:

- This working example uses the user's 2048 MiB memory default. The original S03 example remains 8192 MiB in the source snapshot; do not describe the user preference as a client rule change. Freeze and validate candidate generation, Golden and regrades against the same resource version.

- This working example expands required deliverables only. The source's extra `/logs/artifacts/output` entry conflicts with its field table; see Q3 in `conflicts-and-clarifications.md` before freezing a submission.

- `[metadata].task_id` must equal the task directory name and the normalized name segment of `[task].name`.
- Use the client task-ID convention, generally `<domain-abbreviation>-<task-type>-<sequence>`, and keep the `[task].name` organization prefix consistent with the batch directory.
- `[task].version` starts at `1.0.0`; increment only the patch version for a formal return.
- `[task].keywords` is mechanically `[<domain-english>, "office", <A1|A2|A3>]`; do not replace it with the free-form `tags` array in `[metadata]`.
- `[metadata].domain_l3` and `[metadata].domain_l4` are required by the S03 section 3.2 field table even though some examples omit them. S09 asks whether they are mandatory and remains unanswered; continue following the field table, without presenting this as a new client answer. See [the clarification record](conflicts-and-clarifications.md).
- `tool_set` declares the actual model-available capabilities using platform-existing names such as `filesystem`, `shell`, and `python`; do not require a one-to-one native tool per name.
- `skill_set` directory names must match `environment/skills/<name>/` and the `name` in each `SKILL.md`; it may include interference skills and is empty when there are no skills.
- `expected_tool_dependencies` and `expected_skill_dependencies` are subsets of their available sets. Do not require every available tool or skill to be called. In Skill Discovery, `expected_skill_dependencies` is a true strict subset of `skill_set`.
- Optional `[metadata].expected_pass_rate`, when present, is a number from 0 to 1.
- Required deliverable paths must be exact; `required = true` may not use glob. Optional process artifacts may use glob only if required is false.
- Do not generate dates, timestamps or version components dynamically in deliverable filenames. If the business requires a fixed date, write the exact dated filename in the instruction and keep it byte-identical across all six references, as permitted by S12 section 3.3. Personal-table outer ZIP naming follows its separate convention.
- Names are case-sensitive. The exact deliverable name must be byte-identical in `instruction.md`, `[[metadata.deliverables]]`, `artifacts`, `solution/golden_output/`, `tests/__golden_output/`, and criterion description.
- A deliverable path may include directory layers, but rubric descriptions must refer to complete file paths, not only directories. Use UTF-8 names without control characters, keep each filename at most 200 bytes, and prefer the task-ID prefix.
- `expected_skill_dependencies` and any other expected dependency set must be a subset of the corresponding available set.
- Judge variables belong only in `[verifier.env]`, never `[environment].env`.
- Only allowed `[environment]` keys may be used: `os`, `network_mode`, `allowed_hosts`, `build_timeout_sec`, `docker_image`, `cpus`, `memory_mb`, `storage_mb`, `env`, and `healthcheck`. Do not write `workdir`; set `WORKDIR /app` in Dockerfile.
- Use `${JUDGE_*:-default}` syntax for optional Judge variables; do not put real credentials in TOML.

## Dockerfile

Use one Dockerfile per task; `assets/templates/Dockerfile` is the baseline. Build from official sources only; do not use domestic mirrors. The baseline installs Python 3.12-slim, an `agent` user, node/npm, LibreOffice, Chinese fonts, `claude-code@2.1.114`, `harbor-rewardkit[all]==0.1.7`, and common parsers. A task-specific `requirements.txt` is copied and installed. Inputs are copied read-only into `/app/input_files/`; `/app/output/` is writable; `WORKDIR /app`. If the task has Skills, also `COPY skills/ /skills/` and ensure the Agent user can read and execute them.

After `docker build -t <task-id> environment/`, run:

```bash
docker run --rm --network none <task-id> bash -lc '
  python3 -V && bash --version | head -1 && node -v &&
  claude --version | grep -q 2.1.114 &&
  rewardkit --help >/dev/null && markitdown --help >/dev/null &&
  python3 -c "import openpyxl, docx, pptx, pypdf" &&
  pip show harbor-rewardkit | grep ^Version: && pip check &&
  id agent && su agent -c "touch /app/output/.w && rm /app/output/.w" && echo OK'
```

The last line must print `OK`. The self-check also proves Python, Bash, node/npm, Claude Code 2.1.114, RewardKit, document parsers, pip consistency, the `agent` user, and writable `/app/output/`.

## Solution And Golden

本节保留客户题包与Oracle的书面要求。网页Pro完成Golden、逐项自评和真实生成记录，金融本地默认复用现成Golden完成同冻结版本真实Oracle预检及逐项评分，已有有效同版证据先核对复用。可按授权并行预跑Golden与三候选，Golden通过后统一评分候选。题包保留下述solve.sh、Golden及字节一致副本，各项实际执行状态按真实回执记录，接力步骤见[Pro接力](pro-golden-handoff.md)。医疗本地继续按已明确的格式范围处理。

`solution/solve.sh` is normally `assets/templates/solve.sh`:

```bash
#!/bin/bash
set -euo pipefail

mkdir -p /app/output
cp -R /solution/golden_output/. /app/output/
```

After Oracle execution, the standard answer must satisfy:

- File names, formats, and counts exactly match `instruction.md` and `[[metadata.deliverables]]`.
- Every positive rubric criterion is satisfied.
- No negative or safety criterion is triggered.
- `solution/golden_output/` and `tests/__golden_output/` contain identical nonempty content.
- Golden main score is at least 0.85.

## Fixed Verifier Templates

`tests/test.sh` and `tests/finalize.py` are platform-fixed templates in Appendix A of the rewardkit source. Copy them byte-for-byte, including comments. Do not modify, reformat, reorder, or trim them.

The maintained assets are extracted from S12's fenced code blocks, preserving LF, comments, indentation and trailing blank lines. `assets/templates/source-manifest.json` records the source URL, raw Markdown hash, fence lines and extracted-template hashes. The checker verifies the manifest and assets against the reviewed pinned hashes before comparing the task copies; a missing manifest or asset, or a changed baseline, fails preflight even when the task copies match it. When the retained source is present its hash is also checked. Offline author kits include the manifest and hashes while private source documents remain outside the kit. These locally computed hashes are not client-published standalone script hashes.
