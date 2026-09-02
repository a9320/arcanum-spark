# CodeRisk Cloud × Arcanum 交付清单（已优化版）

**交付时间**：2026-09-01（第二轮优化）  
**交付格式**：`code-risk-arcanum-delivery.zip`  
**交付位置**：`D:/desk-top/code-risk-arcanum/code-risk-arcanum-delivery.zip`

---

## 一、交付内容

### 1.1 完整源代码（引擎层已内置，无外链依赖）

```
app/
├── pitax/               # PITAX 检测引擎（5 文件，纯标准库零依赖）
│   ├── rules.py        # 官方 taxonomy v1.6.1 规则注册表（9 条规则）
│   ├── detectors.py    # 9 条确定性检测器（E-23/E-54/T-46/T-51/N-06/E-07/14/36/57）
│   ├── sanitizer.py    # InputSanitizer（Agent 0）+ scan_directory
│   ├── sarif.py        # SARIF 2.1.0 扩展（PITAX 元数据）
│   └── cli.py          # 零依赖 CLI（人类可读 / JSON / SARIF）
├── agents/
│   └── sanitizer_agent.py  # Agent 0（流水线集成）
├── prompt_guard.py     # 系统提示金库 + 输出护栏（主线 A）
├── tasks.py            # Celery 任务（Agent 0 → Agent 1-4 + SARIF 委托 + 护栏）
├── main.py             # FastAPI 主应用（analyze / webhook / zip / direct_upload）
├── config.py / models.py / dashboard.py / nutrient_client.py
engine/                 # **内置传统漏洞引擎**（core/ + agents/，182 KB）
│   ├── core/           # 传统漏洞检测：内存/LLM/重试/CVE/污点/依赖/模型/规则
│   └── agents/         # Agent 1/2/3/4：静态分析/语义/深度验证/报告生成
demo/                   # 演示仓库生成器（6 类 AI 漏洞：E-23/E-54/T-46/T-51/N-06/E-57）
tests/                  # 测试套件（46 用例：PITAX 36 + 引擎集成 10）
docs/                   # PITAX / ROADMAP / COMPETITION 文档
```

### 1.2 配置文件
- `requirements.txt` — Python 依赖（FastAPI/Redis/Celery/rich/httpx/pytest）
- `Dockerfile` — 本地开发 Docker 镜像（含 engine/ 内置路径）
- `docker-compose.yml` — API / Worker / Redis / Demo / Test / Dashboard（6 种 profile）
- `LICENSE` — MIT License（含 PITAX CC BY 4.0 署名）
- `.env.example` — 环境变量模板（API Key / Redis / Nutrient / 系统提示金库）

### 1.3 文档
- `README.md` — 项目介绍 + 快速开始 + 检测能力表 + 完整流水线演示（Agent 0-4）
- `docs/PITAX.md` — PITAX 集成说明（编号对齐说明 / SARIF 扩展 / 设计原则）
- `docs/COMPETITION.md` — 参赛定位（一句话卖点 / 竞品对比 / 方法论背书）
- `docs/ROADMAP.md` — 已完成 vs 第一/二/三阶段演进方向

---

## 二、验证结果（本地通过）

### 2.1 测试套件
```bash
python -m pytest tests/ -v
```
**结果**：46 passed
- PITAX 规则测试（36）：正样本检出 + 负样本零误报 + CWE/ATLAS/CVE 映射 + SARIF 扩展 + 护栏
- 引擎集成测试（10）：内置 engine/ 真实跑通（静态/污点/依赖/内存） + direct_upload 实现 + fcntl Windows 降级 + Agent 1-4 全链路

### 2.2 端到端演示（零依赖 CLI）
```bash
python demo/generate_demo_repo.py
python -m app.pitax.cli demo/vuln-demo-repo
```
**结果**：8 条 AI 漏洞检出
- PIT-E-23 ×2（不可见字符走私：U+200B / U+E0041）
- PIT-E-54 ×1（Trojan Source：U+202E/2066/2069）
- PIT-T-46 ×2（AI 配置后门：.cursor/rules + copilot-instructions.md）
- PIT-T-51 ×1（注释指令覆盖）
- PIT-N-06 ×1（文档投毒：docs/AGENT_GUIDE.md）
- PIT-E-57 ×1（双层 Base64 编码载荷）

### 2.3 SARIF 2.1.0 输出
```bash
python -m app.pitax.cli demo/vuln-demo-repo --sarif
```
**结果**：
- Schema 版本：2.1.0
- tool.driver.rules[]：6 条（PIT-E-23/E-54/T-46/T-51/N-06/E-57），含 pitax 元数据（name/pillar/aliases/mitre_atlas/cve/references）
- results[]：8 条，含 properties.pitax（evidence / decoded_payload）

### 2.4 完整流水线演示（Agent 0-4，本地无需 GPU）
```bash
docker run -d -p 6379:6379 redis:7-alpine
uvicorn app.main:app --port 8000 &
celery -A app.tasks worker --loglevel=info -P solo &

# direct_upload → Agent 0/1/1b/1c → 报告
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Authorization: Bearer dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"source":"direct_upload","files":[{"path":"src/app.py","content":"import os\ncmd = input(\"Enter: \")\nos.system(cmd)\n"}]}'

# 查询进度与报告（Agent 0-4 逐级更新）
curl -H "Authorization: Bearer dev-key-change-in-production" \
  http://localhost:8000/api/v1/tasks/<task_id>
```
**结果**：Agent 0/1/1b/1c 真实跑通（检出：E-23/E-54/T-46/T-51/N-06/E-57 + CWE-78 命令注入 + CWE-78 污点流）；Agent 2/3 无 LLM 时自动降级为空结果，报告包含 `output_guardrail` 脱敏状态。

