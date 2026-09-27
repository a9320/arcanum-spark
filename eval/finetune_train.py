#!/usr/bin/env python3
"""finetune_train：Laya R0 单卡微调（MI300X/ROCm，官方 Kaggle 2xT4 notebook 的单卡化）。

官方资产链（2026-09-27 侦察定案）：
- 训练方法论 = GitHub NandhaKishorM/laya notebooks/laya_finetune_typed_decisions_2xT4_kaggle.ipynb
  （HF repo 无任何训练脚本；README 明示 notebook 即微调入口）。本脚本 = 其 cell 8
  （train_ddp.py）的单卡改写：去 DDP/nccl；import 从 pip 包 laya 改为 checkpoint 自带的
  vendor rl_common.py（与 checkpoint 同源，零新依赖）；数据层从 LocalLLaMA/typed-decisions
  官方数据集换成 eval/finetune_export 产出的 records.jsonl。
- RLCD 循环照抄官方：零均值高斯 logit 噪声探索（σ 0.4→0.1 线性退火）+ proper_reward
  群基线（w_sph=0.75，GRPO 风格 adv 归一）+ policy gradient + 1.0 权重 soft-CE 引导；
  每 epoch 滚动存 checkpoint，训练后 LBFGS 温度拟合（calib<10 返回 1.2，同官方 fallback）。
- R0 定调：31 条自产数据、同卷重考只验管道不出结论；温度拟合真正生效要等 R1 数据扩容。
- state 兼容：records 的 state 是 str（_laya_state 输出），官方 notebook 是 dict——
  build_sequence → serialize_state 两者皆收（str 直通），无需转换。

用法（DSW）：
    python eval/finetune_train.py \
        --model-dir /mnt/workspace/models/laya/typed-decisions \
        --records /mnt/workspace/runs/records_r0.jsonl \
        --out /mnt/workspace/models/laya-r0
输出 out/：model.safetensors + encoder/ + tokenizer/ + rl_agent_config.json（fine_tuned=true、
temperature 已拟合、temperature_by_options 移除——per-type 拟合会被桶覆盖遮蔽，同官方）
+ checkpoint_meta.json + vendor rl_agent_api.py/rl_common.py（replay score --backend laya
--model 直指所需的加载件）。
"""
import argparse
import importlib.util
import json
import os
import random
import shutil
import sys
import time
from pathlib import Path


