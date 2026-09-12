# evidence/ — 评委证据包

> 全部素材来自真实运行产物，可一键复现：`bash verify.sh`（全确定性，零 LLM API）。

## 清单

| 文件 | 内容 | 生成方式 |
|---|---|---|
| `e2e_report.json` / `.markdown` / `.sarif` | 第三次真实端到端（2026-09-11）定稿报告：7 条 findings、8 条攻击链、隔离统计、降级披露 | `python test_e2e.py`（真实 LLM，约 30 分钟） |
| `e2e_report_EN.md` | 上报告的英文对照版（供国际评委阅读；中文原稿为准） | 人工忠实翻译自 `e2e_report.markdown` |
| `anti-injection-quotes-0911.md` | 模型面对注入诱饵"只当数据、如实上报"的日志原话摘录（含行号） | 摘自 `reports/e2e_run_0911.log` |
| `verify-run.md` | 一键验证 4/4 通过输出：测试套件、dry 秒扫、eval 回归校验、干净仓 FP=0 | `bash verify.sh` |

## 关键数字（e2e #3，2026-09-11）

- Agent0 PITAX 确定性命中：**12**（9 文件）
- Scout 假设 / Verify 裁决：8 / 8（全部 CONFIRMED）
- 合议定稿：**7 条**（2 条隐形字符按 file+vuln_type 口径合并）
- **risk_score 24 = 3×critical(4) + 4×high(3)**——首次由定稿 findings 计算（旧版恒 22）
- Prompt 隔离层：9 文件中 5 个被消毒，剥离 6 个不可见字符，中和 9 处注入触发词
- 降级披露：7/8 攻击链因模型配额 429 走占位链并逐条标注（诚实工程实例）

## 复现命令

```bash
bash verify.sh                                  # 测试+秒扫+eval 校验+FP=0（零 API）
python eval/check_report.py --report evidence/e2e_report.json   # 对真实报告跑回归
python test_e2e.py                              # 完整真实链路（慢，烧免费额度）
```

> 注：`evidence/e2e_report.json` 中所有 `org-*`/`ak-*` 凭证标识已脱敏为 `[REDACTED-CREDENTIAL]`（9/12 修复，raw 错误节选进报告前自动掩码）。
