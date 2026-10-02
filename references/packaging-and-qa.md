# Packaging And QA

Use this after task construction and before handoff. The rewardkit source document remains the final authority for fixed templates and exact checklist wording.

## Naming And Batch Layout

For customer delivery under S03, single-task submission is named as supplier + domain + first-level category + date/time, for example:

```text
xx-金融-投资银行-20260807提交
```

Multi-task submission uses supplier + domain + batch + date/time. Submit separately by domain. The batch hierarchy is:

```text
<batch-name>/
├── 交付文档.md
├── <task-id-001>/
│   ├── instruction.md
│   ├── task.toml
│   ├── rubrics.json
│   ├── environment/
│   ├── solution/
│   └── tests/
├── <task-id-002>/
└── ...
```

Do not add an extra wrapper layer and do not place task directories directly at the ZIP root. The batch root must contain `交付文档.md`. The production guideline requires model products and run trajectories at submission, and rewardkit section 8.3 requires one ZIP for the batch. Default to including that evidence in the same batch ZIP, outside the task directories and Agent-visible inputs. A batch-root `evidence/<task-id>/<model>/` directory with an index in `交付文档.md` is a local organization choice, not a client-prescribed path. Do not ask the user to choose between one ZIP and a companion bundle unless an actual submission-system constraint requires it.

S09询问是否需要`evidence.zip`和`交付文档.md`，截至2026-10-01未答复。当前继续依据S03§8.3—8.4交付批次根目录的说明文件，并按Q3随批附证据；不额外把独立文件名`evidence.zip`设为硬门槛，也不能将该提问理解为证据可省略。答复状态见[冲突记录](conflicts-and-clarifications.md)。

For a formal return, increment `[task].version` from `1.0.0` to `1.0.1` or the next patch version. Resubmit only revised task directories. Preserve the original supplier code and append `_fix<N>` to the original batch and ZIP name, for example `work_b01_20260805_fix1`.

用户2026-10-02明确当前题目均属于首次提交，先前修改为内部迭代。首次提交前即使已有多个本地版本，也不使用“返修”或`_fixN`，不因此填写“修改提交”。只有实际客户返修后的正式重交才执行上一段。版本号继续据实记录，不能为了首次提交的名称伪造或回退运行版本。

用户个人飞书提交表的附件采用[提交表与命名约定](submission-table-and-naming.md)：`<领域>-<YYYYMMDD>-澳鹏通用RL0-1-<本表自动编号>.zip`；已有表编号时直接读回，纯本地交付且没有表编号时使用真实`task_id`。这是该表的附件显示命名，不把它替换成S03的通用客户规范；包内批次目录仍按上面的合同结构，题目目录仍用真实`task_id`。未来准备附件时核对编号映射、日期、ZIP哈希和索引。该表不设截图列，模型产物、轨迹与评分证据仍按本页纳入题包。

## Delivery Document

`交付文档.md` must include a privacy-safe runtime note, but must not reproduce the internal environment-variable configuration table. Do not expose Judge or candidate-Agent variable names, values, service addresses, model routes, protocol choices, cache or effort settings, concurrency details, or internal runtime adaptations in the delivery document. State only that required configuration is supplied by a controlled runtime and that credentials and internal configuration are excluded. The table below is an internal execution reference and must not be copied into an external delivery document.

Baseline variables:

| Key | Required | Default | Type | Meaning |
| --- | --- | --- | --- | --- |
| `JUDGE_API_KEY` | yes | runtime injected | string | Judge gateway key; test.sh derives Anthropic/OpenAI variables. |
| `JUDGE_BASE_URL` | yes | runtime injected | string | Judge gateway URL; may include `/v1`, which test.sh strips. |
| `JUDGE_MODEL` | no | `qwen3.7-plus` | LiteLLM model string | Overrides `rubrics.toml` model through `REWARDKIT_MODEL`; also drives OpenAI-protocol fallback when protocol is OpenAI. |
| `JUDGE_PROVIDER` | no | `anthropic` | `anthropic` / `openai` | Informational declaration only. |
| `JUDGE_API_PROTOCOL` | no | `anthropic` | `anthropic` / `openai` | `anthropic` uses Claude Code agent judge; `openai` downgrades to OpenAI-protocol LLM judge and changes the prompt tool hint. |
| `EVAL_API_KEY` / `EVAL_API_BASE` | no | empty | string | Legacy compatibility; ignored when `JUDGE_*` exists. |
| `LITELLM_DROP_PARAMS` | no | `true` | bool/string | Gateway compatibility switch; copy as specified. |

