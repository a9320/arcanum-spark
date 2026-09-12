---
deployspec:
  entry_file: app.py
---

# CodeRisk Cloud × Arcanum

**检测 AI 时代新型代码漏洞的代码安全平台** —— 基于 [Arcanum Prompt Injection Taxonomy](https://arcanum-sec.com/pitax)（Jason Haddix, Arcanum Information Security）。

全球首批能检测 **AI 提示注入、不可见字符走私、Trojan Source、AI 配置后门、文档投毒、多层编码载荷** 的代码安全工具。传统 SAST/DAST（Semgrep/CodeQL/Snyk）做不到。

> ⚠️ 本项目为独立开发仓（下一代方向），与已发布的 `coderisk-cloud`、`code-risk-agent` 相互独立、互不影响。

## 快速开始（零依赖，无需 Redis/API Key）

```bash
# 1. 生成"故意植入 6 类 AI 漏洞"的演示仓库
python demo/generate_demo_repo.py

# 2. 一键扫描
python -m app.pitax.cli demo/vuln-demo-repo

# 3. JSON / SARIF 输出
python -m app.pitax.cli demo/vuln-demo-repo --json
python -m app.pitax.cli demo/vuln-demo-repo --sarif
```

## 6 节点 Agent 流水线（codeark/，Strands SDK + 国产模型异构合议）

```bash
# 0. 一键验证（确定性测试 + dry 秒扫 + eval 回归校验 + 干净仓 FP=0，零 LLM API）
bash verify.sh

# 1. 确定性秒扫（Agent0 规则层，不调大模型）
python -m codeark.cli demo/vuln-demo-repo --dry

# 2. 完整流水线：Agent0(PITAX 规则) → Scout(GLM-5.3 语义增量侦察)
#    → Verify(DeepSeek-V4-Flash 逐假设拆分裁决) → Deepen(逐条攻击链)
#    → Arbiter(GLM-5.3 异构合议) → Report(JSON/SARIF/Markdown)
python test_e2e.py            # 真实 LLM，10-30 分钟，报告落 reports/

# 3. 对报告跑私有回归集（预期检出全覆盖 + severity 底线 + FP=0）
python eval/check_report.py --report reports/dry_eval/report.json
```

关键机制：**prompt 隔离层**（不可见字符剥离/注入触发词中和/UNTRUSTED DATA 边界，模型只见消毒版、工具跑原始版）；**severity 确定性底线**（LLM 只能带证据升级）；**节点级降级披露**（任一模型故障走确定性路径并在报告标注，绝不静默）；证据包见 `evidence/`，演示叙事见 `docs/DEMO-SCRIPT.md`。

## 检测能力（9 条规则，与官方 taxonomy v1.6.1 编号严格对齐）

| 规则 | 名称 | 严重级 | CWE | MITRE ATLAS | CVE |
|------|------|--------|-----|-------------|-----|
| PIT-E-23 | Invisible Text | HIGH | - | AML.T0051.001 | - |
| PIT-E-54 | Trojan Source | HIGH | - | - | CVE-2021-42574 |
| PIT-T-46 | Agent Instruction-File Injection | CRITICAL | CWE-77 | AML.T0051.001 | CVE-2025-53773 |
| PIT-T-51 | Instruction Override | HIGH | - | AML.T0051.001 | - |
| PIT-N-06 | Document / File Upload | HIGH | - | AML.T0051.001 | - |
| PIT-E-07 | Base64 Encoding | MEDIUM | - | AML.T0051.001 | - |
| PIT-E-14 | Cipher (ROT13) | MEDIUM | - | AML.T0051.001 | - |
| PIT-E-36 | Reverse | MEDIUM | - | AML.T0051.001 | - |
| PIT-E-57 | Layered Encoding | CRITICAL | - | AML.T0051.001 | - |

> CWE/ATLAS 映射仅在官方有明确分类时标注；AML.T0051.001 = Indirect LLM Prompt Injection。

## 项目结构

```
app/
├── pitax/              # PITAX 检测引擎（规则/检测器/扫描器/CLI/SARIF，纯标准库零依赖）
├── agents/             # Agent 0: Input Sanitizer / PITAX 预扫描
├── tasks.py            # Celery 任务（Agent 0 已集成 → Agent 1-4 流水线）
├── prompt_guard.py     # 系统提示金库 + 输出护栏（主线 A 自我加固）
├── main.py             # FastAPI 入口（analyze / webhook / zip 上传 / direct_upload）
├── config.py / models.py / dashboard.py 等
engine/                 # 内置传统漏洞引擎（Agent 1-3：静态分析/污点/依赖/LLM 语义）
demo/                   # 演示仓库生成器
docs/                   # PITAX / ROADMAP / COMPETITION 文档
tests/                  # 测试套件（46 用例：PITAX 36 + 引擎集成 10）
```

## 流水线（Agent 0 已集成）

```
Agent 0 (PITAX 预扫描) → Agent 1 (静态) → Agent 2 (语义) → Agent 3 (验证) → Agent 4 (报告)
       └─ AI 新漏洞（提示注入/Unicode/Trojan Source/配置后门/文档/编码）并入报告 ai_findings 区块
       └─ Agent 4 输出前经过 OutputGuardrail 脱敏（防系统提示泄露）
```

## 测试

```bash
python -m pytest tests/ -v   # 46 passed：PITAX 36 + 引擎集成 10（Agent 1-3 真实跑通）
```

## 完整流水线演示（Agent 0-4，本地即可跑，无需 GPU）

引擎层（传统漏洞检测：静态分析/污点/依赖扫描）**已内置在 `engine/` 目录**，开箱即用：

```bash
# 启动 Redis（仅任务队列需要）
docker run -d -p 6379:6379 redis:7-alpine

# 终端 1：API 服务
uvicorn app.main:app --port 8000

# 终端 2：Celery Worker
celery -A app.tasks worker --loglevel=info -P solo

# 终端 3：提交 direct_upload 分析（静态分析 Agent 1 真实跑通）
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Authorization: Bearer dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"source":"direct_upload","files":[{"path":"src/app.py","content":"import os\ndef run(cmd):\n    os.system(cmd)\n"}]}'

# 查询进度（Agent 0-4 状态逐级更新）与报告
curl -H "Authorization: Bearer dev-key-change-in-production" \
  http://localhost:8000/api/v1/tasks/<task_id>
```

**降级行为说明**（无 GPU / 未装可选依赖时）：

| Agent | 依赖 | 无依赖时行为 |
|-------|------|--------------|
| Agent 0 PITAX | 无（纯标准库） | 完整可用 ✅ |
| Agent 1 静态分析 | rich | 完整可用 ✅（纯规则匹配） |
| Agent 1b 污点分析 | 无 | 完整可用 ✅ |
| Agent 1c 依赖扫描 | 无 | 完整可用 ✅ |
| Agent 2 语义分析 | 本地 LLM（llama.cpp/OpenAI 兼容） | 跳过（日志说明） |
| Agent 3 深度验证 | 本地 LLM | 保留原 findings 直接进入报告 |
| Agent 4 报告 | Nutrient DWS（PDF 时） | JSON/SARIF 完整可用 ✅ |

> 即：**零 GPU 也能演示 Agent 0-4 全流水线**（Agent 2/3 自动降级），有 AMD GPU 时配置
> `CODERISK_MODEL_PATH` 指向 GGUF 模型即可启用语义分析。

## 文档

- [PITAX 集成说明](docs/PITAX.md)
- [Roadmap（参赛核心 vs 长期愿景）](docs/ROADMAP.md)
- [参赛定位与竞品对比](docs/COMPETITION.md)

## 许可与署名

- 代码：独立开发，署名本项目
- PITAX 分类法：**CC BY 4.0**（Arcanum Information Security / Jason Haddix）
- 参考：OWASP LLM Top 10 / MITRE ATLAS / Arcanum 七支柱方法论

---
*Based on the Arcanum Prompt Injection Taxonomy by Jason Haddix, Arcanum Information Security (arcanum-sec.com). CC BY 4.0.*