# Rubrics与评分

优先用20260928质检§2.3—2.4解释当前字段和验收；rewardkit§6控制可执行TOML、固定判分脚本和聚合。语义复核见`quality-review.md`，示例JSON有排版错误，不能直接复制执行。

## 原始JSON与TOML

原始`rubrics.json`使用对象根、`items`条目数组及`metadata.scoring.s_max`。每条包含`id`、`description`、`dimension`、`criterion_type`、`criterion_necessity`、`type`、`weight`，Gradient另含`levels`。按最新质检§2.3.2保留布尔`negate`并与原始权重符号一致：负权重为true，正权重为false。JSON的±3/±7/±10是带符号分值，`s_max`只合计正分。

`criterion_type`为Objective或Subjective，`criterion_necessity`为Explicit或Implicit。显式要求能逐字回到题面；输入材料/必然业务含义的来源也记录清楚，不因Golden出现而认定Explicit。`type`接受原文Binary/Gradient及示例小写写法，成套保持一致。五档levels必须完整为0、0.25、0.5、0.75、1，描述互斥且无空隙。单纯提取数值通常是Binary；连续偏离、比例或覆盖质量只有在中间状态有业务意义时才用Gradient。

本地作者序列化约定见`assets/schemas/rubrics.schema.json`：`levels`是对象，键必须逐字为`"0"`、`"0.25"`、`"0.5"`、`"0.75"`、`"1"`，值为非空判据字符串。数值正确的数组、`"0.0"/"1.0"`端点及`objectivity/visibility`字段别名不符合当前检查器格式。该Schema是对已读规范的本地工程约定，不冒称客户提供的官方Schema。用`scripts/render_rl01_config.py`从同一作者规格生成JSON和TOML，完整用法见[网页作者工程资料](web-author-engineering.md)。

Binary判据保持“判据为真时score=yes，为假时score=no”的原生二值输出说明；负项描述实际违规谓词，是否反转只由TOML的`negate`控制。业务文件中的JSON布尔字段可以继续使用true/false；不能把业务布尔值与评分输出枚举混写。生成器明确附上二值输出说明，作者离线复查仍要验证无违规和发生违规的判定方向。

多交付物时每条原始判据明确目标文件。转换TOML后ID集合、权重绝对值、正负方向及判据含义一一对应，不能只保证条数相等。JSON负权重转为TOML正权重加`negate=true`，绝不在TOML写负权重。

S09询问JSON/TOML是否完全等同，目前未答复。两者是不同表示：例如JSON的Gradient、负权重和0—1档位必须转换为TOML的Likert、正权重加negate和1—5整数档；追求逐字相同会破坏判分。当前格式依据仍是S06和S03，具体状态见[冲突记录](conflicts-and-clarifications.md)。

```toml
[judge]
judge = "claude-code"
prompt_template = "prompt.md"
model = "qwen3.7-plus"
timeout = 7200
mode = "individual"
weight = 1.0

[scoring]
aggregation = "weighted_mean"

[[criterion]]
id = "R1"
name = "R1"
description = "<单个独立判据及可核验口径> Deliverables to inspect: output/<准确文件名>."
type = "binary"
weight = 10.0
```

TOML的每条`name=id`，`description`必须带完整`Deliverables to inspect:`路径。只用`binary`或`likert`；Likert显式`points=5`并将JSON的1/0.75/0.5/0.25/0分别转换为5/4/3/2/1整数档。逐项独立Judge会话，不依靠其他条目提示；`[verifier].timeout_sec`大于单会话7200秒。

S03§6.3将individual进一步描述为“逐条串行”。用户2026-10-01转述甲方线下确认允许条目并行；按本会话授权，VPS独立Verifier默认以2条并发执行，同一条仍是独立会话、同一提示词与同一判据，全部条目完整后按原顺序聚合。运行适配在题包外，固定模板和原TOML不为并发改写；报告沿正常格式，原始回执真实。该授权不等于客户书面文档已更新，详细隔离、版本与对照验证见[vps-harbor.md](vps-harbor.md)。

S09对英文路径清单字样和锚点提出疑问，引用的是法律个案质检建议，尚未给出金融答复。当前按S03§6.2保留一份路径清单及一套档位，去除重复文字；不能将去重建议执行为删除判断所需信息，也不能据此放宽本地校验器。

