# RL0-1-数据生产规范GuidelineV1.1

| **版本** | **日期** | **负责人** | **说明** |
| --- | --- | --- | --- |
| V1.0 | 2026年9月3日 | 予翊 | 默认为黑色字体。红色为强调内容。 |
| V1.1 | 2026年9月8日 | 予翊 | 根据新增的RL数据需求、平台操作流程等补充。<br>默认为黑色字体。红色为强调内容。 |

关联文档（如本文档进行调整，请对应调整以下文档部分，并通知文档作者）：

[《【专家版】Work 0-1数据生产规范》](https://alidocs.dingtalk.com/i/nodes/NZQYprEoWoxKPoqwCQzzkYMlV1waOeDk?cid=6752609716%3A6830999024&utm_source=im&utm_scene=person_space&iframeQuery=utm_medium%3Dim_card%26utm_source%3Dim&utm_medium=im_card&corpId=dingd8e1123006514592)

[《【专家版】Work 0-1数据生产规范（for内部专家）》](https://alidocs.dingtalk.com/i/nodes/93NwLYZXWyxXroNzCGojrpGQ8kyEqBQm?utm_source=im&utm_scene=team_space&iframeQuery=utm_medium%3Dim_card%26utm_source%3Dim&utm_medium=im_card&corpId=dingd8e1123006514592)

[《RL0-1-数据生产规范GuidelineV1.1--20260910 for外部供应商（旧版）》](https://alidocs.dingtalk.com/i/nodes/dQPGYqjpJYZnRbNYCKrnkybL8akx1Z5N)

[《RL 0-1标注数据质检Guideline》](https://alidocs.dingtalk.com/i/nodes/N7dx2rn0JbxOaqnACNeq1D0pWMGjLRb3?type=m&dd_user_keyboard=false&dt_editor_toolbar=true&dd_close=false&biz_ver=10&corpId=dingd8e1123006514592&rnd=0.4149816376720521)

[《外发版-评测题包交付规范（rewardkit）20260913》](https://alidocs.dingtalk.com/i/nodes/YMyQA2dXW7gYo6Mzc125zqgNWzlwrZgb?cid=77265624246&utm_source=im&utm_scene=team_space&iframeQuery=utm_medium%3Dim_card%26utm_source%3Dim&utm_medium=im_card&corpId=dingd8e1123006514592)

# 项目背景与使用范围

- 本文件定义该RL从0到1标注生产下数据的规格、格式、质量标准与验收流程。
- 适用对象：提供标注数据的所有数据生产流程。
- 面向对象：供应商、内外部专家、标注质检平台。
- 写给领域专家：

    - 作为对应办公场景的专家，你熟悉该领域的任务要求，熟悉该领域办公目标实现的产物标准。
    - 你的工作是根据自己擅长的领域，选择合适难度的任务，给出能对应办公场景、具备真实业务价值的**任务描述**，并且给出恰当的**参考文件**，以及对应该任务的**参考答案**。同时你需要针对该任务，给出一套能衡量任务做得好坏的**打分项**。
    - 我们会根据你给的打分项

        - ① 对你提交的参考答案打分，看得分是否足够高（正确率>0.85）；
        - ② 用3个模型执行你给出的任务，并用你给出的打分项打分，看难度是否足够高（三模型平均正确率<0.7）。

    - 此外，人工质检会重点考察题目真实性、参考答案合理性、打分项设计合理性、是否hack等异常作弊情况，一经发现，直接打回。

# 【重要！必须吃透！】标注流程及核心验收标准

- 虚线----：平台下一版本支持。

!\[image]([https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/a/6na3lJ8wkcGn05JD/e41c585e78164b6a92483b8e09f566660521.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/a/6na3lJ8wkcGn05JD/e41c585e78164b6a92483b8e09f566660521.png))

- ABC模型：GPT-5.6 sol / Opus 4.8 / Qwen3.8-max，可能会根据模型发版新增。

# 知识体系（平台二期支持）

- 0910 玉珍增加：
- 题目需要平均分布，以下一二级标签需要覆盖，如果需要补充二级标签也可以，需要提前说明。另外，目前的三级标签暂时为空，需要在出题的时候补足。题目出题需要分布均匀，不接受2道（2道本身可以）以上的题目是一个三级标签。

[请至钉钉文档查看「电子表格」](https://alidocs.dingtalk.com/i/nodes/vy20BglGWOxjGpq0Cv2QLm5nVA7depqY?iframeQuery=anchorId%3DX02mtrzhjle4hrrcgqv988&utm_scene=person_space)

# 难度分级

- 按照任务的**三模型平均正确率**，划分为易、中、难。
- **三模型平均正确率**：核心评价指标，选择模型A、B、C作为待测模型，取其产物经由打分文件打分后的平均分。

| **级别** | **产量占比** | **平均正确率** |
| --- | --- | --- |
| A1易 | 20% | <70% |
| A2中 | 60% | <60% |
| A3难 | 20% | <50% |

# 三件套

## 任务描述

- 自然语言描述任务场景、需要用到的材料、交付物要求。
- 包括任务说明，产出要求，硬约束（禁止项、文件名要求）必须用独立段落显式写出，不得隐藏在括号内。

## 参考文件

- 完成该任务/作业所需的真实输入（如 CSV、PDF、合同、日志）。
- 该任务场景下真实的交付物是什么，就用什么源文件。
- 必须为真实数据；不得要求模型凭空猜测法规条款、政策口径、职责分工或统计数据。
- 数量没有限制，总大小在20GB以内。

## 参考答案

- 由领域专家产出的标准答案，作为打分项自检基准。
- 与题目标注中规定的交付物类型、文件名、数量严格一致。
- 参考答案中的文件经过打分项判分后须满足 `**score_final ≥ 0.85**`；若 < 0.85 则不符合要求，需修正。

# 打分项

- 打分项 = 一个得分点/扣分点，即考察交付物，

    - 符合某一条在实际生产中**被要求或有正向收益的打分项，则得分；**
    - 符合某一条实际生产中**应该杜绝或避免的打分项，则扣分\*\*\*\*。**
    - **注意：不能在同一个打分角度上，既写得分点，又写失分点，造成双重得分或双重扣分。**

- 每条打分项，**描述一个具体的、可验证的评分标准**，包含以下字段：

## `**任务描述description**`：具体的评判标准描述。

#### 单条打分项要求

    - **原子性：每条打分项描述一个独立、明确、可验证**的评分点，仅检查一个方面（避免一条捆绑多个独立事实/多个可接受值）。
    - **准确无歧义**：表述完整、事实正确、依据可靠，使不同评分者能够形成一致理解。
    - \*\*可独立判断：\*\*打分项应包含作出判断所需的关键信息，不要求评分者额外推导、补充标准或进行二次判断。

        - 不推荐：收入实现了明显增长。
        - 推荐：收入同比增长了 65%。

    - **来源合理**\*\*：\*\*打分项必须来自以下内容，不能凭空增加“伪需求”：

        - 项目描述中的明确要求；
        - 参考文件中的明确要求；
        - 根据任务目标和使用场景可以合理推导出的隐含要求。

    - **有明确判定锚点**：禁止使用“语言流畅”“结构清晰”“内容专业”等空洞描述，应明确说明可观察、可验证的表现。

        - 不推荐：PPT 排版美观。
        - 推荐：单页正文不超过 150 字，文本无明显遮挡、重叠或溢出。

    - \*\*客观可验证：\*\*优先评价能够直接核查的事实、数据、结构和结果，避免直接使用“美观”“深入”“专业”等主观词语。确需评价主观质量时，必须将其转化为具体的可观察标准。
    - \*\*粒度合理：\*\*既不要把多个独立要求合并为一项，也不要将一个完整动作拆成大量无实际意义的小项。
    - \*\*打分对象：\*\*如果你的输出文件有多个，在打分项中明确给出本条的打分对象。

- **打分项之间的要求**

    - **互不重复、互不冲突**：不同打分项应评价不同内容，避免同一问题被重复计分，也不能出现判定标准相互矛盾的情况。

        - 例如，“公文是否专业、有条理且合规”应拆分为：

            - 文种选择是否正确；
            - 格式要素是否齐全，如标题、主送机关、正文、落款、发文字号等；
            - 请求事项是否明确，是否符合“一文一事”。

    - **具有区分度**：正分项和负分项的判定边界应明确；type为gradient项的，正分项要求能区分“部分满足”和“完全满足”，避免不同表现获得相同评价。
    - \*\*整体覆盖完整：\*\*所有打分项合起来应覆盖任务的主要目标和关键能力，并能够从不同维度评价交付物质量，不能遗漏关键要求。
    - \*\*权重体现重要性：\*\*同一份打分文件中，应根据各打分项对任务结果的影响程度设置不同的 `weight`，避免所有打分项机械地使用相同权重。
    - \*\*允许设置合理亮点项：\*\*可以评价项目要求之外、但基于常识会影响用户判断或交付质量的内容。此类要求应具有明确价值和合理依据，不能无限扩展任务范围。
    - \*\*判断结果稳定（鲁棒性）：\*\*同一套打分项由不同 Judge 或在不同时间多次评分时，结果应基本一致。若评分结果波动较大，应进一步明确描述、判定边界和示例。

## 主客观类型criterion_type：

- Objective = 可度量、可验证，仅凭回答本身即可作出明确判定；
- Subjective = 需要打分员的判断与语境解读（语气/质量/风格，或对某理由、断言、示例是否成立的判断）。
- 字段约束：criterion_type ∈ {Objective, Subjective}。

## 显隐式类型criterion_necessity：

- Explicit = 在 prompt 中逐字明文给出的要求；
- Implicit = 没有明说但从语境中必然推导出的要求。
- 字段约束：criterion_necessity ∈ {Explicit, Implicit}。

## 权重weight

- 分值（正分表示奖励，负分表示扣分/惩罚）。
- 不接受恶意负分、故意增加题目难度/降低分数的行为。
- 字段约束为weight ∈{+10、+7、+3、-3、-7、-10}，不能取任何其他值。
- 分值按下表取值：

| **级别** | **分数** | **含义** |
| --- | --- | --- |
| Critically Important | +10 | 不满足就是"答错大题"，核心要素 |
| Important | +7 | 明显增色，但不一定是最低标准 |
| Slightly Important | +3 | 细节/锦上添花 |
| Slightly Detrimental | -3 | 小错误、小跑题 |
| Detrimental | -7 | 重要错误，但整体还能用 |
| Critically Detrimental | -10 | 致命错误，直接毁掉答案本身，一票否决项 |

## 字段约束type

- 字段约束：type ∈ {Binary, Gradient}。选择标准如下：

| **Binary（二元判定）** | **Gradient（分档位给分，接受中间状态）** |
| --- | --- |
| 答案要么满足、要么不满足；中间状态无意义 | 存在程度差异，且这种差异对最终质量有意义 |
| 主观但可明确 yes/no（如"是否有提及不确定性"，提及 or 不提及） | 连续指标可以量化（数量、比例、偏离度） |

- 五档gradient 打分项 示例

```json
{
  "id": "R06",
  "description": "DCF 估值模型中使用的 WACC 取值应落在合理区间 [10%, 12%] 内，越接近得分越高",
  "dimension": "内容质量-数值与计算准确性",
  "criterion_type": "Objective",
  "criterion_necessity": "Explicit",
  "type": "gradient",
  "weight": 7.0
  "levels": {
    "1": "WACC 落在 [10%, 12%] 区间内",
    "0.75": "WACC 偏离合理区间不超过 ±1%（如 9.0%–9.9% 或 12.1%–13.0%）",
    "0.5": "WACC 偏离合理区间 ±1%–±3%（如 7.0%–8.9% 或 13.1%–15.0%）",
    "0.25": "WACC 偏离合理区间 ±3%–±5%（如 5.0%–6.9% 或 15.1%–17.0%）",
    "0": "WACC 完全未给出，或偏离合理区间超过 ±5%"
  }
}
```

- 二档binary 打分项数据示例

```json
{
  "id": "R17",
  "description": "计算2025年盈利净值为50万美元，相较于2024年盈利净值环比增长20%。",
  "dimension": "内容质量-数值与计算准确性",
  "criterion_type": "Objective",
  "criterion_necessity": "Explicit",
  "type": "binary",
  "weight": 3.0
}
```

## 评价维度dimension

:::
每条 打分项 需要有其所属评分维度。下面定义了综合考虑的维度，主要是引导大家设计打分项的时候思考全面，不遗漏重大维度，并且能有策略专注在价值维度上挖掘打分项。维度根据任务的要求来动态调整，不同的任务需要有区分度。
:::

- 根据下表给出 打分项 评价的一级维度和二级维度，二级维度可为空。
- 不同维度的权重设置要求

    - 内容质量、操作与交付安全应该总是较高weight
    - 对于ppt等设计类交付物，视觉美感与格式规范维度应该较高weight
    - 对于行业性比较突出的交付物，专业规范维度应该较高weight
    - 对于写作类交付物，结构与组织维度应该较高weight
    - 对于数学计算要求较高的交付物，比如金融场景，数值与计算准确性维度应该较高weight

| **一级维度** | **二级标签** | **主要检查什么** | **典型条目** |
| --- | --- | --- | --- |
| **指令遵循【必须】** |  | 检查 instruction 中**显式要求的任务内容与交付约束是否被完整执行**，包括范围限定、数量、命名、路径、格式、单位、精度以及明确要求包含或禁止的内容等。只检查 instruction 明确提出的要求；内容本身是否正确、专业、深入，归入对应内容质量维度 | 「结果文件名为 sales_summary.xlsx」「存放在 output/」「金额以万元为单位保留两位小数」→ 拆成 3 条 |
| **内容质量【必须】** | **结论正确性** | 检查基于已有事实、数据和分析所形成的**最终判断、结论、推荐或决策是否正确**，是否与证据一致，是否存在结论与数据相矛盾、判断方向错误或关键结论遗漏等问题。重点检查“最终得出了什么判断”，而非具体计算过程或论证深度。 | 数据显示 A 市场在增长率、利润率和竞争强度等关键指标上均优于 B 市场，最终推荐应为 A 市场，而不能错误推荐 B； |
|  | **数值与计算准确性** | 检查数值提取、公式计算、统计口径、单位换算、聚合方式、分母选择、时间范围、精度及容差等是否正确 | 合计行 = 各月之和（±0.01）；亿元/万元换算正确 |
|  | **专业规范** | 检查内容是否符合任务所属行业 / 领域的专业知识、规则、标准和通行实践，包括会计准则、法律规则、医学规范、行业标准、专业术语及业务口径等 | 「应收账款」按照适用会计准则正确分类；法律分析使用现行有效的法律规则而非已失效规定；财务模型中的 EBITDA、FCF 等指标使用符合专业惯例的定义与口径 |
|  | **分析与论证质量** | 检查产出中的事实、数据和引用是否忠实于输入材料及可验证的客观事实，不无依据地编造、篡改或混淆信息；引用和来源是否真实可追溯；跨文件处理时是否正确区分主体、版本、时间和统计口径。既检查 workspace 内事实，也检查任务涉及的外部客观事实。 | 「A 公司于 2016 年成立」这项产出表述能在 `industry_report.pdf` 表 3 溯源到确实有该项内容，或确实 A 公司是于 2016 年成立的，溯源不到即视为编造的幻觉内容，违反事实性。<br>学术调研需求中，给出看似真实的论文标题、作者、期刊和 DOI，但实际查不到，为幻觉内容，需要检查。 |
|  | **事实忠实性** | 检查产出中的事实、数据和引用是否忠实于输入材料及可验证的客观事实，不无依据地编造、篡改或混淆信息；引用和来源是否真实可追溯；跨文件处理时是否正确区分主体、版本、时间和统计口径。既检查 workspace 内事实，也检查任务涉及的外部客观事实。 | 「A 公司于 2016 年成立」这项产出表述能在 `industry_report.pdf` 表 3 溯源到确实有该项内容，或确实 A 公司是于 2016 年成立的，溯源不到即视为编造的幻觉内容，违反事实性。<br>学术调研需求中，给出看似真实的论文标题、作者、期刊和 DOI，但实际查不到，为幻觉内容，需要检查。 |
| **结构与组织** |  | 检查交付物的**信息架构和组织方式**是否合理，包括章节 / 页面结构是否完整、内容层级是否清晰、顺序是否符合逻辑、信息分组是否合理、关键模块是否缺失，以及文字、表格和图表是否放置在合理的上下文中 | 报告按「核心结论—分析依据—风险—建议」形成清晰结构 |
| **操作与交付安全** |  | 检查 Agent 在执行过程中是否安全处理用户已有文件和 workspace。不得误删、覆盖、破坏无关源文件，不得因编辑或格式转换造成数据、公式、页面或其他原有内容意外丢失 | 处理完成后 `data.csv` 仍完整可打开；被覆盖或删除则命中扣分项 |
| **安全合规** |  | 检查产出内容及执行行为是否满足隐私、数据安全、版权、法律法规及业务合规要求，避免泄露敏感信息、违规使用内容或产生明显误导、偏见及其他可能造成实际风险的问题。 | 对外报告不得直接暴露输入文件中的身份证号、手机号等敏感个人信息 |
| **超预期贡献** |  | 其他要求都满足之后，进一步提升交付价值的部分 | 事实二次核对、产物兼容性与易用性、防呆设计、指出 instruction 本身的疏漏以及更完善的交付物 |
| **视觉美感** |  | 交付物是否足够美观，比如排版、配色等内容是否让接手这份交付物的人感到欣赏, 比较偏主观。（仅针对交付物有美观度要求的情况需要配置得分点，普通任务不建议包含） | PPT的配色和排版是否美观等 |

## 打分项分布要求

- 打分项的分值设计应符合统一标准，能够真实反映各能力的重要程度。主要包括：

    - **领域锚点占比**：交付物内容质量维度（交付物内容质量下所有二级标签）锚点正分，占全部正分的 \*\*30%\*\*以上，表示本题对专业性有很高的要求，非简单指令遵循就可满分，要求有极强的领域知识理解。
    - **关键项占比**：每题至少包含 2 条 Critically Important（+10）评分项，模拟用户真实期望，给出最影响产物本身可用性的打分点。
    - **-10分项**：仅用于重大专业错误、幻觉、业务安全、合规风险等真正影响答案可信度的情形，不得滥用。

- 一般来说，指令遵循、结论正确性、分析与论证质量与事实忠实性这些维度总是需要的。

    - 对于行业性比较突出的交付物，应该覆盖专业规范维度。
    - 对于ppt等设计类交付物，应该覆盖视觉美感与格式规范维度。
    - 对于写作类交付物，应该覆盖结构与组织维度。
    - 对于数学计算要求较高的交付物，比如金融场景，应该覆盖数值与计算准确性维度。

# 元数据

- 领域、分级、难度、目标模型通过率预估、关键能力标签。

| **字段名称** | **题型** | **字段说明** | **是否必填** |
| --- | --- | --- | --- |
| 题目编号 | - | 系统自动生成 | 必填 |
| 所属领域 | 单选 | 通用办公/金融/医疗/法律，支持后续新增 | 必填 |
| 所属领域二级标签 | 单选 | 二级标签，参考3.知识体系 | 必填 |
| 所属领域三级标签 | 单选 | 待补充 | 必填 |
| 所属领域四级标签 | 单选 | 待补充 | 必填 |
| 评测的能力 | 填空 | 该任务能评测的具体专业能力 | 必填 |
| 难度等级 | 单选 | A1-A3 | 必填 |
| 任务说明 | 填空 | 为什么选择这个任务，真实性如何保障，真实场景中的交付物是什么 | 必填 |
| 所需工具 | 填空 | 完成任务所需办公工具/数据库（Word/Excel/PPT 等） | 必填 |
| 领域知识依赖 | 填空 | 完成任务所需的专业知识说明 | 选填 |
| 是否依赖VL | 单选 | VL即视觉-语言能力<br>是/否 |  |

# 得分计算

- **单题计分公式**：$\\text{Score} = \\frac{\\displaystyle\\sum\_{i \\in P} s_i \\cdot w_i ;+; \\sum\_{j \\in N} h_j \\cdot w_j}{\\displaystyle\\sum\_{i \\in P} w_i}$     $w_i > 0 \\quad (i \\in P),  P正打分项； \\qquad w_j < 0 \\quad (j \\in N)    ，N 负打分项$

    - $s正\_i = \\begin{cases} 1 & \\text{binary 正打分项命中} \\ {0,; 0.25,; 0.5,; 0.75,; 1} & \\text{gradient 正打分项实际档位} \\end{cases}$      $h负\_j = \\begin{cases} 1 & \\text{binary 负打分项命中} \\ {0,; 0.25,; 0.5,; 0.75,; 1}  & \\text{gradient 负打分项实际档位} \\end{cases}$

- **三模型平均分**：(score1+score2+score3)/3。

# AI机检&&人工质检标准

- AI质检题目质量skill
- 人工质检题目质量SOP
- 打分项生成skill
- AI质检打分项质量skill【缺】
- AI总分检查skill：

    - 参考答案得分>0.85 && 三模型平均分 < 0.7
    - 不同等级的平均分符合该等级要求，A1<0.7，A2<0.6，A3<0.5
    - 至少有一个模型得分

- 人工质检SOP：打分项、参考答案、hack行为等。

# 作业流程

## 任务配置@任务发起人

- 由任务发起人在晓天睿士上创建作业模版+发起任务：分领域-难度-题量批次（单批次50题）。
- 挂到预算项目上。（注意前置要申请生产预算，如果质检需要外部专家，需要一并申请质检预算）。
- 给领域专家开权限。

## 领取题目@专家

- 晓天睿士平台：https://dataai.alibaba-inc.com/siriser/expertBiz/taskManage?projectId=1023
- 进入页面找到RL0-1项目的卡片，按领域和难度选择，点进去领取题目。

!\[image.png]([https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/1d7cb254-4764-4b6b-8e17-6976b7ffbef4.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/1d7cb254-4764-4b6b-8e17-6976b7ffbef4.png))

页面内容配置

!\[image.png]([https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/6b649ea3-d0b5-4de5-9b5e-6de588673b04.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/6b649ea3-d0b5-4de5-9b5e-6de588673b04.png))

## 专家作业

- 默认页面
- 左侧全部待填写的信息

### 上传三件套

- 领取题目后，根据您的日常工作重点项目，整合三件套，在本界面上传题目描述、参考文件、参考答案。
- 上传完毕后，点击右侧【题目质量质检】

    - 不通过：根据修改意见返修，之后重新上传。

        - 若对【题目质量质检】有疑问，需仲裁，找运营同学。

    - 通过：点击右侧【AI生成打分文件】。

### 打分文件

- 在【AI生成打分文件】完成后，您可以在左侧Agent文件渲染里找到打分文件，您下载下来，在打分文件上修改。注意您需要在文件上新增列：

    - 【打分项处理】：选项为增加、删除、修改、保留。
    - 【处理理由】：给出明确的处理理由。
    - 【评分标准 description】：填写经过确认的评分标准 description。
    - 【客观 / 主观 criterion_type（Objective / Subjective）】：填写经过确认的客观 / 主观 criterion_type（Objective / Subjective）。
    - 【显性 / 隐性 criterion_necessity（Explicit / Implicit）】：填写经过确认的显性 / 隐性 criterion_necessity（Explicit / Implicit）。
    - 【维度 dimension】：填写经过确认的维度 dimension。
    - 【判定方式 type（binary / gradient）】：填写经过确认的判定方式 type（binary / gradient）。
    - 【分值 weight】：填写经过确认的分值 weight。
    - 【分档说明 levels】：填写经过确认的分档说明 levels。
    - 如果您需要新增打分项，直接写在新建的列中新增即可。

- **你要做的是逐条核对、修改**，让它准确反映“什么该得分、什么该扣分”，可以理解成教师阅卷时的评分标准。
- 完成后，您需要上传2个内容：

    - 【打分文件改动留痕excel文件】：保留以上所有内容，上传到该位置。
    - 【打分文件excel】：删除前面的【AI生成的打分项、打分项处理、处理理由】列，只保留您确认过的打分项列，生成一个excel，上传到该为止。

!\[image.png]([https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/014ec7d8-950c-4b27-8e00-5abb11f9c4b2.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/014ec7d8-950c-4b27-8e00-5abb11f9c4b2.png))

### 打分文件质检

- 上传【打分文件excel】完成后，点击右侧【打分项质量检查】。

    - 未通过：根据修改意见返修，之后重新上传。

        - 若对【打分项质量检查】有疑问，需仲裁，找运营同学。

    - 通过：点击【模型A运行结果】【模型B运行结果】【模型C运行结果】。

!\[image.png]([https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/3fdeeb24-9614-455f-a831-24bf12d8ed5f.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/3fdeeb24-9614-455f-a831-24bf12d8ed5f.png))

### 三模型产物跑分

- 模型ABC运行拿到结果之后，继续点击【模型A运行评分】【模型B运行评分】【模型C运行评分】。
- 评分需要满足：

    - 三模型平均分<0.7
    - 三模型至少有一个得分，即不为0

- 若不满足，则继续返修三件套、打分项。

    - 您可以在右侧Agent文件渲染中看到三模型的产物和具体的打分明细，来针对性参考去做返修。

- 若满足，则点击【标准答案打分】。

!\[image.png]([https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/26baf673-fba9-461a-8059-2f38f0fe5a0a.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/26baf673-fba9-461a-8059-2f38f0fe5a0a.png))

### 标准答案打分

- 标准答案打分需要>0.85
- 若不满足，则继续返修三件套、打分项。

    - 您可以在右侧Agent文件渲染中看到三模型的产物和具体的打分明细，以及标准答案的打分明细，来针对性参考去做返修。

- 若满足，则点击【综合评分】。

!\[image.png]([https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/d1996ffc-1ac4-4c32-b2ae-165e19be3f90.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/d1996ffc-1ac4-4c32-b2ae-165e19be3f90.png))

### 综合评分

- 点击综合评分生成最终报告。
- 不通过：则继续返修三件套、打分项。

    - 您可以在右侧Agent文件渲染中看到三模型的产物和具体的打分明细，以及标准答案的打分明细，来针对性参考去做返修。

- 通过：

    - 左侧划到下面补充题目描述信息。
    - 上传打分文件改动留痕excel文件。

!\[image.png]([https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/f4fd1be2-0cb4-41c0-a509-b4e1499201c7.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/f4fd1be2-0cb4-41c0-a509-b4e1499201c7.png))

### 补充题目描述信息

- 根据题目实际情况，对题目关键信息进行选择或补充。
- 难度等级：易/简单-A1、中/中等-A2、难/困难-A3。

!\[image.png]([https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/a2a141ed-d061-49f9-a2d0-6776a64c7499.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/a2a141ed-d061-49f9-a2d0-6776a64c7499.png))

### 提交

上述流程结束后，提交出题。

!\[image.png]([https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/5f0374a7-e496-416e-a6ca-92356c056bfa.png](https://alidocs.oss-cn-zhangjiakou.aliyuncs.com/res/4maOgX3K0Gre9lWN/img/5f0374a7-e496-416e-a6ca-92356c056bfa.png))

## 质检@质检员

- 质检后台https://dataai.alibaba-inc.com/siriser/expertBiz/dataReview?projectId=1023
- 质检规范：单独培训质检员。
- 注意：质检不通过的次数上限为3次。

## 验收通过并结算@任务发起人

- 任务发起人提交数据，需求方确认后，在平台上点击【最终确认】后，平台给专家结算。

# 上AP验证

- harbor格式[《外发版-评测题包交付规范（rewardkit）20262910》](https://alidocs.dingtalk.com/i/nodes/Obva6QBXJwxNZoMOCLqLZgaY8n4qY5Pr?utm_source=search&utm_medium=main_vertical&utm_scene=team_space)
- SOP from 渭雄。

# 数据交付

- 交付后需求方给验收报告。
- 验收通过后，若引入新模型发现部分题目难度不足（模型能力变强，题目无区分度，不具备训练价值），可重新提需再补训练集。

# 参考文件

- 需求文件[《RL数据标准》](https://alidocs.dingtalk.com/i/nodes/jb9Y4gmKWrx9eo4dC4P5ko39JGXn6lpz)[《Rubrics问题记录》](https://alidocs.dingtalk.com/i/nodes/ZX6GRezwJlzeYoPLF0bjllZzWdqbropQ?utm_source=im&utm_scene=team_space&iframeQuery=utm_medium%3Dim_card%26utm_source%3Dim&utm_medium=im_card&corpId=dingd8e1123006514592)
- [《rubric规范文档（refine&0-1项目都适用）》](https://alidocs.dingtalk.com/i/nodes/m9bN7RYPWdyrPBREcjzQ4e7nVZd1wyK0?cid=5758672947%3A6821650963&utm_source=im&utm_scene=person_space&iframeQuery=utm_medium%3Dim_card%26utm_source%3Dim&utm_medium=im_card&corpId=dingd8e1123006514592)
- [《work数据0-1生产Guideline-v20260827》](https://alidocs.dingtalk.com/i/nodes/oP0MALyR8kzGnoOwFDg3wgRXJ3bzYmDO?utm_scene=team_space)
