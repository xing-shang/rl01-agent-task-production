# RL0-1 Production Guideline

This is a structured reading of `sources/01_RL0-1-数据生产规范GuidelineV1.1--20260920+for外部供应商.txt`. It must be combined with the rewardkit delivery contract and the construction plan.

## Purpose And Scope

This reference also incorporates the explicitly revised QA wording retrieved on 2026-09-28; older examples do not override it. The document defines specifications, formats, quality standards, and acceptance for RL0-to-1 annotation data. It applies to all data-production flows and is written for suppliers, universities, internal/external experts, and annotation QA platforms.

An expert is expected to:

1. select a real, professionally valuable task in the expert's domain;
2. write a task description appropriate for that scenario;
3. provide realistic reference files;
4. produce a reference answer in the required deliverable format;
5. write a scoring rubric that measures whether the deliverable is good.

The acceptance logic uses the submitted rubric to check that the Golden score is at least 0.85, then runs three models to verify that the task is difficult enough. Human QA specifically checks authenticity, reference-answer reasonableness, rubric quality, and hack attempts. Hacks are rejected outright.

## Knowledge Coverage

Questions must be evenly distributed. The required first- and second-level labels must be covered. Additional second-level labels may be added with prior explanation. Third-level labels are empty and must be filled during question creation. Distribution must be uniform, and more than two questions under the same third-level label are not accepted, even though two are allowed.

## Difficulty

Difficulty is measured by the three-model average score after normalization to 1.0:

| Level | Production share | Average correct rate |
| --- | --- | --- |
| A1 Basic | 20% | `60% <= mean < 70%` |
| A2 Advanced | 60% | `50% <= mean < 60%` |
| A3 Hard | 20% | `mean < 50%` |

Per-task difficulty is measured under Claude Code with `gpt-5.6-sol`, `claude-opus-4-8`, and `qwen3.8-max0902`, each run once. The judge model is `qwen3.7-plus`. The three-model mean must be below 0.7 overall, and at least one model must score above zero. Submit model products and scoring trajectories with the task so difficulty can be verified.

## Three Core Components

### Task Description

The task description must use natural language to describe the scenario, required materials, and deliverable requirements. Task instructions, output requirements, and hard constraints such as forbidden actions or filename rules must be explicit in standalone paragraphs. They must not be hidden inside parentheses.

### Reference Files

Reference files are the real inputs required to complete the task, such as CSV, PDF, contracts, and logs. Use the actual source files for the scenario's real deliverable. They must be real data. Do not require the model to invent regulations, policy interpretations, role responsibilities, or statistics. There is no file-count limit, but the total size is at most 20 GB.

### Reference Answer

The reference answer is produced by the domain expert and serves as the rubric self-check baseline. Its deliverable type, filename, and count must match the task description exactly. After scoring, it must meet `score_final >= 0.85`; if not, the answer or rubric must be corrected.

## Original Rubric Vocabulary

The RL0-1 guideline describes the original scoring rule with these fields:

- `description`: concrete verifiable judgment.
- `dimension`: first-level and optional second-level quality dimension.
- `criterion_type`: `Objective` or `Subjective`.
- `criterion_necessity`: `Explicit` or `Implicit`.
- `type`: `Binary` or `Gradient`.
- `weight`: one of `+10`, `+7`, `+3`, `-3`, `-7`, `-10`.
- `levels`: for Gradient criteria, the score levels from 1 to 0.25 or 0.

A positive score rewards behavior or output required by real production. A negative score represents behavior or output that real production must avoid. Do not create both a positive and a negative item on the same angle.

The rewardkit package converts this into `tests/rubrics.toml`: positive `Gradient` items become `likert` with `points = 5`; negative items become positive-weight criteria with `negate = true`. Never write a negative weight in the delivery TOML.

## Evaluation Dimensions

Every rubric item needs a dimension. Required or commonly required dimensions include:

