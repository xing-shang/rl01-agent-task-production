# VPS上的Harbor运行

这是用户2026-10-01配置的VPS后端。用户2026-10-03已将后续选机改为[VPS／Bohrium自主选择](runtime-selection.md)，本页保留VPS的具体运行与优化策略。VPS为`76.13.21.51:23450`，用户`root`；SSH别名为`76.13.21.51`，通过`ssh-skill`连接。实际密码和API密钥只留在受控凭据文件中，不能复制到Skill、题包、轨迹或日志。

## 环境与并存

独立运行前缀为`/opt/rl01-harbor`，Python虚拟环境为`venv/`，命令为`bin/harbor`、`bin/rewardkit`、`bin/claude`和`bin/rl01`。手动启动原生Claude时用`bin/claude-rl01`，会加载隔离的配置目录。固定Harbor`0.23.0`、`harbor-rewardkit[all]==0.1.7`、Claude Code`2.1.114`；Node为`22.23.3`，用于隔离安装的CLI。Python依赖锁定读回保存在`receipts/python-freeze.txt`。这是本机运行版本，不宣称客户指定Harbor必须为0.23.0。

VPS实测2核、约8GB内存、96GB系统盘。2026-10-01配置时，已有`FIN1-CB-001`和`FIN1-PPA-001`相关Harbor进程及容器，CPU负载约6至7。后续连接先执行只读doctor和容器检查，再决定新作业能否启动。安装使用nice15和ionice3；运行中session的进程、工作目录、全局Python包、Docker配置及现用镜像均不用于安装替换或清理。

新运行、上传任务与回执分别放`runs/`、`tasks/`、`receipts/`；每次运行用新目录，记录源包哈希，保留原始task.toml，再冻结应用本次资源设置的运行副本和哈希。既有工作目录`/root/fin1-cb-001-runs`和`/root/rl01_runs`由其原会话维护。不要对它们运行恢复、改配置、补评分或清容器。2026-10-01按用户的大批量需求改为共享队列；发现其他Harbor不再一律返回VPS_BUSY。旧作业继续由原会话维护，新任务从空闲槽位启动，不接管旧作业。

用户2026-10-01将后续新题的Agent、Golden共享Verifier及独立补判Verifier默认内存上限指定为2GiB，即`memory_mb=2048`。这是容器按需使用的硬上限，不是预留内存。plan和plan-batch在冻结前设置运行副本的environment.memory_mb及显式Verifier环境的memory_mb，原task.toml保存在运行目录的source-task.toml；manifest记录源包哈希、调整字段和有效资源。资源变化进入Agent可见哈希，2GiB下生成的产物必须在对应版本补判，不能把8GiB旧轨迹改成2GiB的新运行证据。已冻结运行按其原资源继续执行。

调整依据是本日对存活容器的只读采样：两个金融候选的cgroup生命周期峰值约442.4MiB、476.5MiB，独立Verifier约512.6MiB，均无OOM；峰值含页缓存。此样本支持普通金融题先用2GiB，不能覆盖大型Office、图像或大表处理题。确有更高需求时，在新plan或plan-batch指定`--memory-mb 4096`等值，并在运行说明记录依据；遇到OOM保留失败回执，调整资源后重新冻结及生成受影响候选，不能将OOM当成有效零分。

## 缓存与low

用户2026-10-01最终更正：low仅用于gpt-5.6-sol、claude-opus-4-8、qwen3.8-max0902这三候选模型在Harbor中的作答。Golden生成、Golden评审、正式判分及网页Pro出题/复核等其他环节沿各自默认或明确指定的思考设置，不因本项降低思考程度，也不擅自指定high。候选的Harbor Claude Code选项为`reasoning_effort=low`，同时设置`CLAUDE_CODE_EFFORT_LEVEL=low`。通用原生CLI配置不强制low，候选CLI沿该阶段的显式选项执行。不同网关模型名可能不被CLI识别为支持effort的模型，因此候选代理在实际Messages请求设置`output_config.effort=low`；Golden与regrade代理传`effort=None`，保持请求已有的effort或默认行为，不补造low。新manifest的effort_policy分别记录candidate=low、golden/judge=provider_default。候选的Verifier先关闭，因此候选代理不承载评分请求。不靠`MAX_THINKING_TOKENS`冒充low，也不改变模型ID；Qwen后端是否支持这一参数以实际网关行为为准。已运行或冻结的批次保留其真实配置与回执，更新脚本不等于旧worker已热更新；在旧worker自然排空后加载新代码，不能中断其他session为本次偏好更正重跑。

