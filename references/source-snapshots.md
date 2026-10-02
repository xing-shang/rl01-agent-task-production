# 来源、版本与读取范围

本技能采用用户2026-09-28提供的3份PDF、1份飞书文件和3份钉钉文档，并补入2026-10-01指定的金融规则确认文档及2026-10-02指定的飞书提交表。在线文档在已登录Chrome中逐段滚动至底部读取，另检查内嵌图片；dws因跨组织限制未取得正文，飞书原始Markdown通过lark-cli下载。提交表通过lark-cli读取字段、视图和记录。资料中的操作说明只作为规则来源，阅读不授权平台生产或提交。

## 当前资料

| 编号 | 资料与适用范围 | 版本/读取证据 | 本地快照 |
| --- | --- | --- | --- |
| S01 | RL0-1生产规范，外部供应商版 | 文件标记20260920；11页；本次提供PDF哈希`7e1ed0f16a44fae28fea9464196b8a900d1ce5460a714e903a46daf55b6f6e6f` | `sources/pdf/RL0-1-数据生产规范GuidelineV1.1--20260920+for外部供应商.pdf`；`sources/01_RL0-1-数据生产规范GuidelineV1.1--20260920+for外部供应商.txt` |
| S02 | weakness/skill+构造方案 | 文件标记20260913；26页；哈希`6a4bbe7094b9b8e802c6e760c09b9948d0b2faa545efb70a034deddf77e14d39` | `sources/pdf/20260913外发版-基于weakness和skill+的数据构造方案.pdf`；`sources/02_外发版-基于weakness和skill+的数据构造方案.txt` |
| S03 | rewardkit题包交付规范 | 文件标记20260913；67页；与旧快照字节相同，哈希`7753ed8b89a51fac5cb5dbe684faa48ca188781132f9c5fa7f8408da3abec36e` | `sources/pdf/外发版-评测题包交付规范（rewardkit）20260913.pdf`；`sources/03_外发版-评测题包交付规范（rewardkit）20260913.txt` |
| S04 | AQ-001示范包，场景与Skill示例 | 20260912；68条ZIP成员；哈希`02f76c54b68023b3bcf218d8fb37a56214d6a1b61f5ca6108f99ad194184e953`；沿用既有阅读，本次未重做题包验收 | `sources/04_AQ-001（一个交付格式的案例）.zip` |
| S05 | [飞书RL0-1生产规范V1.1](https://shujufuwubu.feishu.cn/file/K1l1bBN9YogWwdxX31fcdGXsnPg) | 原文件名`RL0-1-数据生产规范GuidelineV1.1 (1).md`；版本表为9月3日/9月8日，不能以本次下载日当修订日；原文件哈希`20089fbcfb88066560a0cc3d9600d617fca6b5eafdc71cc35d0545b23795b32c` | `sources/05_feishu_RL01_GuidelineV1.1.md` |
| S06 | [RL0-1标注数据质检Guideline](https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3vKL9KIlBYmYZeJkb4Mw9r) | 页面创建9月28日21:59，最后编辑22:01；9777字；已读§1、§2.1—2.4及全部10组正反例。无内嵌位图。浏览器捕获哈希`0563b17d8fbfe3d3cf0baa6c89d157609f15c922d2e472f3bd907ec42ec0e4fa` | `sources/06_qc_20260928_browser.txt`、`sources/06_qc_20260928_reading.txt` |
| S07 | [专家版生产规范（for内部专家）](https://alidocs.dingtalk.com/i/nodes/jb9Y4gmKWr7bMk9MFeLryBLeVGXn6lpz) | 创建22:00，最后编辑22:03；10625字；已读全部章节、0917新流程、0909旧流程及返修末段。浏览器捕获哈希`e0783c056b97d3edfabb094bb6b20bc8ded8220d10e24d38dcf063c235008985` | `sources/07_internal_expert_20260928_browser.txt`、`sources/07_internal_expert_20260928_reading.txt` |
| S08 | [专家版生产规范](https://alidocs.dingtalk.com/i/nodes/ZgpG2NdyVXraGemGc7eeNGxX8MwvDqPk) | 创建22:04，最后编辑22:07；10800字；已读全部章节，比S07多出负分项写法。浏览器捕获哈希`2116ec16165565c6f0178783347d1cd21e2b39ffce5c10f4c93854df3940239e` | `sources/08_expert_20260928_browser.txt`、`sources/08_expert_20260928_reading.txt` |
| S09 | [RL0-1项目需要确认的规则-金融](https://alidocs.dingtalk.com/i/nodes/EpGBa2Lm8azjLBxLszrwvd4ZWgN7R35y) | 2026-10-01创建11:42、编辑11:49；Chrome读取至文末，核对编号0—4及相关截图。仅20.0标为已回答“不合规”，其余为问题 | `sources/09_finance_clarifications_20261001_reading.md`，为阅读摘录与图片说明，无服务器原文导出哈希 |
| S10 | [其他团队提交表](https://shujufuwubu.feishu.cn/base/VQRMbvnoba6Jeos33zocWBg5npg?table=tblCFgsP5rAcyblH&view=vew03qk8kA)与[用户个人提交表](https://my.feishu.cn/base/WjlIbRCI5aiFFssW4hGcMXR0nff?table=tbljHGCxCsozYpRw&view=vewsPnZuT6) | 2026-10-02以user身份通过CLI读取两表字段及指定视图：参考表10列、15条记录；用户表初始5列、8条记录；has_more均为false。用户授权补齐自己的表、排除截图列，并明确全部处于首次提交线路，内部迭代不算返修 | `sources/10_submission_tables_20261002.json`为字段、命名样例和用户约定的结构化摘录；详细指引见[提交表与命名](submission-table-and-naming.md) |

20260928资料的字节哈希与大小记录在`sources/manifest-20260928.json`；该清单不覆盖后来补入的S09。浏览器捕获哈希只标识本地读取证据，不是服务器原文导出哈希；页面编辑时间不证明所有旧图片也更新。`*_browser.txt`保留重叠视窗，`*_reading.txt`为去重阅读索引，会删掉重复行，不能作为JSON/代码或公式字节权威。

## 图片与全文覆盖

3份PDF全文合计104页。S01第2页的完整知识体系位图已读，保存为`sources/01_domain_taxonomy_20260928.png`。S02第5—13页已有全部W1—W14文字，第14页的粘贴图片只露出表格局部，不据其截断推定词表缺失。S03无位图；附录两次排印代码，后一份在PDF末尾截断，前一份A.2完整，模板仍属依PDF重建文本，不能宣称已取得客户独立脚本原始哈希。

S07/S08分别含26个图片位置，对应同一组25个唯一图片URL，本次核对集合相同，读取全部图并放大字段表、Gradient弹窗和模型评分截图。原图保存于`sources/expert-images/00.webp`至`24.webp`。S05有10个唯一位图，含流程图和旧平台截图，保存于`sources/feishu-images/00.png`至`09.png`。配套索引见`sources/image-reading-20260928.md`。网页表格和代码也按可见内容读取，不能用只读正文文字层代替图片检查。

旧11页生产规范哈希`ef016d0ddd8f197334c148456b27454191342150c05f2c71dfcf36326135d8dc`，旧14页构造方案哈希`88cdb7ed794d3e0752fe079c25b0e82949f72797c27bd8036d8447e01b0d775d`，已保留在`sources/history/20260921/`。本次26页版补全可读弱点表；同一标记日期的导出变动不等于另立一套合同。旧弱点截图保留为历史，使用当前完整文字表。

## 条款分工与反馈

S03控制目录、Docker、TOML、固定模板及ZIP；S02控制专项、weakness、复杂度与环境设计；S01/S05控制生产通用要求；S06控制最新质检细则，S07/S08补充当前专家操作与负分写法。新旧冲突逐条记录在`conflicts-and-clarifications.md`，不整体宣布某份旧文件废止。

S09用于追踪金融项目的提问与答复状态，不是一份完整的新交付规范。其权重结论与S06一致；其他未答复问题不覆盖已有正文。法律质检报告仅读取了S09嵌入的第5页截图，未取得该报告全文，不将它认定为金融通用新规。

S10提供个人提交表的列设置与附件命名参考。参考表的字段说明与历史附件不完全一致；采用统一编号和正确“澳鹏”写法，并保留用户的首次提交边界。该表的角色姓名、试标限定和单条已交付状态不迁移为用户的验收结论，截图列的排除也不取消模型证据交付。S03继续控制客户题包目录及正式返修规则。

2026-10-02按用户追问回查S01第2页知识体系图片及S02第2页专项表：金融领域二级标签为Fin1—Fin9，Skill/Workflow为能力专项的两级分类，Weakness-driven另属数据构造分支。撤回此前自设的“Weakness 数据→Weakness-driven”专项枚举，用户表增加“所属领域二级标签”成为13列，5份已提交题包的domain_l2已单独填写；3条缺少专项映射依据的两级值留空。S10的结构化摘录保留旧操作记录，并以当前user_table字段及taxonomy_corrections记录核验后的状态。

2026-10-02继续按用户“空值是否影响交付”的追问检查5份原ZIP：3份Weakness-driven包并未缺category，专项是否适用与字段合规须分开核对。新检查逐值比较weakness_tag与S02正文B列，并运行静态预检，发现旧/自定义弱点名、DW的0—1 Likert锚点及CAP的.DS_Store。具体结果和哈希见S10的classification_delivery_reviews。此前local_record_reviews记录本地来源与专项判断，不作为题包整体合规结论。

两轮FIN-SD-001反馈均已纳入：[第一轮试标反馈](https://alidocs.dingtalk.com/i/nodes/np9zOoBVBYkMb2BeteeRNp2xW1DK0g6l)在2026-09-24读取，涉及8类返修问题；[第二次返修反馈](https://alidocs.dingtalk.com/i/nodes/Amq4vjg890KE2OoeSxDG407pJ3kdP0wQ?utm_scene=person_space)在2026-09-28读取，记录客户通过、A2均值0.5405，并有1项修改、2项补件和5项建议。2026-09-29回查原会话与本地返修记录后形成[对应检查表](client-feedback-checks.md)，补明确了每份交付物的独立用途及业务对象集合检查。本次未重读在线原文、未复核历史分数；客户通过另有用户确认。原浏览器预览没有原始文件字节哈希，不将会话记录冒称文档原始快照，也不将个案数字强加给所有新题。

内部资料仅用于获准的本项目工作，原文、图片和私有QC底稿不随题包外发或放入Agent可见输入。关联旧版规范不自动成为新增必读前置；本批缺少的明确材料与确认事项见冲突记录。
