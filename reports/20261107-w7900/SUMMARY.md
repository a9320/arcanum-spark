# W7900/gfx1100 移植性首证窗口 —— 证据与结论（2026-11-07）

环境：Ubuntu 24.04（容器）/ ROCm **7.2.1**（HIP 7.2.53211，与 DSW gfx942 同族版本）/ llama.cpp
`-DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100` 源码构建 / gpt-oss-20b-MXFP4（字节锚 12109566624 逐位对账）。
驱动：`scripts/run-verify-tiers.py`（钉假设集=reports/20261102-harden/reuse-r1，N=5 × 4 假设，
证据包=synthetic_from_snippet 已披露；MI300X 参照判决仅观察）。

## 冒烟（块 2）

- decode **135.05 t/s** / prompt eval 255 t/s（对照 MI300X 短答 146 t/s 基线，同量级）
- VRAM **12.05 GiB**（48G 卡余量巨大）；`n_slots=4, n_ctx_slot=32768, kv_unified`
- 🔴 移植性发现：`Flash Attention over K/V rows not supported → disabled`（gfx1100 本构建无 FA-KV
  融合算子，自动回退；功能无损）
- MXFP4 在 RDNA3 **原生加载成功**（本窗最大未知数排除）

## 微基准五批全表

| 批 | 温度 | 槽位 | verdict 翻转 | tier 漂移 | 结果 |
| --- | --- | --- | --- | --- | --- |
| temp0.8（INVALID，已标注废弃） | 0.8（server 默认） | 4 | H1/H3/H4 | 多档 | FAIL |
| t0-a | 0 | 4 | H3（1/5 孤例 U0.3） | H1 0.95×4/0.9×1 | FAIL |
| t0-b | 0 | 4 | 0 | H1 0.95×2/**0.9×3** | FAIL |
| t0-np1-c | 0 | 1 | H3（1/5 孤例 U0.3） | H1 +0.75×1、H2 +0.5×1 | FAIL |
| t0-np1-d | 0 | 1 | 0 | 0（四假设全 IDENTICAL） | **PASS** |

## 结论（前哨口径，不替代 DSW Exp A 预注册实验）

1. **漏钉温度 = 采样噪声假 FAIL**：llama.cpp 不下发 temperature 时走 server 默认 **0.8**；
   验收条件三件套（TEMPERATURE=0/EVIDENCE_STRICT=1/PLAIN_JSON=1）必须整组对齐——driver 已修
   （setdefault，2bcdd1f）。
2. **槽位混淆排除**：np=1 批 C 仍翻 → 残余不稳非多槽缓存历史独有。
3. **RDNA3 构建级数值非确定性（真发现）**：temp=0 累计 20 run × 4 假设 = 80 次调用，
   verdict 翻转 2 次（H3，均 1/5 孤例走保守分支）、档位抖 ~6 次（0.95↔0.9↔0.75 相邻档），
   批间随机（c 翻 d 全稳，d 与 MI300X 六卷"签名 IDENTICAL"同形态）——推理链放大单 token 边缘翻格。
   对照锚：gfx942 六卷严格 IDENTICAL。归因层次待裸 curl 探针补锤（引擎层 vs 客户端栈）。
4. **Exp A 前哨 = inconclusive on RDNA3**；正式裁决场仍是 DSW Exp A（gfx942）。
5. 参照偏离（H1 C vs U、H2 U vs C 等）= 合成证据包只含 snippet 行所致（预告内，非硬件差异）；
   治理链路本身工作正常（模型正确执行"无 E2 反证不得 REFUTED"等纪律）。

## temp=0 累计分布（80 次调用）

- H1：C×20/20（0.95×15、0.9×4、0.75×1）
- H2：U×20/20（0.3×19、0.5×1）
- H3：C×18、U×2（0.95×18、0.3×2）
- H4：R×20/20（0.95×20）
- elapsed：17–33s/run（4 次调用），np=1 批 d 全程 22.6–22.8s