隔离的原生Claude配置位于`claude-config/settings.json`，权限0600，目录0700，包含用户指定Anthropic网关与认证和禁用非必要流量设置。Harbor的Agent与Judge容器必须显式注入这些运行设置；宿主机文件不会自行传入容器。每个运行单元使用仅绑定Docker bridge的临时认证代理，真实上游密钥留在宿主机进程中；代理配置和轨迹只有一次性本地代理令牌的环境占位符。通过Job的extra_allowed_hosts补入这一个运行网关地址，以便allowlist任务访问模型通道；任务其他网络规则仍由冻结配置控制。各代理共享state/api-slots文件锁，所有新入口的上游请求合计最多8个。VPS的INPUT默认DROP曾导致容器访问私有代理超时；每个代理为其私有IPv4和实际临时端口添加只匹配docker0/br-网桥的INPUT规则，关闭代理即删除，worker重启清理进程已退出的残留。规则带独立注释，不改既有防火墙策略或SSH端口；不开放公网接口。

保留三种缓存：Docker层和预构建镜像、`cache/pip`与`cache/npm`依赖下载、供应商提示词前缀缓存。Harbor默认`force_build=false`，Docker启用BuildKit；优先重用已核对的同版本依赖层。输入文件COPY放在昂贵依赖安装层之后，修改某题输入不应重复安装整套Office或Claude Code。缓存目录不能放进题包或作为Agent答案；每次Agent的输入、输出和会话目录仍须独立。

本版Docker backend结束trial会执行项目自己的`down --rmi local`，默认生成的未标记镜像可能随容器被删除。队列在启动模型前先给冻结Agent环境建立`rl01-agent-runtime:<task-digest-prefix>`缓存标签并记录image ID，保留同版依赖层，后续独立Verifier继承这份干净的Agent基础环境。同版已缓存镜像直接复用，构建由state/build.lock串行协调，避免跨题同时重复安装；已缓存的题目可直接继续，不等待其他题的冷构建，构建也不长期锁住运行状态文件。大文件哈希分块读取，避免8路检查同时把整文件载入内存。不得把包含Golden的Verifier镜像反用给Agent。该预缓存不修改题包的instruction、input_files、Dockerfile或task.toml，实际运行仍使用冻结题包并记录调度配置。

本次发现VPS宿主机可解析并下载依赖，而Docker构建默认网络出现DNS transient error。使用`assets/vps-build-network.yaml`为新作业指定`build.network=host`，借宿主机解析下载；helper会将其加入本次extra_docker_compose。它只配置构建阶段，Agent运行网络仍遵守冻结任务的network_mode和Harbor策略。不能为解决构建DNS修改全局Docker daemon、系统DNS或重启已有session；外层Job返回0也可能有构建异常，必须查看每个trial的exception_info。

设置`DISABLE_PROMPT_CACHING=0`及三个分模型开关为0。保持模型、effort、工具定义和稳定提示词前缀一致，保留原始`cache_control`及`anthropic-beta`头。以真实`usage.cache_read_input_tokens`和`cache_creation_input_tokens`核验命中，不能从本地缓存目录非空推定节约了API token。不同候选模型不共享模型缓存，重复Judge前缀可在同模型、同路由实际支持时获益。默认使用该固定CLI版本的缓存TTL；新文档的`CLAUDE_CODE_PROMPT_CACHE_TTL`等要求2.1.242以上，不给2.1.114照抄新开关或默认强制1小时。

## Pro接力、正式Golden与三模型