Judge session timeout is in `rubrics.toml` as `timeout = 7200`; verifier timeout is in `task.toml` as `timeout_sec = 18000`. There is no runtime override hook, so changes require a new package and must be stated in the delivery document.

## Static Preflight

Before packaging, verify:

1. All required package components exist; `environment/requirements.txt` exists even when empty.
2. `solution/solve.sh`, `tests/test.sh`, and `tests/finalize.py` use LF line endings; `solve.sh` and `test.sh` have executable bits.
3. Deliverable names are byte-identical in `instruction.md`, `[[metadata.deliverables]]`, `artifacts`, `solution/golden_output/`, `tests/__golden_output/`, and criterion descriptions. Count source files from disk and reconcile totals and purported complete file lists wherever they occur in the prompt, Skill, rules, Golden evidence index, or rubrics; a source mentioned in prose should also appear in a purported complete table.
4. Rubric count is at least A1:8/A2:12/A3:25 and distribution satisfies current QA; there are at least two weight-10 positive items; the four QA-defined domain-anchor dimensions contribute at least 30% of positive weight, and total negative magnitude is at most 50% of positive weight; required dimensions are covered.
5. Weights are only `3.0`, `7.0`, or `10.0`; types are only `binary` or `likert`; every `likert` has `points = 5` and 5/4/3/2/1 anchors; no negative weight exists.
6. Golden preflight passes with Oracle score at least 0.85 and `verifier_error = 0`.
7. `task_id` is consistent across directory name, `[metadata].task_id`, and the name segment of `[task].name` after normalized comparison; `[task].name`'s organization segment matches the batch prefix code. Replace platform template placeholders with confirmed values, check the declared environment image against `environment/Dockerfile`, and verify `domain_l2` describes the actual scenario.
8. No real key, token, credential, private key, secret file, or scoring-related variable appears in `[environment].env` or anywhere else in the package. Use placeholders only where allowed.
9. No `.git/`, `__pycache__/`, `.venv/`, `__MACOSX/`, `.DS_Store`, intermediate reward logs, old archives, QA screenshots, generation scripts, or private reports remain in the task root. Keep required candidate evidence in the documented batch evidence directory; use a separate upload only when the actual submission workflow requires it. Inspect all evidence for credentials and irrelevant residue.
10. All names are UTF-8, each name is at most 200 bytes, no symlink exists, and the archive is at most 20 GB.
11. `rubrics.toml` has `judge = "claude-code"`, each criterion has `name = id`, and descriptions include deliverable paths.
12. `tests/prompt.md` exists and contains `{criteria}`; prompt plus descriptions totals below 100 KB.
13. Docker self-test ends with `claude --version` showing `2.1.114`.
14. TOML and prompt files contain no invisible whitespace such as U+00A0 or U+3000.
15. Judge variables in `[verifier.env]` use the `JUDGE_` prefix and optional variables use `${VAR:-default}` syntax. `JUDGE_*` never appears in `[environment].env`.
16. A local scoring run produces a numeric `reward.txt` matching `reward.json`; `reward-details.json` appears consistently in `/logs/verifier/` and its `graded/` subdirectory; success does not contain `reward_exit_message.json`; forced failure creates the latter with a correct exit code. Treat zero counted criteria or a verifier error as invalid scoring, not a model failure.
17. The batch root contains `交付文档.md` with the privacy-safe runtime note. It does not expose internal Judge or candidate-Agent configuration, credentials, service addresses, or secret-shaped values. Its version, test status, evidence locations, and open items agree with `task.toml`, the difficulty report, the validation report, and actual archive entries.

For Skill/Workflow tasks, also verify that `skill_set`, skill directories, instruction entries, and Dockerfile copy paths agree; dependency sets satisfy subset rules; the real Agent user can read skills and run scripts; and the SOP has complete conditional branches and completion checks. This is an environment and instruction check, not process scoring.

When `[task]` is absent or needs repair, the contract permits:

```bash
harbor task update "path/to/<task-id>" --org "<supplier-code>"
harbor task update "path/to/tasks" --org "<supplier-code>" --scan
```

After batch repair, manually verify `[task].name`; the command generates it from the directory name. Local `harbor run -p ...` does not require Harbor login, but use one supplier code consistently across the batch and all returns.

## Quality Gates

For a static local preflight, run:

```bash
~/.codex/skills/rl01-agent-task-production/scripts/check_rl01_package.py <task-directory>
```

