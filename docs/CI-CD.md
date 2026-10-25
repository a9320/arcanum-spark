# CI/CD 集成指南（确定性层，零 LLM）

> 适用对象：想把 arcanum-spark 的确定性 PITAX 扫描接进流水线的使用者。
> 扫描本身不调用 LLM；除安装依赖外不需要外部服务，Python ≥3.10。

## 1. 先看清楚退出码语义

`codeark.cli` 的退出码只反映"跑没跑成"：

| 退出码 | 含义 |
|---|---|
| `0` | 扫描完成（**无论命中多少条**） |
| `1` | 路径不存在，或没读到任何代码文件 |

"发现即失败"的策略门由流水线自己加（见 §5）。确定性层没有 `--fail-on` 之类的开关，
这是故意的：规则命中是否阻断合并取决于你的仓库分级策略，工具不替你做主。

## 2. GitHub Actions（含 SARIF 上传 Code Scanning）

可直接复制的完整文件：[`examples/ci/github-actions-audit.yml`](../examples/ci/github-actions-audit.yml)

要点：

- 必须带 `--dry`：跳过 Scout/Verify/Deepen/Arbiter 的模型调用，只跑确定性规则层；
- `permissions.security-events: write` 才能上传 SARIF；
- `report.sarif` 是标准 SARIF 2.1.0，可直接被 GitHub Code Scanning / IDE 消费；
- 扫描整个仓库时把路径设为 `"$GITHUB_WORKSPACE"`（或 `.`）。

## 3. GitLab CI

```yaml
pitax-audit:
  image: python:3.11
  script:
    - pip install -r requirements.txt
    - python -m codeark.cli . --dry --formats json,sarif --out audit-out
    # 策略门脚本不随仓提供（scripts/ci_gate.py 从未入库）——请内联 §5 的
    # python 片段实现"CRITICAL/HIGH 阻断"，阈值由你的仓库分级策略定
  artifacts:
    paths:
      - audit-out/
    expire_in: 7 days
```

## 4. 本地 / pre-commit

```bash
python -m codeark.cli . --dry --formats markdown --out reports/precommit
```

`.pre-commit-config.yaml` 片段（可选）：

```yaml
repos:
  - repo: local
    hooks:
      - id: pitax-audit
        name: PITAX deterministic scan
        entry: python -m codeark.cli . --dry --formats json --out .pitax-precommit
        language: system
        pass_filenames: false
```

## 5. 策略门参考（CRITICAL/HIGH 阻断）

```bash
python - <<'PY'
import json, sys
report = json.load(open("audit-out/report.json", encoding="utf-8"))
bad = [f for f in report.get("findings", [])
       if str(f.get("severity", "")).lower() in {"critical", "high"}]
print(f"findings={len(report.get('findings', []))} critical_or_high={len(bad)}")
sys.exit(1 if bad else 0)
PY
```

建议从"只报告不阻断"起步，把 `critical` 单独设为阻断阈值，再根据自身基线收紧。

## 6. 与完整流水线的边界

- `--dry`：Agent0 规则层 + 确定性工具，零模型调用，秒级；
- 完整六段流水线需要模型端点（本地委员会见 `deploy/mi300x-oneclick.sh`），
  预检用 `python scripts/check_endpoints.py`；
- SARIF 在两种模式下同构，CI 只需要确定性层时建议永远用 `--dry`。