量表转换必须落实到实际description文字，不能只设points=5。每条Likert统一用5行`1: …`至`5: …`，依次承载JSON levels的0/0.25/0.5/0.75/1原文；Judge-facing档位不得保留0/0.25等归一化标签，也不能在同一段让“1”同时表示满分和最低原始分。检查器会拒绝缺档、重档、归一化档和可识别的档位文字错配；改写后的语义仍需逐条比对。需要业务步骤编号时避免在同一description写成另一组`1:`样式评分行。

FIN8-DW-001回归说明：10条最高档理由被输出成raw=1，导致Golden从应有高分降至0.640212；量表修正后真实Golden为1.0。详见[Pro与Golden接力](pro-golden-handoff.md)。合成raw=5测试不能证明裁判看了实际文字后也会返回5；真实明细必须同时读reasoning/raw/value。

## 维度与分布

维度只能是以下11个名称：指令遵循、内容质量-结论正确性、内容质量-数值与计算准确性、内容质量-专业规范、内容质量-分析与论证质量、内容质量-事实忠实性、结构与组织、操作与交付安全、安全合规、超预期贡献、视觉美感。不沿用旧rewardkit表中额外的“内容逻辑性与分析深度”维度，也不自己创造名称。

每题根据真实需要覆盖一般必需的指令遵循、结论正确性、分析与论证质量和事实忠实性；金融计算题增加数值与计算准确性，行业题增加专业规范，写作题重视结构。视觉美感只在交付有美观要求时设置，不机械凑齐11类。

20260928质检的硬要求为：

- A1至少8条、A2至少12条、A3至少25条；依据§2.2.2，原文分布表缺C3行但不能据此取消下限。“打分项条目数”没有限定正分，按全部独立条目计数，包含正负项；不额外索取确认，不靠无业务价值的条目凑数。
- 正分中至少2条+10；重要性必须分档，不应全部同一权重。
- 领域锚点正分之和≥全部正分30%；分子只计“内容质量-专业规范”“内容质量-结论正确性”“内容质量-数值与计算准确性”“内容质量-事实忠实性”四类。分析与论证质量不计入该分子。
- 全部扣分绝对值之和≤全部正分50%。-10仅用于重大专业错误、幻觉、业务安全或合规风险。
- 所有权重只允许±3/±7/±10；TOML用对应正值及negate。旧自检表中的20.0由更新的质检允许集排除。

类别名本身不能证明专业锚点成立，须人工检查判据确实涉及领域正确性。不能给文件命名要求套“专业规范”以凑30%。条数达标也不替代原子性、来源、覆盖和区分度检查。

## 负分与独立判定

最新外部专家版要求负分description直接描述“违规事件发生”，不写“若…扣多少分”，尽量不用否定句，尤其双重/三重否定，不引用其他条目。语义只需按材料完成当前判定，不能要求裁判再猜标准。

同一根因不重复正负双扣，不把上游分数当下游开关。例：原始值提取、按自报值应用计算方法、按自报结果适用明示分类规则，分别判断；最终正确结论如须单独考察，核对其价值与根因是否独立。开放题允许多种有效结论及解法。

负项优先Binary。确有业务意义的程度差异时可使用现行rewardkit支持的负向Likert，每档必须独立可核验；不写动态weight或任意“满足几项加多少、不满足扣多少”的混合阶梯。

## Judge与主分

`tests/prompt.md`保留`{criteria}`、Material map、Reference-solution policy、Fairness anchor和技术工具提示。只评`/app/output/`，输入是证据，Golden仅用于校准。不能因为Golden满足就给候选分，也不能因等价正确解不同而扣分。不得在裁判提示里添加宽松/严苛引导。prompt加全部description小于100KB。

RewardKit将Likert归一化为`(raw-1)/4`；负项再翻转，所以负项明细value=1表示无违规，value=0表示违规完全成立。固定finalize.py按下式计算：

```text
S_max = Σ正项weight
numerator = Σ正项weight×value - Σ负项weight×(1-value)
reward = clip(numerator/S_max, 0, 1)
```

例如负向weight=7且value=0.25，扣5.25；无违规value=1不加奖励。复算以固定脚本和真实明细为准，不把RewardKit的审计`soft_score`当主分。`verifier_error=1`、`criteria_counted=0`、条目错误或缺失均为无效评分，不能计为有效零分。明细中的ID/名称、权重、negate与最终TOML逐项对应，所有汇总载体须一致。

Golden当前门槛为≥0.85；保留同版本Oracle和逐项理由。源PDF的>0.85和示例截图的≥0.9均已被当前质检的明确含0.85表述更新，仍在冲突记录中注明。
