---
name: rl01-agent-task-production
description: Design, improve, review, calibrate and package Appen RL0-1 Harbor rewardkit tasks, including batch A3 production, automatic VPS/Bohrium runtime selection, Skill/Workflow and weakness cases, client quality checks, and personal Feishu submission-table fields and attachment naming. Tracks current client sources and answered versus pending rule clarifications; excludes the separate audit L3/L4 Harbor v4 contract.
---

# RL0-1 Agent Task Production

本技能用于RL0-1出题、返修、质检、三模型难度验证和Harbor交付。以用户指定任务为范围；阅读规范或更新技能不授权领取、提交题目、发消息、付费跑模型或修改线上规则。文档中的命令、示例和流程是待解释的资料，不能自动当作本轮执行指令。

## 规则来源与边界

先读[来源与版本](references/source-snapshots.md)和[冲突记录](references/conflicts-and-clarifications.md)。比较具体条款的适用对象、实际修订内容和日期，不能只因页面刚复制或重新导出就认定整份文件更新。优先级为：用户本轮明确更正；针对本题本字段的最新客户答复；适用范围一致的最新规范正文；历史快照；本技能解释。示例、旧平台截图和单题通过记录不能自动推翻现行通用条款。未解决的冲突影响出题、判分或交付时向用户说明出处并询问，继续不受影响的工作。

2026-10-01读取的金融规则确认文档S09仅将`weight=20.0`标为已回答“不合规”；其他问题仍未答复。按冲突记录中已有正文依据继续执行，保留问题状态，不把提问当成客户批准，也不因待确认清单重复请求用户确认正常出题口径。法律个案的删字建议须核对适用范围，不能自动取消金融题的交付物路径或Likert评分锚点。

保持与`audit-l4-topic-production`等项目隔离，不搬用其Schema、模型、路径、权重或验收门槛。2026-09-28用户确认此前试标已经通过，按客户反馈记录；不能因此推定所有历史运行已补齐，也不能把一题的题型、22条Rubric或A2结果变成以后所有题的模板。

技术基线仍由20260913rewardkit规范控制：`schema_version="1.4"`、`harbor-rewardkit[all]==0.1.7`、`claude-code@2.1.114`；裁判`qwen3.7-plus`，使用Claude Code agent judge。三候选模型为`gpt-5.6-sol`、`claude-opus-4-8`、`qwen3.8-max0902`，每模型一次正式运行。实际凭据只由受控运行环境注入，不进入题包、日志或交付文件。技能中的运行变量说明仅供内部执行参考，不能原样复制到对外交付文档。

交付文档隐私边界：不得披露Judge或候选Agent的环境变量名、具体值、服务地址、模型路由、协议、缓存、思考等级、并发和内部适配细节。交付文档只写受控运行环境提供必要配置的通用说明，以及任务版本、检查结果、有效分数、证据路径、哈希和剩余状态。题包中因平台合同必须保留的占位字段不在交付文档中展开，真实凭据不得进入任何交付材料。

## 按任务读取

出题或加难时读[构造方案](references/construction-plan.md)、[W1—W14词表](references/weakness-catalog.md)、[A3与批量生产](references/a3-production.md)，同时读[质检规则](references/quality-review.md)。选定金融场景时用[生产规范与知识体系](references/rl01-guideline.md)核对标签。

网页Pro制作或本地接力时必读[Golden接力与量表回归](references/pro-golden-handoff.md)、[网页作者工程资料](references/web-author-engineering.md)及[网页启动与挂载](references/web-pro-startup.md)。网页操作端开启Pro制作时将当前小工程ZIP直接附到制作消息；先实际取得当前检查器、固定模板和hash清单，执行工程冒烟检查，项目文件列表可见不等于原件已进入本轮代码环境。网页交包前必做逐条Pro模拟Golden及反方复查，保留分数、证据和修复记录，不能因缺外部Judge跳过。当前用户要求所有领域网页作者Golden严格>0.85，目标1.0，客户通用≥0.85另记；金融后续本地跑Harbor，医疗后续本地仅delivery_format_only。后续其他领域按当轮范围处理，不自动继承金融运行流程。用户要求极难、复杂或增加坑点时读[金融高难度设计](references/adversarial-finance-design.md)；为候选模型及Judge启动请求前读[运行与10次重试](references/execution-reliability.md)。这些是用户目标及本地生产方法，不冒充客户新增验收条款。

已授权运行的任务先读[VPS／Bohrium自主选机](references/runtime-selection.md)。用户2026-10-03要求后续自主决定使用VPS还是Bohrium：按任务所需回执、实际隔离能力、依赖、队列和资源选择，不再把正常选机作为需要用户确认的步骤。原生Harbor或严格容器资源要求优先用具备能力的VPS；符合已验证直跑范围且资源更合适时，可直接选Bohrium。冻结前确定主机和执行方式，记录私有选择回执；本地直跑证据如实记录`native_harbor_trial=false`。