用户已确认最终交付按文档保留真实Golden预检。网页Pro负责制作答案和作者自评；金融本地核对题包、环境和记录后冻结版本，默认安排现成Golden的Oracle预检与三候选作答，真实Golden通过后统一评分候选。候选保存实际产物、轨迹、config/result/lock和artifacts/manifest.json；已有同版本有效Oracle回执先核对复用。

plan的--pro-review和plan-batch的--pro-review-dir导入完整作者记录并冻结其hash，默认golden_review_mode=formal_golden、formal_golden_required=true，保留golden.json和1个Oracle+3个候选单元。作者评分不写成Oracle回执。只有用户明确安排候选阶段时额外使用--skip-formal-golden；该模式需完整作者记录，golden_valid保持false，并标最终Golden预检待补。

首次候选只生成一遍，按实际失败恢复请求或原产物评分。规则含义、权重或Golden改变时更新作者评审及评分版本，验证该版本真实Golden再统一补判；Agent可见内容或环境改变则重跑受影响候选。队列仍共享8槽、单题最多4槽，逐题保留冻结版本及真实有效记录。医疗不因本参考扩大本地运行范围。

Harbor0.23.0的`verifier.disable=true`能只跑Agent，`harbor trials regrade`能只补判已记录产物。regrade要求独立Verifier：运行副本的`[verifier] environment_mode="separate"`，并有能启动`/tests/test.sh`的Verifier环境。本机Docker backend实测仍在`tests/`寻找环境定义，单独设置separate不会自动复制`environment/Dockerfile`；须提供`tests/Dockerfile`或已验证的Verifier docker_image。Dockerfile必须包含所需依赖、`COPY . /tests`及预期输出目录。需要适配时在题包外建立运行副本，记录源包hash、Agent可见内容hash和适配diff；固定test.sh与finalize.py逐字节保留。运行副本保留原task.name或原目录basename，否则regrade会报Task name mismatch。独立Verifier恢复产物到原路径的能力先用无模型smoke核验；不能仅凭CLI帮助就认定业务题已可重评。

Oracle执行需要bash，即使solve.sh写了`#!/bin/sh`；无bash的极简Alpine会留下exit-code.txt=127而Job外层仍可能返回0。不得只看Harbor退出码。Agent退出状态、预期产物实际存在性和artifacts/manifest.json逐项核对；status=failed须调查真实未生成与收集故障，不能直接当作可用零分。CPU字段和override_cpus在本版Schema只接受整数，不填写0.1一类小数配额。

Harbor0.23.0会省略trial配置中的默认字段，Oracle的agent也可能完全省略；来源核验用已安装AgentConfig解析默认值，不能据字段缺失拒绝真实Oracle补判。Oracle成功时可没有exit-code.txt，失败时才写该文件；核对exception_info、实际产物及收集状态，并在文件存在时检查非零退出码。

## 单份答案的条目并发

S03§6.3第30页原文将individual描述为“逐条串行”。用户2026-10-01转述甲方已线下确认允许条目并行，授权本VPS后续采用该方式。此授权来自本会话，不是客户书面规范的新版本。报告沿用正常字段和格式，不额外新增并发说明；运行配置、日志和回执按真实执行保留，不将其描述成串行，也不改客户原文、题包模板或历史回执。

新plan和plan-batch默认--judge-workers 2，每个独立Verifier最多2个裁判会话，整台上游请求共享8路。--judge-workers 1可准备原生串行版本；旧manifest没有judge_execution时按串行处理。默认模式在独立Verifier版本上先取得有效Golden，再补判同版本候选；明确候选阶段-only模式单列待补。

assets/vps_parallel_rewardkit.py只替换RewardKit0.1.7的individual调度，提示词、schema、Claude Code调用、解析与聚合仍用其原实现。原始顺序汇总全部ID、权重、raw/value与reasoning，任何缺项、解析失败、取消或超时沿固定finalize.py判为不可用。确定性模拟裁判的串并行对照只验证调度和汇总，不证明真实模型两次评分一定相同。

