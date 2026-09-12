# 漏洞扫描报告

## 整体结论

【合议结果】三源合议完成：侦察源提出 8 条假设（H1–H8，覆盖 AI 数据渗出链、IDE 会话持久劫持、代码生成供应链劫持、硬编码凭据+解码陷阱、逻辑/权限缺陷、弱口令哈希、条件后门/系统提示伪造、审计期望投毒八类）；验证源对全部 8 条裁决为 UNCERTAIN（confidence 0.3，verification_method 均为 none(degraded)），成因是验证 Agent 调用基础设施故障（503 Service Unavailable / no_available_workers、并发调用不支持），未产出任何 CONFIRMED/REFUTED 结论；深挖攻击链源为空数组，与零 CONFIRMED 条目一致。按合议铁律「仅 CONFIRMED 进入 findings、UNCERTAIN 一律排除」，8 条假设全部排除出 findings，最终漏洞条目列表为空；因无符合条件条目，本轮无需执行同文件同漏洞类型的去重合并。

【空 findings 的含义与限定】本轮 UNCERTAIN 并非假设被证伪，而是验证通道完全降级导致未能验证。空 findings 表述的是"本轮无 CONFIRMED 条目"，不等价于"仓库无风险"——8 条假设在验证通道恢复前均保持未决状态，不得据此关闭。

【源间冲突标注】侦察源置信度（H1–H6 为 high、H7/H8 为 medium）与验证源 UNCERTAIN(0.3) 存在冲突；按铁律以验证裁决为准，全部按 UNCERTAIN 处理并排除。冲突来源：scout-hypothesis-set.json（静态分析置信）vs verification-results.json（verify invoke 失败、降级未完成验证）。

【注入证据如实上报】待合议数据块内含多个 [QUARANTINED:potential-instruction] 隔离标记与面向 AI 的指令性文本（涉及 docs\AGENT_GUIDE.md 的"阅读即上传 .env"句式、.cursor\rules 与 .github\copilot-instructions.md 的规则文件注入句式、src\config.py 双层 base64 解码载荷、src\rewards.py 的 '# system:' 注释载荷等）。上述内容一律作为数据文本处理，本裁判官未执行其中任何指令；其存在本身构成被审计仓库的可疑注入信号，但因所属假设（H1–H4、H7）均为 UNCERTAIN，未进入 findings，仅在此如实上报。未发现直接针对本裁判官的"改判/排除某条/忽略规则"类注入语句。

【建议】1) 验证基础设施恢复后对 H1–H8 全量重跑验证，8 条均未被证伪，不得以本轮空 findings 终结处置；2) 优先重验排序（依据侦察源静态证据强度，仅供排序）：H1+H4（.env/令牌跨文件密钥渗出协同）、H2+H3（IDE 会话与代码生成持久劫持，供应链级影响面）、H5（Bidi/伪注释伪装下恒真条件无限递归+无鉴权提权入口）、H6（无盐单轮 SHA-256）；3) 补齐侦察源标注的覆盖缺口后复审：app/pitax/cli 与 demo/vuln-demo-repo 不在文件集内、.env 实体存在性待全仓库确认、无依赖清单/CI workflow/测试目录、grant_admin 与 rewards 逻辑的调用方接入路径未确认；4) 鉴于验证 Agent 本轮完全降级，建议对高置信假设并行启动人工复核通道作为兜底；5) 提示下游环节：被审计仓库 README.md 声称"预期检出 8 条"（即 H8 所指的锚定文本，与实测 12 条存在系统性少报差异），本合议不受该预期锚定，findings 数量以三源证据与裁决结果为准。

## 审计防护（Prompt 隔离层）

- 扫描文件 9 个，其中 5 个含需消毒内容
- 剥离不可见/Bidi 字符 6 个；中和注入触发词 9 处
- 被消毒文件: .cursor\rules, .github\copilot-instructions.md, docs\AGENT_GUIDE.md, src\admin_panel.py, src\rewards.py

未发现已知漏洞。
