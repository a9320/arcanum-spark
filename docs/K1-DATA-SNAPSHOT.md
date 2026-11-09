# K1 题库快照与数据前置闸（2026-11-09）

> 背景：上游 `NYU-LLM-CTF/NYU_CTF_Bench` 的 HEAD 已删除 manifest 20 题中的 19 题
> （11-08 实锤：`removed×14 + test×5` 仅在历史提交里）。DSW 的旧克隆曾是唯一实物。
> 2026-11-09 夜从 GitHub 历史提交重建快照，并做成可复现、可校验的仓库资产。

## 1. 快照身份

| 项 | 值 |
| --- | --- |
| 来源 | `NYU-LLM-CTF/NYU_CTF_Bench` 提交 `4c5744f55a31a58e03d6118c9dbb1c18e5bbdfa9`（2025-09-22） |
| 范围 | `data/m8_k1_manifest.json` 的 20 个 `upstream_path` |
| 体量 | **557 文件 / 50,602,114 B** |
| 清单 sha256 | `e3f957d8b6e5708a659be66b7aa6986b7871f6cd94671adc2c0b8a6a98534595`（`data/nyu_k1_20tasks.sha256`，557 行） |
| 双源验证 | W7900 直连 api 与本机经 gh-proxy 两次独立抓取，清单 sha 逐字节一致 |
| 本机落点 | `D:\nyu-backup\nyu-bench-4c5744f`（另 tar 35M） |

**入仓的只有文件哈希清单**（`data/nyu_k1_20tasks.sha256`），题目内容不入仓。

## 2. 三个命令

```bash
# 抓取（任何机器；GitHub 直连不通时换 --api-base 走镜像）
python scripts/fetch_nyu_k1_snapshot.py --out D:/nyu-backup/nyu-bench-4c5744f

# 换提交（例如 DSW 旧克隆的 HEAD 不是 4c5744f）
python scripts/fetch_nyu_k1_snapshot.py --out <dir> --sha <DSW HEAD>

# 数据前置闸（零模型、零网络；K1 开跑前必跑）
python scripts/k1_data_check.py --corpus <dir> --sha-list data/nyu_k1_20tasks.sha256
```

`k1_data_check.py` 校验三件：manifest 自身 sha（与 `k1_rescore.sh` 同钉值）、20 题目录存在且非空、
逐文件 sha 与清单一致。全绿输出 `PASS: K1 题库数据完整`，退出码 0。

## 3. 网络事实（2026-11-09 实测，供别的窗口抄）

- `github.com` 的 git 通道：本机被 hosts 里 Steam++ 的 `127.0.0.1` 条目挡住（`curl` 000）；
  W7900 容器被集群出口代理 `CONNECT 503` 拒绝。**两边都不能靠 git clone**。
- `raw.githubusercontent.com` 与常见加速镜像：两边均不可用。
- **可用**：`api.github.com`（W7900 直连 200；本机需 `--resolve` 绕 hosts 或经镜像）、
  `codeload.github.com`（本机 15KB/s / W7900 168KB/s）、`gh-proxy.com` **能转发 api.github.com
  且透传 Authorization**（本机实测树清单 10.6MB/4s，557 文件 267s 全成）。
- 本机 `sha256sum` 默认二进制模式会输出 `hash *path`，与 Linux `hash  path` 不同；
  生成跨机清单用 `sha256sum -t` 归一。

## 4. 待核项（下个 DSW 窗第一件事）

```bash
git -C /mnt/workspace/NYU_CTF_Bench rev-parse HEAD
```

- 等于 `4c5744f…` → 快照与 10-03 基线的数据源逐字节同源，K1 可直接用；
- 不等于 → 用 `--sha <该值>` 重抓，再跑 `k1_data_check.py` 与现有清单比对，差异如实登记。
- 无论哪种，DSW 侧仍要按执行单 §10 做 bundle/整树 tar 备份（持久区双副本）。