每条裁判使用bubblewrap创建独立PID、临时目录、Claude配置和可写工作区；输入与交付物在相同绝对/相对路径只读挂载，避免互相改写或读取前一条会话。可信Verifier调度进程需要SYS_ADMIN及其单个容器的AppArmor/seccomp例外来建立挂载命名空间，裁判子进程启动前丢弃全部capability；不配置privileged或Docker socket，不修改Agent沙箱及主机策略。固定test.sh、finalize.py、prompt.md和rubrics.toml逐字节保留，额外运行文件只在题包外的Verifier副本，不能把带Golden或裁判程序的镜像用于Agent。

plan将本次驱动和Compose策略复制到judge-runtime/并记录哈希；prepare-verifier和队列启动前核对，驱动更新只影响新运行。2GiB限制内先采用2条并发；不支持的MCP或自定义Judge cwd明确报错，可准备--judge-workers 1的新运行。请求重试与供应商缓存仍由原链路控制；low仅用于三候选模型作答，Golden及判分等其他环节不强制low。每条会话的真实起止记录保存在Verifier的criterion-runtime.jsonl供内部核验，客户要求的逐项分数和理由按原格式交付。

## 操作入口

先通过ssh-skill读回：

```bash
python3 ~/.codex/skills/ssh-skill/scripts/ssh_execute.py 76.13.21.51 "/opt/rl01-harbor/bin/rl01 doctor"
```

后续获授权跑某题时，先按ssh-skill上传最终题包到`tasks/<task-id>-<digest>/`，再准备独立运行目录：

```bash
/opt/rl01-harbor/bin/rl01 plan /opt/rl01-harbor/tasks/<task-id>-<digest>/<task-id> --pro-review /opt/rl01-harbor/author-reviews/<task-id>.json
/opt/rl01-harbor/bin/rl01 run /opt/rl01-harbor/runs/<prepared-run>
```

plan执行源包静态和Pro记录核验，应用默认2048MiB或显式--memory-mb，再检查并冻结运行副本与Compose策略，不调用模型。source-task.toml保留源配置，资源适配不改作者已检查的题面、输入、Golden及评分材料。默认run将1个Oracle及3个候选单元入队，由后台dispatcher执行；重复提交复用登记单元，各单元原生并发为1、整任务重试为0。返回QUEUED_ASYNCHRONOUSLY不代表完成。实际使用前核对服务器已同步本技能的check_pro_golden_review.py、vps_harbor.py和vps_queue.py；本地更新不等于运行中的worker已加载新代码，按原有排空方式加载，避免干扰既有会话。

一次准备和运行多题：

```bash
/opt/rl01-harbor/bin/rl01 plan-batch /opt/rl01-harbor/tasks/<batch-directory> --pro-review-dir /opt/rl01-harbor/author-reviews/<batch-directory>
/opt/rl01-harbor/bin/rl01 run-batch /opt/rl01-harbor/batches/<prepared-batch>
/opt/rl01-harbor/bin/rl01 status
/opt/rl01-harbor/bin/rl01 status /opt/rl01-harbor/runs/<prepared-run>
```

plan-batch接受多个明确题目目录或一个批次，直接子目录须有task.toml；Pro记录目录中每题文件名为<题目目录名>.json，先核验全部记录再准备运行。每题独立manifest，批次只索引这些运行。多session共享state/queue.sqlite3和8槽，--concurrency 2或3表示单题同时运行上限。status显示队列、worker心跳、可用槽位与资源等待原因，全局最多50条，指定run查看该题全部单元。

旧入口的“发现任意Harbor就等待”已经移除。8是通过rl01新入口提交的多session共享上限；既有未纳管session的Agent与独立Verifier容器只用于观察，不按容器个数强制扣减新槽位。实测旧session有4个容器时CPU负载约0.4、可用内存约5.5GB，按容器数预留会错误地阻止新题启动。新作业按实际资源余量安排，CPU负载用于观察，不单独把所有题拦住。可用内存低于1536MB、空闲磁盘低于15GB或无法读取容器清单时暂停启动新单元，资源恢复后自动继续。已有单元按冻结的CPU、内存和超时继续执行。新Compose策略设cpu_shares=128，新worker为nice15/idle I/O，使旧session在CPU竞争时有更高相对优先级。未纳入队列的旧作业不能被强制限流，其占用变化由容器清单观察，不宣称已改造其模型请求。