| Dimension | Focus |
| --- | --- |
| Instruction compliance | Explicit task content, scope, count, naming, path, format, unit, precision, required and forbidden content. |
| Content quality - conclusion correctness | Whether the final judgment or recommendation follows the evidence and is correct. |
| Content quality - numerical and calculation accuracy | Extraction, formula, unit conversion, aggregation, denominator, time range, precision, and tolerance. |
| Content quality - professional standards | Domain-specific rules, standards, terminology, business interpretation, and compliance. |
| Content quality - analysis and evidence quality | Whether facts, citations, calculations, and reasoning are faithful to inputs and traceable. |
| Content quality - factual fidelity | Whether cited facts and sources exist and are not fabricated or confused across files, versions, subjects, or periods. |
| Structure and organization | Information architecture, hierarchy, order, grouping, completeness, and placement of text, tables, and charts. |
| Operational and delivery safety | No destruction, overwrite, deletion, or accidental loss of unrelated input content. |
| Safety and compliance | Privacy, data security, copyright, legal compliance, sensitive data, misleading claims, bias, and risk. |
| Above-baseline contribution | Additional verifiable value such as double-checking, compatibility, usability, or identifying an instruction gap. |
| Visual quality | Only for deliverables with visual requirements; convert appearance into observable layout checks. |

Content quality, operational and delivery safety should carry high weight. Add professional standards for domain-heavy tasks, visual quality for design deliverables, structure for writing deliverables, and numerical/calculation accuracy for financial tasks.

## Rubric Distribution

Current QA C1 counts only the positive weights in conclusion correctness, numerical/calculation accuracy, professional standards and factual fidelity toward the 30% domain-anchor threshold. Analysis/evidence quality is still a valid dimension but is not in that numerator. A1/A2/A3 require at least 8/12/25 criteria. Total negative magnitude must not exceed 50% of total positive weight. Every task must include at least two `Critically Important` positive items worth 10. A -10 item is only for a major professional error, hallucination, business safety, or compliance risk. Instruction compliance, conclusion correctness, analysis/evidence quality, and factual fidelity are generally required; adjust other dimensions by deliverable type.

## Metadata

The original guideline requires task ID, domain, second-, third-, and fourth-level labels, evaluated capabilities, difficulty, task rationale/source note, required tools, optional domain knowledge, and visual-language dependency. The rewardkit contract adds environment, tool, Skill, complexity, weakness, and dependency fields.

## AI And Human QA

AI checks include task quality, rubric quality, and total score. AI total-score checks require:

- Golden score at least 0.85.
- Three-model mean below 0.7.
- Assign the measured band after admission: A1 [0.6,0.7), A2 [0.5,0.6), A3 below 0.5. A targeted A3 task that measures A2 has not met the user's A3 goal.
- At least one model score above zero.

Human QA follows the separate RL0-1 QA guideline and must verify professional realism, not only structural validity.

## 金融二级标签

本次11页PDF第2页图片已核读，金融固定二级为：Fin1-投资银行、Fin2-股票研究、Fin3-私募股权、Fin4-财富管理、Fin5-零售证券投资、Fin6-家庭财富规划、Fin7-消费金融、Fin8-个人税务与社保、Fin9-跨境个人金融。按当前平台枚举填写，不能只因使用财务数据就把会计/审计题随意归到投资银行。三、四级写具体知识点与场景；同三级最多2题。图片只给出通用办公、金融、法律、医疗，DA/GA/DE的正式二级体系未随这批资料提供。

## 真实性与匿名化

新专家文档允许对真实单位、个人匿名化/虚拟化，公开财报、行情、政策、法律等按其说明可保留公开信息；非公开公章等须处理。其示范又使用“脱敏后的模拟数据”，与“必须真实数据”边界不清。先保留可核验原始来源及转换说明，不将完全虚构材料标为真实；全合成数据是否允许见待确认事项。网页证据要作为可直接读取文件冻结，不让离线被测模型自行联网找答案。