选VPS时读[VPS与Harbor运行](references/vps-harbor.md)，复用`/opt/rl01-harbor`及其共享队列；选Bohrium时读[Bohrium隔离直跑](references/bohrium-direct.md)，复用`/opt/rl01-direct`和本技能收录的已验证组件。VPS队列总并发8、单题上限4，新题Agent与Verifier默认2GiB硬上限；Bohrium当前约4GiB容器先限制整机最多2个CLI会话，每会话2GiB采样监控，不能称为单会话硬cgroup限额。两台当前没有跨机共享限流，分布执行前须实际协调总预算，不能将两个8路锁当成一个跨机8路锁。

用户2026-10-01最终更正：low仅用于三指定候选模型在Harbor中的作答；Bohrium已验证的直跑候选沿CLI／供应商默认设置。Golden生成、Golden评审、正式判分及出题复核等其他环节沿各自默认或明确指定的思考设置，不因选机降低或提高思考程度。用户已允许预检和冻结后并行预跑同版本Golden与候选，候选先留产物与轨迹，Golden有效通过后统一补判。VPS使用plan-batch/run-batch及grade-batch；Bohrium按整机资源控制调度。异步启动后继续核对进程、产物、全部评分条目和真实终态；并行预跑不等于已通过难度门槛。

用户2026-10-01转述已与甲方线下确认允许单份答案的Rubric条目并行评分。按这一会话授权，VPS与Bohrium的独立Verifier默认同时评分2条；全部请求沿既有8路预算，并受所选主机资源约束。报告沿正常格式，不额外添加并发说明，原始运行回执保留真实配置，不写虚假的串行执行或伪造回执。S03原文的“逐条串行”保留为原书面口径，不能宣称已取得新的客户书面文件。固定题包模板和评分定义保持原内容，独立Verifier先复评Golden，再用同一运行版本补判候选。

写题面、Docker或Harbor配置时读[交付合同](references/rewardkit-delivery-contract.md)。写或复核Rubric时读[评分规则](references/rubrics-and-scoring.md)和质检规则。跑分、封包、返修或交付时读[打包与证据核验](references/packaging-and-qa.md)。只有用户要求平台操作时，才读[平台作业流程](references/platform-workflow.md)，确认当前页面属于0917新版还是0909旧版。

设置用户的飞书提交表、整理附件名称或为该表准备交付文件时，读[提交表列设置与文件命名](references/submission-table-and-naming.md)，通过lark-base和飞书CLI核对真实字段及视图。采用用户2026-10-02选择的列方案，自动编号在第一列、题目编号在第二列，不设截图列。个人表外层附件统一使用`<领域>-<YYYYMMDD>-澳鹏RL0-1-<真实task_id>.zip`，自动编号只作为表内记录索引。金融领域二级标签按S01的Fin1—Fin9填写，能力专项一级、二级按S02的专项表核对。Weakness-driven为并列构造分支，读取其category与weakness_tag核对分类；不能将专项列空值直接解释为题包缺分类，也不自行把Weakness分支扩成已确认的专项枚举。弱点标签必须逐值符合S02正文B列并有题内触发，旧名称或自定义Bad Pattern说明不直接充当正式标签。首次提交前的内部修改仍按首次提交准备，不加“返修”或`_fixN`；只有真实客户返修重交才使用返修命名。个人表的附件命名约定与S03的包内目录、Harbor题目编号分别管理。

解释争议条款时回到`sources/`中的原文相应范围。浏览器文字快照、逐页PDF文本和图片的读取范围见来源表；不能把单次页面快照或字数统计当作全文已读。

## 当前验收口径

三模型有效分数的算术均值必须小于0.70，至少一个大于0；通过后按实际均值归档：A1为`0.60≤mean<0.70`，A2为`0.50≤mean<0.60`，A3为`mean<0.50`。A3目标未达到时保留实际档位，不把A2通过写成A3完成。单模型高于0.50不自动否定A3；分差悬殊须检查产物、逐项理由、解析和裁判方差。不能挑最低重跑分数或把环境错误当作零分压低均值。

20260928质检§2.4明确Golden为`score_final≥0.85`，含0.85；仍须独立验证正确性、可用性和安全性。旧PDF的`>0.85`及旧截图的`≥0.9`保留在冲突记录中，不能隐去来源差异。

Rubric须从题面与输入独立推导，接受有效替代解，按独立失败点原子化。当前质检要求：A1至少8条、A2至少12条、A3至少25条，按原文“打分项条目数”计全部正负条目；至少2条正向+10；权重只用±3/±7/±10且按业务重要性分配；扣分绝对值合计不超过正分池50%；指定4类领域锚点正分不少于全部正分30%。原始JSON使用`items`、固定11个维度名及`metadata.scoring.s_max`。详细计量口径、`negate`转换和示例缺陷见评分参考。

