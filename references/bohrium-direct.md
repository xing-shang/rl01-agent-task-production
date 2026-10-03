# Bohrium隔离直跑

这是2026-10-02至2026-10-03在用户提供的Bohrium容器上验证的执行方式。用户已允许直接用Claude Code与RewardKit作答、判分，并在2026-10-03要求后续按[runtime-selection.md](runtime-selection.md)自主选择VPS或Bohrium。此页为内部运行参考，不复制到客户交付文档。

## 主机与已验证基线

SSH别名为`bohrium-rl01`，对应`qqej1495066.bohrium.tech:22`、用户root；通过`~/.codex/skills/ssh-skill/`的Python工具连接。实际密码只留在受控SSH配置中，不写入本技能。独立前缀为`/opt/rl01-direct`，真实模型配置在其`private/runtime-settings.json`，权限0600；只核验权限和存在性，不打印值。

2026-10-03只读复查为Ubuntu24.04运行环境、x86_64内核5.10.134、cpuset=0-1、父cgroup内存上限4190109696字节（约3.90GiB），没有Docker socket。Python3.12.4、Claude Code2.1.114、Node22.23.3、Bubblewrap0.9.0、RewardKit0.1.7、LibreOffice24.2.7.2和常用文档解析库已经安装。运行时以实时probe和包版本读回为准，不用宿主机MemTotal估算可用容量。

此模式完成了FIN4-WDS-001三候选作答及33项有效评分、同版本Golden1.0和空答案0.0；GPT额外运行也完整完成。现有隔离探针17项通过，响应头／响应体／SSE故障注入验证同一请求最多11次尝试。这些记录证明该本地模式可执行，不代表原生HarborTrial、平台环境模板批准或任意后续任务都已受验收。

## 可复用组件

已验证组件收录在本技能的`scripts/bohrium_runtime/`，SHA-256见该目录的`source-sha256.json`：

- `direct_isolation.py`：逐会话隔离、受控模型通道、输入／输出哈希、资源监控及回执。
- `direct_judge.py`：调用RewardKit0.1.7原提示词、schema、解析与聚合，仅调度独立criterion会话，默认2条。
- `reliable_proxy.py`与`vps_request_proxy.py`：完整响应校验、11次请求预算和等待期间的连接保活。
- `sandbox_entry.py`：可信初始化、最小proc视图、权限丢弃、seccomp及会话内模型连接。

新运行在`runs/<task-id>-<run-id>/runner/`复制这份组件并冻结哈希，从该目录导入模块。宿主机可信入口`/opt/rl01-direct/lib/sandbox_entry.py`也须与记录哈希一致。前缀中的旧`lib/direct_isolation.py`和通用CLI入口可能仍是保活修复前版本；新生产使用本技能收录组件，不把前缀存在当成已经加载新版实现。组件更新只影响新运行，不能热改已冻结任务或接管其他会话。

新任务控制入口应接收真实题目目录、源ZIP哈希、模型范围和评分版本，创建自己的manifest与工作目录。历史FIN4的`task_run.py`、`dispatch.py`含任务专用来源与调度，不作为通用生产入口复用。组件不包含本题材料、Golden或真实凭据；导入模块不会启动模型，实际调用由当前任务控制入口执行。

## 隔离与能力边界

每个会话用锁分配独立宿主UID及独立目录，再建立文件、用户、PID和网络命名空间。候选仅能写自己的`/app/output`，输入只读，不能看到tests或Golden；Judge读取同一候选快照与tests，答案和输入都只读。模型执行前丢弃全部有效与bounding capabilities，锁定NOROOT、设置no_new_privs，seccomp拒绝再建命名空间或挂载。独立home／tmp、模型身份检查及只允许指定模型的通道防止跨会话读取和真实凭据暴露。

