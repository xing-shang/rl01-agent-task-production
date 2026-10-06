# 网页Pro完整接力ZIP

用户2026-10-04要求网页Pro把实际制作成果放在一个可下载ZIP中，便于本地一次取得题包、Golden、reward和作者核验材料。这是网页到本地的接力形式，最终客户提交仍按适用交付文档整理。

接力ZIP沿用单批次根目录，题目目录继续保持合同结构；作者证据放题目目录外。默认结构为：

```text
<接力批次>/
├── 交付文档.md
├── <task_id>/
│   ├── instruction.md
│   ├── task.toml
│   ├── rubrics.json
│   ├── environment/           # 输入、技能、依赖和Dockerfile
│   ├── solution/              # solve.sh及golden_output/
│   └── tests/                 # 固定脚本、量表、提示词及__golden_output/
└── author_evidence/
    └── <task_id>/
        ├── local_handoff.md
        ├── material_manifest.json
        ├── golden/
        │   ├── generation-record.json  # 实际生成/导出记录及可取得的原始工具日志索引
        │   ├── pro_simulated_golden_review.json
        │   ├── reward.txt
        │   ├── reward.json
        │   └── reward-details.json
        ├── checks/            # 实际检查命令、脚本hash、退出码及完整输出
        └── ...                # 已制作的来源证据、核验脚本、样本及作者底稿
```

`solution/golden_output/`与`tests/__golden_output/`必须逐字节一致且符合交付物清单，题包中保留完整评分脚本。逐项自评字段与材料hash遵循[Golden接力](pro-golden-handoff.md)，用当前`check_pro_golden_review.py`核验全部ID、权重、方向、raw/value及复算分数。所有已生成、接力需要的作者材料一并收齐，按实际用途列索引，不要求补造未进行的检查、运行或轨迹。

本流程的作者reward来自Pro逐项自评及实际执行的代码聚合。完整可判时，`reward.txt`保存复算数值，`reward.json`保存同一数值，`reward-details.json`保存全部逐项证据、原始档位、归一化值、权重、方向和理由。两个JSON显式记录`mode=author_simulation`、`external_judge_executed=false`、任务ID及版本、评分文件与材料hash；与原始自评记录逐项及总分一致。聚合公式与固定`finalize.py`一致，固定模板本身按来源字节保留。无法判定、记录不完整或复算失败时保留原始失败结果，分数为null，不创建成功的数值reward.txt或补造达标记录。已有真实评分文件按原字节及实际来源留存于单独索引位置，不覆写。

作者评分文件仅放author_evidence，不复制成Oracle/候选回执。网页Pro制作Golden、逐项自评并保存真实生成/导出记录；金融本地核对后复用现成Golden，取得同冻结版本的真实Oracle预检及逐项评分证据。可按已有授权并行预跑Golden与三候选，实际Golden通过后统一评分候选。已有同版本有效Golden证据可以复用，作者自评和生成记录各按实际来源保留。医疗本地仍仅delivery_format_only，其他领域按本轮明确范围执行。未实跑的正式成绩及均分保留null，不填预测值。

`material_manifest.json`记录题包和作者文件的相对路径、大小及SHA-256，清单本身不计算自身hash。`local_handoff.md`说明真实task_id、版本、题目路径、自评路径、实际检查、本地执行范围及待办。接力ZIP根目录的`交付文档.md`只按客户要求写必要内容，不新增Golden来源、制作模型、自评方式或内部流程栏目；内部信息写入`local_handoff.md`及作者证据。

Golden制作过程的真实代码、动作、工具输出/退出状态和最终文件hash按[反馈复核](acceptance-feedback-review.md)收齐，已有记录尽量保留原件，缺失处如实说明。生成记录与逐项自评各有自己的用途；客户要求轨迹时，核对实际模型轨迹或该题允许的生成记录/不适用说明，不能只拿自评分替代。

先导出题包及完整作者材料，从最终批次目录用`check_rl01_archive.py <批次目录> --write-manifest <包外台账>/staging-manifest.json`记录全量文件，再制作实际接力ZIP并用`check_rl01_archive.py <最终.zip> --expected-manifest <包外台账>/staging-manifest.json`检查。核对作者索引、材料hash、reward一致性及Pro记录检查器结果；证据区JSON损坏、产物清单缺件和主分不符会报错，判词疑点列review_required提示待实际复核。归档检查不证明专业正确或客户验收。检查回执加入作者目录后，重新记录清单、封包和复验最终ZIP。最后的ZIP自身hash及最终检查回执放ZIP外，避免自引用改变hash。回复只需给这个完整接力ZIP的下载链接和SHA-256，必要状态按实际说明。

本地接力时留存原ZIP，再将`author_evidence/`转存私有台账，核对最终冻结任务及原始自评记录后继续授权流程。最终客户ZIP按合同整理题包、客户要求的模型产物、轨迹、评分证据及交付说明；实际三模型证据在运行完成后补入，客户未要求的作者私有材料留在内部。最终ZIP重新核验并记录新hash，网页接力ZIP的静态通过不代替客户所需的实际运行或验收。