def load_rl_common(model_dir: str):
    """从 checkpoint 目录加载 vendor rl_common.py（build_model/proper_reward/QTYPES）。

    与 _load_laya_agent 同模式：模型目录自带脚本，sys.path 插入后 importlib 加载。
    """
    path = Path(model_dir) / "rl_common.py"
    if not path.exists():
        raise FileNotFoundError(f"未找到 {path}——checkpoint 目录须自带 vendor rl_common.py"
                                "（typed-decisions 曾缺失，从 laya 根目录 cp 补）")
    sys.path.insert(0, str(Path(model_dir)))
    spec = importlib.util.spec_from_file_location("laya_rl_common", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def parse_records(path: str) -> list[dict]:
    """records.jsonl → 扁平训练条目（纯逻辑，零 torch）。

    每条 record 的每个 question 展开一项：{state, q:{t,ins,crit}, y, meta}。
    校验内部键名契约（t/ins/crit/y——finetune_export 产出；混入外部 API 键名
    instructions/criteria 会在 build_sequence KeyError，此处提前报错给出修正方向）。
    """
    items = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if "state" not in rec or not rec.get("qs"):
                raise ValueError(f"第 {ln} 行缺 state/qs——不是 finetune_export 产出的 records")
            for qi, q in enumerate(rec["qs"]):
                missing = {"t", "ins", "crit", "y"} - set(q)
                if missing:
                    raise ValueError(f"第 {ln} 行第 {qi} 题缺内部键 {sorted(missing)}"
                                     "（instructions/criteria 是推理侧键名，训练须 ins/crit）")
                if not 0 <= q["y"] < len(q["crit"]):
                    raise ValueError(f"第 {ln} 行第 {qi} 题 y={q['y']} 超出选项范围")
                items.append({"state": rec["state"], "q": {"t": q["t"], "ins": q["ins"], "crit": q["crit"]},
                              "y": q["y"], "meta": rec.get("meta", {}), "line": ln})
    if not items:
        raise ValueError(f"{path} 无有效条目")
    return items


def split_calib(items: list[dict], calib_frac: float, seed: int) -> tuple[list[dict], list[dict]]:
    """固定种子切出校准片（不进训练批次）——官方注释：在训过的题上拟温度=测拟合而非校准。"""
    order = list(range(len(items)))
    random.Random(seed).shuffle(order)
    n_calib = min(int(len(items) * calib_frac), len(items) // 2) if calib_frac > 0 else 0
    calib = [items[i] for i in sorted(order[:n_calib])]
    train = [items[i] for i in sorted(order[n_calib:])]
    return train, calib


def main() -> int:
    ap = argparse.ArgumentParser(description="Laya R0 单卡 RLCD 微调（官方 notebook 单卡化，吃 records.jsonl）")
    ap.add_argument("--model-dir", required=True, help="底座 checkpoint（含 rl_agent_config.json/tokenizer/encoder/model.safetensors/rl_common.py）")
    ap.add_argument("--records", required=True, help="finetune_export 产出的 records.jsonl")
    ap.add_argument("--out", required=True, help="输出 checkpoint 目录")
    ap.add_argument("--epochs", type=int, default=4)
    ap.add_argument("--micro-batch", type=int, default=32, help="MI300X 192G，默认 32（官方 2xT4 为 8/GPU）")
    ap.add_argument("--grad-accum", type=int, default=2, help="有效 batch=32×2=64，对齐官方 2×8×4")
    ap.add_argument("--group-size", type=int, default=4, help="GRPO 基线采样数")
    ap.add_argument("--lr-encoder", type=float, default=2.5e-5)
    ap.add_argument("--lr-head", type=float, default=1.0e-4)
    ap.add_argument("--sigma-start", type=float, default=0.4)
    ap.add_argument("--sigma-end", type=float, default=0.1)
    ap.add_argument("--calib-frac", type=float, default=0.15, help="校准片占比（固定种子切分，不进训练）")
    ap.add_argument("--seed", type=int, default=20260927)
    ap.add_argument("--max-len", type=int, default=1024)
    ap.add_argument("--head-max-len", type=int, default=256)
    args = ap.parse_args()

    try:
        import torch
        from safetensors.torch import load_file, save_file
        from transformers import AutoTokenizer
    except ImportError as e:
        print(f"[finetune_train] 缺训练依赖（torch/safetensors/transformers）：{e}\n"
              "  DSW 上已随 score_laya 验证安装；本地 Windows venv 无 torch，属预期。")
        return 1

    rc = load_rl_common(args.model_dir)
    model_dir = Path(args.model_dir)
    with open(model_dir / "rl_agent_config.json", encoding="utf-8") as f:
        cfg = json.load(f)
    cfg.update({"gradient_checkpointing": True, "max_tokens_per_batch": 4096,
                "max_len": args.max_len, "head_max_len": args.head_max_len})

    tok = AutoTokenizer.from_pretrained(str(model_dir / "tokenizer"))
    records = parse_records(args.records)
    train_rec, calib_rec = split_calib(records, args.calib_frac, args.seed)

    def build_items(rows: list[dict]) -> list[dict]:
        items = []
        for r in rows:
            seq, markers = rc.build_sequence(tok, r["state"], r["q"], cfg["max_len"], cfg["head_max_len"])
            k = len(rc.render_options(r["q"]))
            if len(markers) != k:
                continue  # 官方同款：选项装不下宁可跳过，不训截断答案空间
            target = [1.0 if i == r["y"] else 0.0 for i in range(k)]  # one-hot（无 soft 标签）
            items.append({"ids": seq, "markers": markers, "qtype": rc.QTYPES[r["q"]["t"]],
                          "target": target, "label": r["y"], "meta": r["meta"]})
        return items

    train_items = build_items(train_rec)
    calib_items = build_items(calib_rec)
    print(f"[finetune_train] records {len(records)} → train {len(train_items)} + calib {len(calib_items)}"
          f"（构建失败跳过 {len(train_rec) + len(calib_rec) - len(train_items) - len(calib_items)}）")
    if not train_items:
        print("[finetune_train] 无可训练条目")
        return 1

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = rc.build_model(cfg, encoder_dir=str(model_dir / "encoder"))
    model.load_state_dict(load_file(str(model_dir / "model.safetensors")), strict=True)
    model.encoder.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.head_checkpointing = True
    model.to(device)
    model.train()

    enc_params = [p for n, p in model.named_parameters() if "encoder." in n]
    head_params = [p for n, p in model.named_parameters() if "encoder." not in n]
    optimizer = torch.optim.AdamW([
        {"params": enc_params, "lr": args.lr_encoder},
        {"params": head_params, "lr": args.lr_head},
    ], weight_decay=0.01)
    total_updates = max(1, (len(train_items) // (args.micro_batch * args.grad_accum)) * args.epochs)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=total_updates, eta_min=1e-6)
    scaler = torch.amp.GradScaler("cuda", enabled=device.type == "cuda")

    EPOCHS, MICRO_BATCH, GRAD_ACCUM, GROUP_SIZE = args.epochs, args.micro_batch, args.grad_accum, args.group_size
    print(f"[finetune_train] device={device} | epochs {EPOCHS} | micro {MICRO_BATCH}×accum {GRAD_ACCUM}"
          f" | group {GROUP_SIZE} | σ {args.sigma_start}→{args.sigma_end}")
    t0 = time.time()

    def collate(chunk):
        n = len(chunk)
        L = max(len(it["ids"]) for it in chunk)
        kmax = max(len(it["markers"]) for it in chunk)
        ids = torch.full((n, L), tok.pad_token_id, dtype=torch.long)
        att = torch.zeros((n, L), dtype=torch.long)
        mpos = torch.zeros((n, kmax), dtype=torch.long)
        mmask = torch.zeros((n, kmax), dtype=torch.bool)
        target = torch.zeros((n, kmax), dtype=torch.float32)
        for i, it in enumerate(chunk):
            ids[i, :len(it["ids"])] = torch.tensor(it["ids"])
            att[i, :len(it["ids"])] = 1
            k = len(it["markers"])
            mpos[i, :k] = torch.tensor(it["markers"])
            mmask[i, :k] = True
            target[i, :len(it["target"])] = torch.tensor(it["target"], dtype=torch.float32)
        return {"input_ids": ids, "attention_mask": att, "marker_pos": mpos, "marker_mask": mmask,
                "target": target, "qtype": torch.tensor([it["qtype"] for it in chunk])}

    def save_checkpoint(out_dir: Path, temps: list[float] | None, epoch: int, avg_loss: float):
        out_dir.mkdir(parents=True, exist_ok=True)
        sd = {k: v.half().contiguous().cpu() for k, v in model.state_dict().items()}
        save_file(sd, str(out_dir / "model.safetensors"))
        model.encoder.config.save_pretrained(str(out_dir / "encoder"))
        tok.save_pretrained(str(out_dir / "tokenizer"))
        for vendor in ("rl_agent_api.py", "rl_common.py"):  # score_laya --model 直指所需加载件
            src = model_dir / vendor
            if src.exists():
                shutil.copy2(src, out_dir / vendor)
            else:
                raise FileNotFoundError(
                    f"底座缺 {vendor}：输出 checkpoint 将无法被 RLAgent 直读。"
                    "请从 laya 根目录 cp 两 vendor 脚本后重跑（score_laya --model 直指所需加载件）"
                )
        out_cfg = dict(cfg)
        out_cfg["fine_tuned"] = True
        out_cfg["model_name"] = "laya-r0-arcanum"
        if temps is not None:
            out_cfg["temperature"] = temps
            out_cfg.pop("temperature_by_options", None)  # per-type 拟合会被桶覆盖遮蔽（官方口径）
        with open(out_dir / "rl_agent_config.json", "w", encoding="utf-8") as f:
            json.dump(out_cfg, f, indent=2)
        with open(out_dir / "checkpoint_meta.json", "w", encoding="utf-8") as f:
            json.dump({"epoch": epoch, "total_epochs": EPOCHS, "avg_loss": avg_loss,
                       "train_items": len(train_items), "calib_items": len(calib_items),
                       "base": str(model_dir), "records": args.records}, f, indent=2)

    for epoch in range(EPOCHS):
        random.seed(args.seed + epoch)
        random.shuffle(train_items)
        epoch_loss, n_batches, accum = 0.0, 0, 0
        optimizer.zero_grad(set_to_none=True)
        progress = epoch / max(1, EPOCHS - 1)
        sigma = args.sigma_start + (args.sigma_end - args.sigma_start) * progress

        for b_idx in range(0, len(train_items), MICRO_BATCH):
            chunk = train_items[b_idx:b_idx + MICRO_BATCH]
            if not chunk:
                continue
            batch = collate(chunk)
            with torch.autocast("cuda", dtype=torch.float16, enabled=device.type == "cuda"):
                logits, _ = model(batch["input_ids"].to(device), batch["attention_mask"].to(device),
                                  batch["marker_pos"].to(device), batch["marker_mask"].to(device),
                                  batch["qtype"].to(device))
            logits = logits.float()
            mask = batch["marker_mask"].to(device)
            k = mask.sum(-1, keepdim=True).float()
            target = batch["target"].to(device)

            # 1) G 组零均值高斯 logit 噪声探索（官方 cell 8 照抄）
            eps = torch.randn((GROUP_SIZE,) + logits.shape, device=device) * sigma * mask
            eps = (eps - eps.sum(-1, keepdim=True) / k) * mask
            z = logits.detach().unsqueeze(0) + eps
            q = torch.softmax(z.masked_fill(~mask, -1e4), -1)

            # 2) proper reward（w_sph=0.75 软目标匹配）+ GRPO 式组基线
            with torch.no_grad():
                r = rc.proper_reward(q, target.unsqueeze(0), batch["qtype"].to(device), mask,
                                     w_sph=0.75, w_rps=1.0)
                adv = r - r.mean(0, keepdim=True)
                adv = adv / (adv.std() + 1e-6)

            # 3) policy gradient + 1.0 权重 soft-CE 引导
            logp = -(((z - logits.unsqueeze(0)) ** 2) * mask).sum(-1) / (2 * sigma ** 2)
            loss_rl = -(adv * logp).mean()
            loss_ce = -(target * torch.log_softmax(logits.masked_fill(~mask, -1e4), -1)).sum(-1).mean()
            loss = (loss_rl + 1.0 * loss_ce) / GRAD_ACCUM

            scaler.scale(loss).backward()
            accum += 1
            if accum % GRAD_ACCUM == 0 or (b_idx + MICRO_BATCH) >= len(train_items):
                scaler.unscale_(optimizer)
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                scaler.step(optimizer)
                scaler.update()
                scheduler.step()
                optimizer.zero_grad(set_to_none=True)

            epoch_loss += loss.item() * GRAD_ACCUM
            n_batches += 1
            if n_batches % 20 == 0:
                print(f"  epoch {epoch + 1}/{EPOCHS} | step {n_batches} | loss {loss.item() * GRAD_ACCUM:.4f}"
                      f" | reward {r.mean().item():.3f} | lr {scheduler.get_last_lr()[0]:.2e}")

        avg = epoch_loss / max(1, n_batches)
        print(f"=== epoch {epoch + 1}/{EPOCHS} 完成 {time.time() - t0:.1f}s | avg loss {avg:.4f} ===")
        save_checkpoint(Path(args.out) / "checkpoint_latest", None, epoch + 1, avg)  # 滚动存防中断

    # 温度拟合（官方同款：LBFGS 逐 qtype；样本 <10 退回 1.2）
    model.eval()
    calib_preds = []
    with torch.no_grad():
        for c_idx in range(0, len(calib_items), 16):
            chunk = calib_items[c_idx:c_idx + 16]
            if not chunk:
                continue
            cb = collate(chunk)
            with torch.autocast("cuda", dtype=torch.float16, enabled=device.type == "cuda"):
                l_sub, _ = model(cb["input_ids"].to(device), cb["attention_mask"].to(device),
                                 cb["marker_pos"].to(device), cb["marker_mask"].to(device),
                                 cb["qtype"].to(device))
            l_np = l_sub.float().cpu().numpy()
            for ri, it in enumerate(chunk):
                kk = len(it["markers"])
                calib_preds.append((it["qtype"], l_np[ri, :kk], it["target"]))

    def fit_one_temp(sel):
        if len(sel) < 10:
            return 1.2
        kmax = max(len(z) for z, _ in sel)
        Z = torch.full((len(sel), kmax), -1e4)
        T = torch.zeros((len(sel), kmax))
        for i, (z, t) in enumerate(sel):
            Z[i, :len(z)] = torch.tensor(z)
            T[i, :len(t)] = torch.tensor(t, dtype=torch.float32)
        log_t = torch.zeros(1, requires_grad=True)
        opt = torch.optim.LBFGS([log_t], lr=0.1, max_iter=100)

        def closure():
            opt.zero_grad()
            loss = -(T * torch.log_softmax(Z / log_t.exp(), -1)).sum(-1).mean()
            loss.backward()
            return loss

        opt.step(closure)
        return float(torch.clamp(log_t.exp(), 0.1, 10.0).item())

    temps = [1.2, 1.2, 1.2]
    for qt in range(3):
        sel = [(z, t) for q_type, z, t in calib_preds if q_type == qt]
        if sel:
            temps[qt] = fit_one_temp(sel)
    print(f"[finetune_train] 拟合温度 (choice, score, noul) = {[round(t, 3) for t in temps]}"
          f"（calib {len(calib_preds)} 条；<10/类退回 1.2，R1 扩容后才有意义）")
    save_checkpoint(Path(args.out), temps, EPOCHS, avg)
    print(f"[finetune_train] 完成 → {args.out}（四件套+meta+vendor 两脚本；replay score --backend laya --model {args.out}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
