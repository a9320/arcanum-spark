# 冒烟脚本（非 pytest 套件）

历史联通性探针（黑客松冲刺期产物）：验证免费模型经 Strands 接入 + 工具调用闭环。

2026-09-30 从 `codeark/tests/` 迁出并去 `test_` 前缀：它们没有测试函数，
且模块层读取本机 API key 文件（`/mnt/d/API Key/` 或 `D:/API Key/`），留在
tests/ 时曾导致干净环境 pytest 收集报错（verify.sh 第 1 步假红）。

运行方式：`python scripts/smoke/model_connect_smoke.py`（需 key 文件在位）。
