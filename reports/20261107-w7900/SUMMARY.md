# W7900/gfx1100 移植性首证窗口 —— 证据与结论（2026-11-07，终版）

环境：Ubuntu 24.04（容器）/ ROCm **7.2.1**（HIP 7.2.53211，与 DSW gfx942 同族版本）/ llama.cpp
`-DGGML_HIP=ON -DAMDGPU_TARGETS=gfx1100` 源码构建 / gpt-oss-20b-MXFP4（字节锚 12109566624 逐位对账）。
驱动：`scripts/run-verify-tiers.py`（钉假设集=reports/20261102-harden/reuse-r1，N=5 × 4 假设，
证据包=synthetic_from_snippet 已披露；MI300X 参照判决仅观察）。

## 冒烟（块 2）

- decode **135.05 t/s** / prompt eval 255 t/s（对照 MI300X 短答 146 t/s 基线，同量级）；
  verify 级长 prompt（2274 tokens）prompt eval **2949 t/s**
- VRAM **12.05 GiB**（f16 KV）→ **11.76 GiB**（q8_0 KV，32k ctx 仅省 0.29 GiB——B1 的 13.9G
  大收益属 r1 131072 ctx 场景，gpt-oss 32k 下 KV 量化收益有限）
- 🔴 移植性发现 ①：MXFP4 在 RDNA3 **原生加载成功**（本窗最大未知数排除）
- 🔴 移植性发现 ②：`Flash Attention over K/V rows not supported → disabled` 告警**仅在 4 槽
  启动日志出现**，np1 两实例日志无此告警（f16_g/kv8_h grep 均 0 命中）——回退路径疑似与多槽
  unified 配置相关，留档供后续归因

## 微基准八批全表（temp=0 除标注外）

| 批 | KV | 槽位 | verdict 翻转 | 结果 |
| --- | --- | --- | --- | --- |
| temp0.8（INVALID，已标注废弃） | f16 | 4 | H1/H3/H4（0.8 采样噪声） | FAIL |
| t0-a | f16 | 4 | H3（1/5 孤例 U0.3） | FAIL |
| t0-b | f16 | 4 | 0（H1 档漂 0.95×2/0.9×3） | FAIL |
| t0-np1-c | f16 | 1 | H3（1/5 孤例） | FAIL |
| t0-np1-d | f16 | 1 | 0（四假设全 IDENTICAL） | **PASS** |
| t0-kv8-e | q8_0 | 1 | H3（**U 优势 4/5**）+H4 | FAIL |
| t0-kv8-f | q8_0 | 1 | 0（**H3=U0.3 稳定**） | PASS |
| t0-f16-g | f16 | 1 | H3（1/5 孤例） | FAIL |
| t0-kv8-h | q8_0 | 1 | H3（**U 优势 4/5**）+H4 | FAIL |

## 头条结论：B1 的"KV q8_0 判决中性"是 gfx942 特性，不外推到 gfx1100

H3（边缘假设）跨实例分布（实例配对，排除实例级混沌）：

| KV | 实例 | H3 分布 | 合计 |
| --- | --- | --- | --- |
| f16 | #1(a)/#2(b,c)/#4(g) | 每实例 C 4–5/5 | **C22 / U3**（25 run） |
| q8_0 | #3(e)/#5(h) | 每实例 C 仅 0–1/5 | **C2 / U13**（15 run） |

- q8_0 下 9/10 U 偏离按 f16 基率（3/25）纯巧合概率 ~10⁻⁹ 量级——**系统性 U 倾斜，非噪声**
- H4 同向弱信号：q8_0 两实例各 1 次 U0.3 离开，f16 五实例 0 次
- H1/H2/H4 的 modal 判决+档位在两种 KV 下完全一致——**中性只对非边界假设成立**
- 对照锚：gfx942 六卷严格 IDENTICAL（含 KV q8_0 与 f16 对照）⇒ 判决中性在 gfx942 成立

## 其余结论（前哨口径，不替代 DSW Exp A 预注册实验）

1. **漏钉温度 = 采样噪声假 FAIL**：llama.cpp 不下发 temperature 时走 server 默认 **0.8**；
   验收条件三件套（TEMPERATURE=0/EVIDENCE_STRICT=1/PLAIN_JSON=1）必须整组对齐——driver 已修
   （setdefault，2bcdd1f）。
2. **RDNA3 构建级 sporadic 数值非确定性（f16）**：f16 累计 25 run 中 H3 孤例翻 3 次、
   H1/H2 档抖各 1–3 次；批间随机、np1 批 d 四假设全 IDENTICAL（与 gfx942 六卷 IDENTICAL
   同形态）；短 prompt 10 连 curl 全同 ⇒ 边缘只在长上下文 prefill（缓存命中态/批组成）出现。
3. **Exp A 前哨 = inconclusive on RDNA3**；正式裁决场仍是 DSW Exp A（gfx942）。
4. 参照偏离（H1/H2 与 MI300X 反向等）= 合成证据包只含 snippet 行所致（预告内，非硬件差异）；
   治理链路本身工作正常（模型正确执行"无 E2 反证不得 REFUTED"等纪律）。

## 日志补证（raw 五份入 `logs/`，盒上 du 字节数逐位对账）

1. **FA-KV 告警 ↔ 配置绑定实锤**：4 槽日志 `n_slots=4, kv_unified='true'` 且 FA 告警在；
   三个 np1 日志 `n_slots=1, kv_unified='false'` 且**无** FA 告警——回退路径与 unified 多槽配置绑定。
2. **缓存态扰动直接证据**：np1 单槽下逐请求仍走 `selected slot by LCP similarity`，
   `f_keep` 在 **0.478–0.967** 间大幅波动 ⇒ 顺序同 prompt 调用的缓存保留比例不稳定，
   正是长上下文 prefill 数值边缘的来源（与微基准批间随机翻转吻合）。
3. **q8_0 KV 解码开销**：tg ≈ **126.2–128.1 t/s** vs f16 ≈ **134.6–137.1 t/s**（RDNA3 上 **−7%**）；
   gfx942 B1 曾实测墙钟无差异——第三个跨架构差异点。
4. prompt eval ~2.9–3.5k t/s（2274-token verify prompt）；`truncated=0` 全程。

## temp=0 累计分布（f16 25 run + q8_0 15 run = 40 run × 4 假设）

- H1：C×40/40（0.95×34、0.9×4、0.75×2）
- H2：U×40/40（0.3×37、0.5×3）
- H3：f16 C22/U3；q8_0 C2/U13（0.95 与 0.3 之间无中间档）
- H4：R×38、U×2（均在 q8_0；0.95×38、0.3×2）
- elapsed：17–33s/run（4 次调用）