内核不允许挂新procfs。可信初始化仅将主CLI的进程目录绑定至`/proc/self`，随后遮蔽临时宿主proc源；没有完整宿主PID树。原生Claude必须作为主进程启动，不能用Bash包一层再启动Claude；该子启动在本容器上曾SIGTRAP。需要完整proc、嵌套Claude／Subagent、MCP或自定义Judge cwd的任务不落到当前基线。Skill挂载、浏览器及外部任务网络也不在已验证范围，适用任务应使用输入自包含、仅需现有文件与计算工具的模式。

当前每会话2048MiB由0.25秒间隔的PSS采样执行，无法取PSS时用RSS；观测失败或超过限额终止并留下resource_error。父容器约4GiB是硬上限，单会话并无硬cgroup限额，不能写成等价Harbor2GiB硬限额。可信入口另有单文件128MiB、单进程600秒CPU时间、1024文件描述符和128进程的限制。需求不满足时按选机参考使用VPS，不通过提高已冻结限额或把OOM／SIGTRAP当有效0分补救。

LibreOffice依赖公共字体、配置和必要库路径挂载，当前组件已包含这些适配。核对字体、版本、严格JSON、公式及缓存、可读导出；安装成功或能生成PDF不代表视觉质检通过。模型产物按原字节留证，不修正候选答案以改变其分数。

## 运行顺序

先做静态、依赖、文件权限、无模型隔离与资源预检，在独立运行目录冻结题包、组件和实际资源。按整机最多2个CLI会话安排候选和Golden，允许预跑但候选评分等该题同版本Golden门槛通过。一次Verifier的2条criterion并发占用2个CLI会话，不再叠加其他候选或Verifier；同主机其他会话也计入这份起步容量。三指定候选各完成一次有效生成，已有成功产物直接留给对应版本Judge。

候选使用`Stage(label, app, writable_output=True, model=指定模型, effort=None)`，题面来自冻结instruction.md，app只装输入和本轮空output。直接运行原生CLI，保存完整JSONL、终态、产物哈希及Stage.close回执；少做文件属于实际回答表现，请求／进程不可用按基础设施状态处理。当前候选沿CLI／供应商默认思考设置，不能因使用此主机擅自设low或high。

判分调用该运行副本的`direct_judge.grade(tests, app, graded_reward, workers=2)`，随后使用题包固定finalize.py收尾。逐项数量须等于该题Rubric数量，verifier_error=0且各分数载体一致；先核对所有Golden正向项及负项，再核对空答案和候选。完整原始回执、每条理由、退出状态和分数复算保留在私有台账，客户要求的产物、轨迹和评分证据按主技能封包。

受控代理使真实认证只留在可信进程；沙箱中仅有本会话临时身份。同逻辑请求成功即停，失败后最多再试10次，完整验证前不向CLI交付真实输出。确定性配置错误先修复配置，不伪造重试次数。保活修复避免等待响应头或重试退避时下游连接提前断开；候选和Judge都须使用同一已验证版本。耗尽写REQUEST_FAILED／VERIFIER_UNAVAILABLE，不写有效0分；恢复沿[execution-reliability.md](execution-reliability.md)。

## SSH与恢复

只读探测和短命令使用：

```bash
python3 ~/.codex/skills/ssh-skill/scripts/ssh_execute.py bohrium-rl01 '<只读探测或已授权命令>' --no-daemon --timeout 30
```

上传与下载使用ssh-skill的`ssh_upload.py`／`ssh_download.py`，加`MSYS_NO_PATHCONV=1`并等待传输完成后再执行依赖步骤。不直接调用ssh／scp。长作业由有日志、PID与单元锁的后台控制器管理；SSH退出不等于任务退出。Bohrium实测共享SSH daemon可能串行阻塞短探测，并在超时恢复时重复执行远程命令，作业控制因此使用`--no-daemon`，启动前检查已有单元和进程以防重复候选生成。

恢复先查当前任务的status、PID、完整CLI终态、产物与criterion记录；不根据一个缺失result.json重新启动整个任务。容器释放、地址变化或依赖丢失时重新验证别名、前缀和隔离能力，不能从旧路径存在推定可用。实际源文件、失败记录与已成功产物保留，新尝试用新目录；跨主机恢复条件按[runtime-selection.md](runtime-selection.md)执行。