The script checks required structure, task TOML fields including unresolved environment templates and the current S02 column-B weakness vocabulary, rubric hard constraints, relative-path Golden identity, executable/LF files, forbidden residue, and credential-shaped text. Invalid table, array, ID, weight or description types are reported as field diagnostics; syntactically parseable TOML is not sufficient. JSON/TOML rubric checks cover one-to-one IDs, absolute weights, penalty direction and type conversion. Likert descriptions must have exactly five nonempty raw integer anchor lines, `1:` through `5:`; normalized anchor labels and detectable swapped JSON level texts fail preflight. Reworded anchor meaning still requires manual comparison. Review its warnings, including repeated rubric deliverable lists, before freezing. It does not run Docker, render documents, judge semantic validity or replace the manual quality gate; template equality is checked against the maintained local assets, not an independently supplied client source-code hash.

最终ZIP还须执行`scripts/check_rl01_archive.py <final.zip>`。该脚本只读原ZIP，在临时目录解压并恢复文件执行位，再用当前题目检查器逐题预检；同时检查整个ZIP的.DS_Store等残留、CRC、自包含批次结构、重复/非法路径和文件名编码。必须取得退出码0和ok=true；已有包内preflight.json、模型成绩或打包前的目录通过记录不能替代本次结果。临时解压目录自动清理，实际ZIP哈希及两个检查器哈希由回执返回，回执保存在包外台账，避免把最终ZIP的自身哈希写回ZIP导致哈希改变。重新打包或修改ZIP后重做检查。该脚本验证静态门槛，正式运行、语义、视觉、模型证据及客户验收仍依各自来源核对。

Run separate gates; passing one does not imply another:

- Structural gate: required files, TOML/JSON parse, fixed-template identity, exact names, permissions, and line endings.
- Semantic gate: task requirements are self-contained, sources support every conclusion, and rubric items do not leak or invent requirements.
- Golden gate: all positive criteria pass, no negative or safety criterion fires, and Oracle score is at least 0.85.
- Visual gate: every final document renders without clipping, overlap, missing glyphs, broken formulas, empty pages, or unreadable tables/charts.
- Residue gate: no AI-authorship labels, generator names, internal paths, credentials, QA files, or local tool residue in content, Office XML, PDF metadata, filenames, or ZIP entries.
- Archive gate: ZIP extraction reproduces structure and bytes, preserves executable modes, has no traversal or symlink, and hash is recorded only after the final freeze.
- Candidate gate: run the required candidate models on the exact artifact digest and preserve products and trajectories.

## Difficulty Evidence

Submit model products and trajectories with the task. A difficulty result is valid only when the exact artifact digest is preserved and the required models execute under the stated framework and judge. Provider errors, timeouts, missing routes, zero counted criteria, or wrapper failures are infrastructure evidence, not task difficulty. For each model, retain the run identity, artifact digest, output, trajectory, aggregate reward, and per-criterion judgments with reasons where the judge provides them. Recompute the aggregate using the packaged scoring implementation and reconcile it with every reported score carrier. If per-criterion detail is unavailable, explicitly mark it missing and do not claim it is attached.

Acceptance bands:

| Level | Three-model mean |
| --- | --- |
| A1 | 0.60 to below 0.70 |
| A2 | 0.50 to below 0.60 |
| A3 | below 0.50 |

The mean across the three models must be below 0.7, and at least one candidate must score above zero.

Before handoff, run Golden scoring on the exact frozen task version and keep its aggregate and per-criterion evidence. A score inherited from an earlier digest does not close the Golden gate. Check every cited evidence path inside the actual archive, and align all delivery and validation documents on whether each run has occurred. Do not cite an unsupplied failed run or private QA receipt as if it were in the handoff.

For web Pro production, use [the Golden handoff sequence](pro-golden-handoff.md): exported-file semantic checks and per-criterion proof, followed by actual Oracle/Golden. Under the user's 2026-10-01 scheduling update, preflighted and frozen candidate Agents may run in parallel with Golden; retain their artifacts and trajectories without grading, then grade them uniformly after the valid Golden gate. See [VPS runtime](vps-harbor.md) for resource limits, low effort on the three candidate Agents only, caching and regrade prerequisites. Golden generation/review, scoring, and other work preserve their explicit or default effort; the proxy does not force low for those stages. Missing web runtime capability is recorded, not simulated. For local Agent and Judge calls, enforce [ten retries after the initial failure](execution-reliability.md), including response-body and stream failures, with an effective limit of eleven physical attempts per logical request and no repeated successful task generation.

## Final Freeze

Create the ZIP with UTF-8-safe tooling, verify CRC and extracted structure, rerun checks on extracted bytes, record SHA-256, and stop mutating. Hand off only the ZIP path, exact state, task count, validation summary, Oracle result, candidate status, residue result, SHA-256, and residual risks.