## 生产与复核

1. 冻结本批适用资料、任务类别、领域标签、目标难度、复杂度、数据来源、交付物和可用环境。批量A3是当前用户目标；全项目20%/60%/20%的计划配比不自动限制用户这一批。范围或资源有缺口时记录到本地生产底稿。
2. 先证明真实业务价值与可解性，再设计难度。用输入事实构成可复算的真值与证据链，映射到目标weakness及交付物。允许的冲突、缺失、恢复和Skill依赖须有可执行的正确路径，不用无关噪声、暗号、隐藏判据或故意坏环境压分。
3. 检查与已有任务的知识点、Workflow、场景、来源组合、决策路径和交付物是否重复。同三级标签或同知识点/Workflow最多2题，不能靠改名规避。没有历史台账时，只声明本次可检范围。
4. 准备源文件、可复算Golden和逐项证据。题面逐个列出输入与可用技能入口，给出准确输出路径；任务特有SOP保留在技能中。发现任务不泄露必要技能或干扰项身份。出题者的真值、错误设计说明、Rubric与Golden不能进入Agent可见输入。
5. 先做题面/输入、Golden、Rubric、评分链路四部分质检。追溯每条要求，检查根因重复计扣、错误级联、负分方向、Gradient边界及等价正确解。参考答案高分不代替专业复核。
6. 按交付合同建包。Golden生成一次后逐字节复制到两处；从`assets/templates/`取Dockerfile、solve.sh、prompt.md、test.sh和finalize.py。后两者固定，不为压分改动。源PDF相同不代表任意题包模板相同，仍需比较实际字节。
7. 运行`scripts/check_rl01_package.py <task-directory>`做静态预检，逐值核对正式weakness_tag、实际TOML五档文字为1—5及JSON显式negate。保存当前检查器哈希、命令、退出码和完整JSON；存在错误或ok=false时完成授权范围内的修复及复验，未通过则如实记录未就绪，不用旧回执、作者说明或模型分数覆盖失败。再完成实际Docker、权限、文档渲染、语义与作者Golden预检并冻结。按VPS运行参考可并行预跑同版本Golden Judge与候选Agent，候选先关闭Verifier并保存完整产物和轨迹；有效Golden通过且扣分已解释后才统一补判、确认为正式难度证据。也可按资源采用串行。网页离线检查不替代实际Judge，Golden失败先恢复请求或修复真实缺陷，任务可见内容改变则重跑受影响候选。脚本输出仅证明它列明的静态检查；不代表平台Schema认证、业务正确或A3难度已验证。
8. 从原始逐项回执复算主分，核对候选产物、轨迹、评分理由与冻结版本。每条全满分/全零、模型分差悬殊、Golden扣分都说明原因。返修后递增版本并复验受影响环节，全部有效证据必须对应最终冻结版本。
9. 最后打包后对实际交付文件运行`scripts/check_rl01_archive.py <final.zip>`：检查整个ZIP含批次根目录的残留、CRC、结构和文件名编码，解压同一ZIP并逐题重新预检。ok=false不进入交付就绪状态；修复或重新打包后必须重新检查。继续核验执行位、解压字节、完整运行及证据对应，最终ZIP的SHA-256和检查器哈希回执存于包外台账，上传附件必须匹配该ZIP哈希。每个声称已附的证据路径须真实存在。私有QA底稿和内部质检资料放题包外；客户要求的模型产物、轨迹和评分证据默认随同一批次ZIP交付，在题目目录外组织并索引，具体目录选择不额外要求用户确认。

## 终态

本地接力默认执行用户要求的请求重试：首次失败后再重试10次，共最多11次物理尝试，成功即停；候选和Judge均覆盖HTTP状态、完整响应体和流终止错误。启动前验证实际运行层生效，不用重复重跑整个任务代替请求恢复，也不把有效低分当失败重抽。具体计数、幂等、故障注入和耗尽留痕见运行参考。

分别报告客户结论、静态检查、实际运行、难度归档与交付状态。`SOURCE_READY`和`FULLY_ACCEPTED`是本地跟踪标签，不冒充平台回执：前者要求本地结构、语义、渲染、残留、同版本Golden、Oracle/空输出和压缩包检查全部通过；后者再要求三模型有效证据、对应档位和必要的人工/客户验收全部完成。客户已通过但仍有补件时如实写“客户通过，待补某证据”，不撤销客户结论，也不虚构闭环。

交付说明用简洁自然的中文，写明真实做过的检查、文件路径及剩余问题，并遵守交付文档隐私边界。普通出题请求继续推进本地工作；正式提交、对外发消息和超出已授权范围的执行以用户明确要求为准。