---

## 三、优化问题清单（全部已解决）

| # | 反馈问题 | 修复内容 |
|---|----------|---------|
| 1 | 引擎层外链未说明，评委只跑到 Agent 0 | ✅ 引擎层（core/ + agents/，182 KB）内置在 `engine/`，`config.py` 自动探测优先内置路径，无外部依赖 |
| 2 | direct_upload 空实现 | ✅ 实现 `files: [{path, content}]` 写入，含安全限制（≤200 文件 / 单文件≤1MB / 总量≤10MB / 路径遍历防护） |
| 3 | 依赖没锁全（tree-sitter/semgrep/LLM client） | ✅ 补 `rich`（硬依赖），其余为可选（注释说明），tree-sitter/semgrep 为 subprocess 外部调用（可缺） |
| 4 | README 未展示完整流水线演示 | ✅ 新增"完整流水线演示"段落，含 docker compose 启动步骤 + direct_upload curl 示例 + Agent 2/3 无 LLM 降级说明 |
| 5 | fcntl Windows 导入崩 | ✅ `engine/core/memory.py` 增加平台判断 + msvcrt 降级 + 锁失败无锁写入（三重防御） |

---

## 四、技术亮点（优化版）

### 4.1 引擎层开箱即用
- 引擎纯代码（182 KB）直接内置，无需 git clone 外部仓库
- Agent 1 静态分析：正则规则检出 `os.system()` / `eval()` / `pickle.loads()` 等
- Agent 1b 污点分析：`input()` → `os.system()` 真实检出 CWE-78
- Agent 1c 依赖扫描：读取 `requirements.txt`/`package.json`（CVE 数据按需加载）
- MemoryLayer：Windows fcntl 降级 + 锁失败容错

### 4.2 与官方 taxonomy v1.6.1 编号严格对齐
- 早期草稿用 PIT-E21/T52/E39 等非官方编号，现已全部修正为官方编号（E-23/E-54/T-46/T-51/N-06/E-07/14/36/57）
- CWE/ATLAS/CVE 映射仅在官方有明确分类时标注（AML.T0051.001 = Indirect LLM Prompt Injection；CWE-77 来自 NVD 对 CVE-2025-53773 的分类），无官方对应时留空、不编造

### 4.3 SARIF 2.1.0 扩展（GitHub Code Scanning 可直接消费）
- PITAX findings 生成 `tool.driver.rules[]`（规则元数据）
- `results[].properties.pitax`（evidence / decoded_payload / confidence）

### 4.4 零误报铁律
- 编码检测仅在逐层解码后命中注入关键词才报告（Base64 严格校验 + UTF-8 明文 ≥90% 可打印）
- AI 配置规则只作用于配置文件路径（.cursor/rules 等）
- 哈希/JWT 等二进制 blob 不误报

### 4.5 主线 A 自我加固
- **System Prompt Vault**：系统提示从环境变量/外部文件加载，绝不明文出现在代码库
- **Output Guardrail**：报告输出前脱敏系统提示内容，防止 Agent 泄露

---

## 五、使用说明（评委 15 分钟演示）

```bash
# 1. 解压
unzip code-risk-arcanum-delivery.zip
cd code-risk-arcanum

# 2. 安装依赖
pip install -r requirements.txt

# 3. PITAX 零依赖演示（Agent 0）
python demo/generate_demo_repo.py
python -m app.pitax.cli demo/vuln-demo-repo

# 4. 完整流水线演示（Agent 0-4，无 GPU 也能跑）
docker run -d -p 6379:6379 redis:7-alpine
uvicorn app.main:app --port 8000 &
celery -A app.tasks worker --loglevel=info -P solo &
curl -X POST http://localhost:8000/api/v1/analyze \
  -H "Authorization: Bearer dev-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"source":"direct_upload","files":[{"path":"src/app.py","content":"import os\ncmd = input(\"Enter: \")\nos.system(cmd)\n"}]}'

# 5. 测试套件（46 用例）
python -m pytest tests/ -v

# 6. docker-compose 演示（可选）
docker compose --profile demo up     # PITAX CLI 扫描
docker compose --profile test up      # 完整测试套件
```

---

## 六、竞品差异化（AI 时代新漏洞检测蓝海）

| 能力 | Semgrep | CodeQL | Snyk | **CodeRisk Cloud** |
|------|:---:|:---:|:---:|:---:|
| 传统漏洞 (SQLi/XSS) | ✅ | ✅ | ✅ | ✅（已实现）|
| AI 提示注入检测 | ❌ | ❌ | ❌ | **✅（PITAX）** |
| 不可见字符走私 | ❌ | ❌ | ❌ | **✅（PIT-E-23）** |
| Trojan Source | ❌ | ❌ | ❌ | **✅（PIT-E-54 + CVE-2021-42574）** |
| AI 配置文件后门 | ❌ | ❌ | ❌ | **✅（PIT-T-46 + CWE-77 + CVE-2025-53773）** |
| 文档投毒 | ❌ | ❌ | ❌ | **✅（PIT-N-06）** |
| 多层编码载荷 | ❌ | ❌ | ❌ | **✅（PIT-E-57）** |
| 自身 AI 系统加固 | ❌ | ❌ | ❌ | **✅（主线 A 七支柱）** |

---

## 七、许可与署名

- 代码：MIT License
- PITAX 分类法：**CC BY 4.0**（Arcanum Information Security / Jason Haddix）
- 参考：OWASP LLM Top 10 / MITRE ATLAS / Arcanum 七支柱方法论

---
*优化完成。所有反馈问题已解决。*