# Construction Plan

This is a structured reading of `sources/02_外发版-基于weakness和skill+的数据构造方案.txt`. The 26-page PDF supplied on 2026-09-28 exposes the complete W1-W14 text table on pages 5-13. Use `weakness-catalog.md` and that source text when assigning tags. The old bitmap is retained only as historical evidence.

## Overall Distribution

The first batch contains 2000 items:

- 1000 specialty items based on Skill, Tool, or Workflow capability coverage.
- 1000 weakness-driven items targeting observed model failures.

Required domains: General Office `GO`, Finance `FIN`, Law `LAW`, Medical `MED`, Data Analysis `DA`, Game `GA`, and Design `DE`. Data must cover domains and internal labels evenly. Do not create three or more tasks from the same knowledge point or Workflow. The source difficulty table reports totals 200/600/200 and per-domain counts 50/150/50; these imply four domains and conflict with the seven-domain scope. Do not expand either set into a batch allocation without clarification. User-selected A3-only batches remain allowed within the requested scope.

## Difficulty And Complexity

The three-model average score must be below 0.7. After that, classify:

| Level | Name | Share | Total | Per domain | Mean |
| --- | --- | ---: | ---: | ---: | --- |
| A1 | Basic | 20% | 200 | 50 | `0.60 <= score < 0.70` |
| A2 | Advanced | 60% | 600 | 150 | `0.50 <= score < 0.60` |
| A3 | Hard | 20% | 200 | 50 | `score < 0.50` |

Each task is run once with `gpt-5.6-sol`, `claude-opus-4-8`, and `qwen3.8-max0902` under Claude Code. The judge is `qwen3.7-plus`. At least one model must score above zero. Submit model products and scoring trajectories.

## Specialty Data Quotas

| Capability family | Subcategory | Count |
| --- | --- | ---: |
| Skills | Skill Discovery | 200 |
| Skills | Skill Generation / Editing | 200 |
| Skills | Skill Dependency | 200 |
| Workflow Execution | Dependency-aware Workflow | 200 |
| Workflow Execution | Subagent Workflow | 200 |

Specialty data should systematically cover scenarios, difficulty, environments, and task forms, not merely repeat surface tools.

## Weakness-Driven Data

Weakness data starts from an explicit bad pattern or trigger and must reliably reproduce the intended failure under a competent setup.

Rules:

- 1000 items total.
- Cover all 14 weaknesses.
- Every item must have at least one `weakness_tag`.
- Each tagged weakness counts once, even if an item tags multiple weaknesses.
- Every weakness must be covered by at least 50 and at most 250 items.
- The tag must correspond to a real trigger in the prompt and environment; do not tag from surface topic alone.

All 14 definitions and trigger boundaries are in `weakness-catalog.md`. The source says `weakness_tag` uses column B names; W1-W14 are column A priorities. Example strings such as `W07-流程跳步` do not match the table and must not be copied as a formal vocabulary. The scaling observation about Qwen is a design hypothesis, not evidence that a new task has reproduced a failure.

## Complexity C1-C5

| Level | Files | Requirements | Outputs | Evidence chain | Execution/tool steps | Tool families | Depth | Count | Share |
| --- | ---: | ---: | ---: | --- | --- | ---: | --- | ---: | ---: |
| C1 | 2 | 3 | 1-2 | 1-hop | 1-3 / 1 | 1 | General common sense | 120 | 12% |
| C2 | 5 | 6 | 2-3 | 2-hop | 4-7 / 2-3 | 2 | Basic professional | 250 | 25% |
| C3 | 10 | 10 | 3-4 | 3-hop | 8-15 / 4-6 | 3 | Mid-level business | 350 | 35% |
| C4 | 25 | 15 | 4-6 | 4-hop | 16-30 / 7-10 | 4 | Advanced professional | 180 | 18% |
| C5 | 50+ | 20 | 4-8 for a large project, or 1 for one large deliverable | 5-hop | 30+ / 10+ | 5+ | Expert | 100 | 10% |

The table is the source's metric profile, not a mapping from A3. Its C1 row says two files but its narrative says one file; output count is expressly a reference and can be one for a large C5 project. Record actual metrics and flag borderline classifications instead of padding files. Narrative profiles:

- C1: one file, one output, one step, no professional knowledge.
- C2: simple multi-file comparison, two tools, basic professional threshold.
- C3: standard project, medium reasoning chain, three capability families.
- C4: complex project, long dependency chain, advanced domain knowledge.
- C5: large project or knowledge base, complete multi-artifact delivery, expert judgment.

Count files excluding duplicates and temporary files. Count requirements explicitly or implicitly necessary, including functional, format, citation, and quality constraints. Count tool calls as atomic operations. Repeated calls to the same tool family count as one family.

## Scaling Design Direction

Current Cowork tasks are often limited to filesystem/shell and fixed native tools; Skills may be auxiliary context rather than necessary; Workflows may be linear read-process-output. The next step is to expand environment distribution with real state changes, asynchronous dependencies, exception recovery, cross-tool coordination, blocking states, and Subagents.

### Skill Dependency

Make the special information, behavior rule, or SOP in the Skill necessary. Avoid Skills that are merely contextual documents.

Recommended patterns:

1. Special business rule: when two authoritative sources conflict, require the Skill's behavior to stop and ask the user rather than choose silently. Plant the conflict in the task.
2. Environment-specific SOP: define an internal approval or publication chain. If the model skips required steps, the final workflow state must fail.
3. Special calculation/judgment rule: include a special threshold, internal mapping, custom field definition, business priority, or fallback order that directly changes the final answer.

### Skill Generation / Editing

Construct tasks that create a Skill, modify an existing Skill, extract a Skill from an SOP, migrate a Skill, or repair a Skill package.

### Workflow Execution

Dependency-aware Workflows should contain explicit dependencies such as `A -> B`, `A -> C`, `B + C -> D`, and `D -> final`. The model must decompose dependencies, track completed work, avoid premature execution, and confirm all dependencies before the final action.

Subagent Workflows must require results from multiple Subagents before producing the final result. MCP Scaling is lower priority and can increase unfamiliar tool-schema generalization through MCP or dynamically injected tools.

## Skill Package Shape

A functional Skill is delivered under the environment skill directory. `SKILL.md` uses Anthropic frontmatter with name, description, and compatibility, then contains the SOP, script usage, failure recovery, and hard rules that make the Skill non-optional. `scripts/` and `references/` are included as needed. Dockerfile must copy the skill into the runtime location declared by the instruction.

For a directed SOP task, an explicitly required method may be stated when business-relevant. In Skill Discovery, list available skill names, descriptions and entry paths without revealing necessary skills or interference identities. The contract's discovery rule overrides indiscriminate copying of the contract-redliner example. Score resulting artifacts and valid workflow states, not skill invocation counts or call order (rewardkit section 3.4).

## Recommended Metadata

In addition to task.toml fields, maintain the logical linkage:

```toml
skill_set = ["<installed-skill-directory>"]
task_complexity = "C1 | C2 | C3 | C4 | C5"
expected_skill_dependencies = ["<subset of skill_set>"]
weakness_tag = ["<at least one formal tag>"]
```

`skill_set` matches `environment/skills/<name>/` exactly and may contain interference skills for Skill Discovery. `expected_skill_dependencies` is a strict subset of `skill_set` in discovery tasks and must be empty when no Skill is truly necessary.