后台队列跨进程事务领取槽位，按题轮转。控制进程异常重启时，未开始单元继续排队；已开始单元保留INTERRUPTED或ORPHANED并要求核对，存活的孤儿作业仍占槽位，不自动重跑候选。请求重试仍由代理承担11次物理尝试，不能用队列重放生成代替请求恢复。后续更新worker代码前查看status，已有dispatcher仍须自然排空后重载，不能停止其他session。2026-10-01由4槽切换8槽时使用独立dispatcher.lock和rl01-harbor-dispatcher.service接管调度；旧rl01-harbor-queue.service只停止领取新单元，已有线程、代理和Harbor进程继续至自然结束。队列新增owner_pid/owner_start记录实际控制进程，恢复时保留仍由存活控制进程维护的RUNNING单元，避免误标孤儿或重复运行。新dispatcher按SQLite里全部RUNNING/ORPHANED单元合计核对8槽，旧单元同样占槽。运行中的任务hash、已保存分数、轨迹和产物保持真实；新的槽数及交接回执单独记录。

多题完成候选生成并核对已导入的Pro记录后，可以整批补判：

```bash
/opt/rl01-harbor/bin/rl01 grade-batch /opt/rl01-harbor/batches/<prepared-batch>
```

默认grade-batch复用干净Agent镜像并建立独立Verifier，在当前评分版本取得有效Golden后放行候选补判，共享8槽。明确使用--skip-formal-golden的候选阶段仍标最终预检待补。结果记SCORES_READY_REQUIRES_REVIEW，继续复算、专业复核和难度归档，不因队列结束就写FULLY_ACCEPTED。

单题手工补判先核对缓存镜像ID和输入版本，再准备独立Verifier副本；helper记录实际image ID、保留任务名及Agent可见内容并建立tests/Dockerfile。实际候选补判使用：

```bash
/opt/rl01-harbor/bin/rl01 prepare-verifier <prepared-run>
/opt/rl01-harbor/bin/rl01 regrade <candidate-trial> --task <prepared-verifier-task> --run-dir <prepared-run>
```

默认正式模式中，新建独立Verifier须先核对该评分版本Golden；对应命令为：

```bash
/opt/rl01-harbor/bin/rl01 regrade <oracle-trial> --golden --task <prepared-verifier-task> --run-dir <prepared-run>
```

补判异步入共享队列，拒绝Agent可见内容改变、Pro记录或评分材料不匹配、shared-mode Verifier；正式Golden模式另核对Golden评分版本。helper不把退出码0当有效分数，按完整Rubric计数、原始明细、固定finalize.py和verifier_error核验。评分材料改变时更新同版作者记录，并取得相应真实Oracle回执后统一补判候选。

`vps_request_proxy.py`缓冲完整响应并识别HTTP、JSON错误及SSE终止，候选和Judge同用最多11次物理尝试。成功立即返回；预算耗尽返回明确的终止错误，以阻止外层SDK把整个预算重新重复。Harbor整任务重试为0。`test_vps_queue.py`验证多题轮转、跨进程8槽上限、重复提交、失败释放、孤儿恢复和逐题Golden依赖；`test_vps_runtime.py`使用本地假上游验证第11次成功、持续失败、HTTP200错误、半截流、body超时、认证拒绝及low/cache透传，不消耗模型额度。实际代理请求审计位于运行私有目录，记录payload hash、尝试计数和usage，不记录提示词、回答或密钥。

验收回执以VPS的`receipts/`和本次工作目录`rl01-vps-setup-20261001/`读回为准。环境安装、mock验证、无模型Harbor smoke及真实模型评测分别记录，不相互替代。

来源核对于2026-10-01：[Claude Code模型配置](https://code.claude.com/docs/en/model-config)、[提示词缓存](https://code.claude.com/docs/en/prompt-caching)、[Harbor regrade源码](https://github.com/harbor-framework/harbor/blob/main/src/harbor/trial/regrade.py)。实际参数和行为以本机固定版本代码、schema及smoke为准。
