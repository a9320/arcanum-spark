# M8/K1：CTF flag 真值审计集 — 设计协议 v0

定位：军规兼容的**独立真值来源**。现行难卷/R3 难负均为手工构造（anti-leak 保证
不泄题，但本质是"我们出题我们判"）；CTF flag 是客观真值——**能拿 flag ⇒ 漏洞真实
可利用**，不需要任何模型或人工裁判。这是 Laya/管线从"考卷优胜"走向"实战可信"的一公里。

## 一、真值协议（flag → 判分口径）

每题 = 一个 challenge 仓（源码 + docker-compose + 官方 flag + 官方类目）。
管线对 challenge 源码仓跑全链（与 M3 三臂同口径），判分：

| 口径 | 定义 | 说明 |
|---|---|---|
| TP | intended 类目（官方 writeup 类别）的假设被 CONFIRMED | flag 即可利用性证明，无需人工核对 |
| FN | intended 类目无假设，或全被 PRUNE/REFUTED | **REFUTED-on-intended = 独立口径 FP**（模型裁判错了，flag 说了算）——这是 M8 区别于 M3 的核心增量 |
| Unplanned | 非 intended 类目的 CONFIRMED | 单列，**不自动计 FP**——可能真但超纲，逐条人工复核后才定性 |
| 规则/单agent 臂 | 同卷同口径 | 与 M3 消融表接续，构成"增益×真值"二维答案 |

## 二、候选真值源对表（2026-09-30 实查 license）

| 源 | 规模 | license（实测口径） | 形态 | 适配度 |
|---|---|---|---|---|
| **NYU CTF Bench**（NYU-LLM-CTF/NYU_CTF_Bench，NeurIPS 2024，arXiv 2406.05590） | **200 题** + dev 55 题，6 类目（web/pwn/forensics/rev/crypto/misc），CSAW 2017-23 | bench **代码 GPL-2.0**（只消费数据不拷代码）；题目=公开竞赛工件汇编，数据集随仓分发（`test/`） | docker-compose 部署、`chal.flag` 官方真值 | **首选**：web 类有源码可静态扫；规模最大；flag 全验证 |
| **cybench**（andyzorigin/cybench，Stanford，arXiv 2408.08926） | 40 题 × 4 赛站（HackTheBox/SekaiCTF/Glacier/HKCert） | **Apache-2.0**（GitHub API 2026-09-30 实查） | docker + 分级子任务 | 副源：题少质高；**HTB 源题授权需逐题复核** |
| InterCode-CTF / picoCTF | ~100 题 | 未核 | 教育向 | 备选：web 源码偏浅 |
| Juliet/SARD（NIST） | 数千合成用例 | public domain | C/C++/Java + 官方 CWE 标注 | 非 CTF（无 flag），作 K2 补充真值源 |

## 三、防泄漏与纪律

- challenge 仓**永不进任何训练集**（records_* 只来自既有 pipeline 产出）；hard_exam held-out 地位不变。
- 跨题去重：同源 patched/重复 challenge 检测后再入库。
- 判分脚本输出逐题 JSON（intended_class / flag / pipeline 裁决 / 判分四元组），**缺失=null 不猜**，与消融器同纪律。
- 数据不 rehost：脚本从上游仓原位消费，license 声明与 THIRD_PARTY_NOTICES 同层登记。

## 四、schema 与分阶段

- 不复用 gate-dataset/1（M8 目标是**裁决审计**，不是 gate 训练）：直接吃 e2e 报告
  （meta.agent0_findings + hypothesis_set + verifications），判分层只加"intended_class"一列。
- **K1-min（先行）**：手选 20 题 web 类（源码可静态分析），DSW 跑通端到端 + 人工核对判分脚本，
  产出第一张"独立真值对照表"。
- **K1-full**：200 题 dockerize 批跑（依赖容器环境）。
- **风险登记**：①DSW pod 未必有 docker——fallback=纯静态源码分析不提 flag，真值=官方
  intended class 静态对照（强度降级但独立性不变）；②GPL-2.0 传染面=仅 bench 代码，消费
  数据集不触发；③web 类题量待统计（200 题中 web 占比决定 K1-full 实际规模）。

## 更新记录

- 2026-09-30 v0（外部审计"手工构造不代表真实分布"整改的长期方案立项；license 实查口径见上表）。
