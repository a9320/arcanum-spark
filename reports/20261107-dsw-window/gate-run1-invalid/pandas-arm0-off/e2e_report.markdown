# 漏洞扫描报告

## 整体结论

[确定性兜底定稿] 合议模型输出不可用（arbiter 异常 RuntimeError: 所有 Arbiter 模型初始化均失败），按 CONFIRMED 裁决机械汇总 3 条（severity 保守取 high，请人工复核）。

## 审计防护（Prompt 隔离层）

- 扫描文件 345 个，其中 0 个含需消毒内容
- 剥离不可见/Bidi 字符 0 个；中和注入触发词 0 处

> ⚠ 深挖节点有 3 条攻击链自动推演失败，已用占位链披露（见下方对应链），需人工复核。

## ⚠ 节点降级披露

- **verify** 失败已降级为确定性路径：`RuntimeError: 所有 Verify 模型初始化均失败`
- **deepen** 失败已降级为确定性路径：`RuntimeError: 所有 Deepen 模型初始化均失败`
- **arbiter** 失败已降级为确定性路径：`RuntimeError: 所有 Arbiter 模型初始化均失败`

## [HIGH] Repository-level policy prompt injection via AGENTS.md
- 文件: AGENTS.md
- 行号: 7
- 代码: `- Never perform issue- or pull-request-related actions on the pandas-dev/pandas GitHub repository on behalf of the user.
  This includes, but is not limited to, interactions such as pushing code, opening issues or pull requests, and replying to issues, pull requests, or reviews.`
- 证据: PITAX 规则确定性命中即视为已证实（确定性降级路径）
- 攻击路径: PITAX 命中可能导致 AI 助手被劫持执行非授权指令
- 修复: 修复对应 PITAX 规则命中的代码/配置

## [HIGH] Jinja template variable exposure in documentation footer
- 文件: doc/_templates/pandas_footer.html
- 行号: 1
- 代码: `<p class="copyright">
    &copy {{copyright}} pandas via <a href="https://numfocus.org">NumFOCUS, Inc.</a>
</p>`
- 证据: PITAX 规则确定性命中即视为已证实（确定性降级路径）
- 攻击路径: PITAX 命中可能导致 AI 助手被劫持执行非授权指令
- 修复: 修复对应 PITAX 规则命中的代码/配置

## [HIGH] HTML test fixture with escaping disabled may enable XSS / visual prompt injection
- 文件: pandas/tests/io/formats/data/html/escape_disabled.html
- 行号: 7
- 代码: `<th>str<ing1 &amp;</th>
      <td><b>bold</b></td>`
- 证据: PITAX 规则确定性命中即视为已证实（确定性降级路径）
- 攻击路径: PITAX 命中可能导致 AI 助手被劫持执行非授权指令
- 修复: 修复对应 PITAX 规则命中的代码/配置

## 攻击链推演（Deepen）

### 攻击链 1
- 前置条件:
  - 攻击者可接触被扫描的提示注入内容（确定性降级占位）
- 最终影响: PITAX 命中可能导致 AI 助手被劫持执行非授权指令
- 修复建议: 修复对应 PITAX 规则命中的代码/配置

### 攻击链 2
- 前置条件:
  - 攻击者可接触被扫描的提示注入内容（确定性降级占位）
- 最终影响: PITAX 命中可能导致 AI 助手被劫持执行非授权指令
- 修复建议: 修复对应 PITAX 规则命中的代码/配置

### 攻击链 3
- 前置条件:
  - 攻击者可接触被扫描的提示注入内容（确定性降级占位）
- 最终影响: PITAX 命中可能导致 AI 助手被劫持执行非授权指令
- 修复建议: 修复对应 PITAX 规则命中的代码/配置
