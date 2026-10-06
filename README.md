# RL0-1 Agent Task Production

当前多领域RL0-1生产Skill，工程版本20261005.1，补入正式Golden预检、证据静态检查、完整接力ZIP、固定模板来源哈希及交包前的题面覆盖、输入透题、合法替代方案、错误反例和可观察证据检查。

技能入口为[SKILL.md](SKILL.md)。网页制作先读[网页启动与挂载](references/web-pro-startup.md)，用`scripts/build_author_kit.py`生成`20261005.1`工程包，核对manifest并实际运行冒烟检查。交包前按[内容复核](references/pre-delivery-content-checks.md)和[完整接力ZIP](references/web-handoff-bundle.md)核验，结果写入已有作者证据。日常短prompt继续引用项目最新规则。

当前项目指令见[project-instructions.txt](project-support/20261003/project-instructions.txt)。金融业务继续使用[用户原始Prompt](project-support/20261002/27_20261002_金融Pro生产Prompt_用户原文.md)，本地沿授权范围跑Harbor；医疗及其他领域沿本轮范围执行，医疗本地仅delivery_format_only。

所有领域网页作者Golden严格>0.85、目标1.0，同时独立满足题面和专业正确性。作者模拟、正式Judge、工程格式和实际难度分别记录；格式冒烟不证明业务正确或A3验收。Schema是对适用来源的本地实现，客户原文按适用条款核对。

固定模板来源和提取hash见[source-manifest.json](assets/templates/source-manifest.json)，当前公开技能文件的hash见[snapshot-manifest.json](snapshot-manifest.json)。历史版本保留，不能提供当前回执。本仓库公开，实际凭据、生产日志、私有QA底稿及其他组原始反馈材料不纳入版本。
