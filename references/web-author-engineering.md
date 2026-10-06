# 网页作者工程资料

本参考解决网页作者读取旧模板、JSON字段别名和档位序列化导致的本地修复。工程版本为`20261005.1`，包含最终封包文件清单、证据JSON/产物/评分一致性检查、Golden真实生成记录及Pro逐项自评记录核验、[完整接力ZIP](web-handoff-bundle.md)规则，并按客户文档限定交付说明内容；固定模板继续按S12原始Markdown代码块及来源清单核对，保留法律条数建议提示。内容复核与作者证据方法见[交包前内容复核](pre-delivery-content-checks.md)。Schema与检查器是对适用合同的本地实现，不冒称平台官方Schema或专业验收。

网页制作先取得当前工程资料包和`kit_manifest.json`，逐文件核对hash，运行`scripts/author_engineering_smoke.py <包外测试目录>`。它用合成格式夹具实际执行生成器、目录检查器和最终ZIP检查器，并确认ADU端点键、BSI数组及CSE待确认模板三个错误会被阻断。`ok=true`只证明作者工具可读、可执行；夹具不能当作业务新题或A3证据。项目列表可见、文件名相同、检索到了摘要或旧检查器通过都不替代这一步。文件不能取得时先解决资源读取，继续不依赖它的研究；工程门槛未完成的包只能明确交付为待完成稿。

网页Pro制作Golden、逐项自评并保存真实生成/导出记录；金融本地核对后复用现成Golden，取得同冻结版本的真实Oracle预检及逐项评分证据。可按已有授权并行预跑Golden与三候选，实际Golden通过后统一评分候选。已有同版本有效Golden证据可以复用，作者自评和生成记录各按实际来源保留。医疗本地仍仅delivery_format_only，其他领域按本轮明确范围执行。网页作者自评严格>0.85、目标1.0，两遍评审与代码聚合保留真实证据。实际运行沿本轮授权，核对冻结版本和原始回执。

`assets/templates/task.toml`提供完整配置形状。`[task].description`非空，`keywords`机械为`[领域英文名,"office",难度]`，自由关键词放`metadata.tags`。S03字段表未将`tags`列为必填，本地作者模板保留它，缺失只警告。`environment_template`必须来自有依据的模板身份；不得留占位或pending confirmation。基础镜像名不单独证明平台批准，静态检查也不替代批准身份核对。

原始Rubric每条完整保留`id/description/dimension/criterion_type/criterion_necessity/type/weight/negate`。`criterion_type`只能是Objective/Subjective；`criterion_necessity`只能是Explicit/Implicit；不使用objectivity/visibility别名。Gradient的`levels`严格使用对象和以下字符串键：

```json
{"0":"零分判据","0.25":"四分之一分判据","0.5":"二分之一分判据","0.75":"四分之三分判据","1":"满分判据"}
```

数值相同的数组或`"0.0"/"1.0"`键不符合该本地序列化约定。完整结构见`assets/schemas/rubrics.schema.json`，解析后TOML结构见`assets/schemas/task.schema.json`；跨文件、池算术、字段语义和真值还要实际核对。

从一份包外`author_spec.json`生成配置，形状为：

```json
{
  "task": {"schema_version":"1.4","task":{},"metadata":{},"agent":{},"verifier":{},"environment":{}},
  "rubrics": {"metadata":{"scoring":{"s_max":0}},"items":[]},
  "deliverables_to_inspect": {"R1":["output/<准确文件名>"]}
}
```

此处空对象仅说明输入形状，制作时填完整字段和真实条目。`task`填模板解析后的完整配置，`rubrics`填符合Schema的原始规则，路径映射逐条列全，放作者证据区。运行：

```bash
python3 -B scripts/render_rl01_config.py author_spec.json <task_id>
python3 -B scripts/check_rl01_package.py <task_id>
python3 -B scripts/check_rl01_archive.py <最终批次目录> --write-manifest <包外台账>/staging-manifest.json
python3 -B scripts/check_rl01_archive.py <最终题包.zip> --expected-manifest <包外台账>/staging-manifest.json
```

生成器机械展开required交付物的artifacts，生成`task.toml/rubrics.json/tests/rubrics.toml`。它保持业务判据、带符号JSON权重和显式negate；Gradient按同一levels逐行映射为TOML的1—5，负项只反转一次。Binary明确score=yes/no，与业务JSON中的true/false分别表达。生成配置成功不等于完整题包通过；修改后重新生成已有路径时显式加`--overwrite`。

`tests/test.sh`和`tests/finalize.py`从固定模板逐字节复制，含注释、缩进和末尾空行。工程包必须包含`assets/templates/source-manifest.json`；检查器固定已核对的S12来源与模板哈希，来源清单缺失、assets缺失或基线变化均报template-source错误，题包副本变化报fixed-template错误。离线包只带清单及固定哈希，私有规范原文留在本地技能。最后在实际交付ZIP上执行当前归档检查，exit_code=0且ok=true后才写格式通过；保存两个检查器hash、命令、完整输出、工程版本和最终ZIP hash于包外。法律25/30/35条建议不足只提示，通用条数硬门槛另核对。每条warning解释实际适用性。网页26号等旧快照只能作为历史原文参考，不能提供本次当前工程通过回执。

个人表外层附件采用`<领域>-<YYYYMMDD>-澳鹏RL0-1-<真实task_id>.zip`，自动编号只作表内索引。金融原始出题Prompt可以保留，工程实现按本参考和本轮更正执行；领域分类、专业真值和正式客户来源仍按适用原文核对。
