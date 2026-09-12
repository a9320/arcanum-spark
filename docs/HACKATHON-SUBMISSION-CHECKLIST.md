# Agents for Humans Hackathon — 提交合规清单（9/14 截止）

> 规则依据：devpost.com/rules（2026-08-12 版）。截止：**2026-09-14 17:00 PT = 北京时间 9/15 08:00**。
> 结论：**合规基线全部达标**；剩余项全部是"人的动作"（录视频/填表/发帖），代码侧今天收口。

## 一、硬性要求对照（规则 → 本项目现状）

| 规则要求 | 现状 | 状态 |
|---|---|---|
| 新项目（窗口期 8/10–9/14 内创建，需披露预存在代码） | 首提交 2026-09-02，全部代码在窗口内 | ✅ Devpost 描述中含披露段 |
| Strands Agents SDK 为编排核心 | 6 Agent 全部 strands.Agent + structured_output + 绑定工具 | ✅ 技术叙事核心 |
| 公开代码仓（完整源码+安装说明） | github.com/a9320/code-risk-arcanum 匿名可访问（200） | ✅ 本地 8+ 提交待推送（e2e 收口后统一推） |
| MIT 或 Apache 许可证，且 GitHub About 可见 | 根目录 LICENSE = MIT | ✅ 提交前确认 GitHub About 侧栏显示 "MIT license" |
| README | 已含 6 节点流水线快速开始 + verify.sh | ✅ |
| 架构图 | docs/architecture-6node.png / .svg | ✅ |
| 演示视频 ≤5 分钟、公开链接（YouTube/Vimeo）、覆盖三问 | 脚本 2-3 分钟；**需英文口播或英文字幕**；`docs/DEMO-SCRIPT.md` 已加英文口播段 | ⬜ 你录（9/13） |
| 文本描述（英文） | `docs/DEVPOST-DESCRIPTION-EN.md` 草稿 | ⬜ 你粘贴进 Devpost |
| AWS Builder ID | — | ⬜ 你注册/提供 |
| 测试路径免费可用 | verify.sh 全零 API + ModelScope Studio 公开演示 | ✅ |
| 主题契合（重复性后台工作 + 只在有决策时找人类） | 叙事已对齐：CI/仓库审计后台自治，只上报 CONFIRMED（要修）与 UNCERTAIN（要人复核） | ✅ |

## 二、赛道选择（建议）

**Professional Agents**：安全审计是"重复、判断密集、人人受益"的专业工作；Agent 在后台自治跑完整多模型合议，只在需要真实决策时浮出。备选 Good Neighbor（防御性安全赋能小团队），但 Professional 更贴"让专业人士效率倍增"的判词。

## 三、评分标准与我们的得分策略（5 项同权）

| 评分项 | 我们的证据 |
|---|---|
| Technological Implementation | Strands 深度用法（structured_output/绑定无参工具/多模型路由/逐节点编排）；**加 live demo 链接可加分** → 填 ModelScope Studio 公开地址 |
| Design | 三格式报告（MD/SARIF/JSON）+ 攻击链区块 + 降级披露——成品而非 PoC |
| Potential Impact | AI 助手自动读取规则文件已是默认行为，投毒即供应链入口；给出 CI 门禁落地路径 |
| Creativity & Originality | PITAX 新漏洞类 + 异构模型合议防自证 + prompt 隔离层（模型把注入当数据上报的日志原话） |
| Presentation | 2-3 分钟英文视频，钩子=零宽字符闪烁 |

**加分项（最多 +0.6）**：builder.aws.com 发布构建历程帖（标题须含 "Agents for Humans"，截止前公开发布，每篇 +0.2 最多 3 篇）。建议至少发 1 篇：《Building a 6-agent security auditor with Strands Agents SDK and domestic model routing》。

## 四、资格自查

参赛资格以官方规则为准：Devpost 规则页列有居住地排除条款（部分国家/地区不参赛），提交人应自行核对官方名单确认资格。本仓库不做资格判断。

## 五、剩余动作（全部是你的部分，代码侧无阻塞）

1. （9/13）按 `docs/DEMO-SCRIPT.md` 录英文视频 ≤5 分钟（三问：问题/给谁/为何重要），传 YouTube 设公开；
2. （9/13）Devpost 填表：文本描述粘贴 `DEVPOST-DESCRIPTION-EN.md`（可润色）；代码仓 URL；live demo = ModelScope Studio；架构图；AWS Builder ID；确认 GitHub About 显示 MIT；
3. （建议，截止前）builder.aws.com 发 1-3 篇构建帖（标题含 "Agents for Humans"）；
4. （截止前 2 小时）Devpost 提交并留截图存档。

## 六、风险缓冲

- 视频"公开链接"在提交后可改 unlisted 吗？规则未禁止，但按最保守口径：提交时即公开。
- 仓库名/About 描述建议统一为 "CodeRisk Arcanum — 6-agent AI-era code security auditor (Strands Agents SDK)"，与 Devpost 一致。
- 若 e2e #5 仍有节点降级：演示叙事本来就以"降级披露=诚实工程"为卖点，报告空 findings 也有完整解释链，不影响提交资格。
