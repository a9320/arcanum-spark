"""IC27 合规用量生成器：让 5 项 AI 服务各自产生 >= $1.00 计费用量。

为什么存在：Imagine Cup 2027 正式规则 §7 要求提交时账户上「至少 10 项 Azure 服务、
每项 >= $1.00 用量」。免费层（F0 / Free）计量为 $0.00，不满足判据；本脚本按
Azure Retail Prices API 实测单价（快照见同目录 prices-20261117.json）把「$1.00」
换算成精确调用量，只做最小必要跑量。

配套脚本：
  provision_10_services.sh   建资源（幂等、支持 --dry-run）
  check_usage.py             用 az consumption 逐项核对是否已过 $1.00
  cleanup_10_services.sh     达标后按名单删除（不删整组）

用法：
  python scripts/azure/generate_usage.py plan
      只打印每项服务的换算与计划调用量（零联网、零凭据）

  python scripts/azure/generate_usage.py all-ai --env-file ~/azure-ic27.env
      按 provision 脚本落盘的环境文件一次跑完 5 项 AI 服务

  python scripts/azure/generate_usage.py cs --endpoint URL --key KEY
      单项跑量；其余服务同构（language / docintel / vision / speech）

  python scripts/azure/generate_usage.py all-ai --env-file ~/azure-ic27.env --dry-run
      打印将从环境文件读到哪些项（不打印密钥内容）

纪律：
  * 不打印密钥；异常信息只带主机名与状态码。
  * 只用良性文本/空白图像/纯音音频做跑量，不投攻击语料（避免污染扫描器的
    自扫闸门与任何误报统计）。
  * 默认目标 $1.25（比规则门槛留 25% 余量，吸收计量取整与四舍五入）。
  * 退出码：0=全部达到计划量；1=有失败；2=参数/配置错误。
"""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as futures
import json
import math
import struct
import sys
import time
import urllib.error
import urllib.request
import wave
import zlib
from pathlib import Path

# --- 单价快照（2026-11-17 取自 https://prices.azure.com/api/retail/prices） ----
# 只列本脚本用到的计量项；区域差异见 prices-20261117.json 与选型文档。
PRICES: dict[str, dict[str, object]] = {
    "cs": {
        "service": "Azure AI Content Safety",
        "meter": "Standard Text Records",
        "region": "uaenorth",
        "unit_usd": 0.000375,  # $0.375 / 1K 文本记录
        "unit": "record",
    },
    "language": {
        "service": "Azure AI Language",
        "meter": "Standard Text Records",
        "region": "eastasia",  # UAENorth 无该付费计量（见选型文档 §3）
        "unit_usd": 0.00025,  # $0.25 / 1K 文本记录
        "unit": "record",
    },
    "docintel": {
        "service": "Azure AI Document Intelligence",
        "meter": "S0 Read Pages",
        "region": "uaenorth",
        "unit_usd": 0.0006,  # $0.60 / 1K 页
        "unit": "page",
    },
    "vision": {
        "service": "Azure AI Vision",
        "meter": "OCR glbl Pages",
        "region": "uaenorth",
        "unit_usd": 0.001,  # $1.00 / 1K 页
        "unit": "page",
    },
    "speech": {
        "service": "Azure AI Speech",
        "meter": "S1 Speech To Text",
        "region": "uaenorth",
        "unit_usd": 1.0 / 3600.0,  # $1.00 / 音频小时 → 按秒换算
        "unit": "second",
    },
}

# 单项请求承载的计费单位数（多单位/请求可显著缩短跑量时间）。
UNITS_PER_CALL: dict[str, int] = {
    "cs": 1,          # text:analyze 一次一条文本记录
    "language": 5,    # analyze-text 一次最多 5 篇文档（每篇 1 条记录）
    "docintel": 10,   # 一份 10 页 PDF 一次分析 = 10 页
    "vision": 1,      # v3.2 ocr 一次一张图 = 1 页
    "speech": 30,     # 30 秒 WAV 一次 = 30 秒音频
}

DEFAULT_TARGET_USD = 1.25
MAX_WORKERS = 8
PROGRESS_EVERY = 200


# ---------------------------------------------------------------- 计划换算 ----
def units_needed(service: str, target_usd: float) -> int:
    """达到 target_usd 所需的计费单位数（向上取整）。"""
    unit_usd = float(PRICES[service]["unit_usd"])  # type: ignore[arg-type]
    return max(1, math.ceil(target_usd / unit_usd - 1e-12))


def calls_needed(service: str, target_usd: float) -> int:
    units = units_needed(service, target_usd)
    per = UNITS_PER_CALL[service]
    return max(1, math.ceil(units / per))


def plan(target_usd: float) -> dict[str, dict[str, object]]:
    out: dict[str, dict[str, object]] = {}
    for key, meta in PRICES.items():
        units = units_needed(key, target_usd)
        calls = calls_needed(key, target_usd)
        out[key] = {
            "service": meta["service"],
            "meter": meta["meter"],
            "region": meta["region"],
            "unit_usd": meta["unit_usd"],
            "units_needed": units,
            "units_per_call": UNITS_PER_CALL[key],
            "calls": calls,
            "estimated_usd": round(units * float(meta["unit_usd"]), 4),  # type: ignore[arg-type]
        }
    return out


# ------------------------------------------------------------------ HTTP ----
class HttpResult:
    __slots__ = ("status", "body", "error", "headers")

    def __init__(
        self,
        status: int,
        body: bytes,
        error: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status = status
        self.body = body
        self.error = error
        self.headers = {k.lower(): v for k, v in (headers or {}).items()}

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


def _http(
    method: str,
    url: str,
    headers: dict[str, str],
    data: bytes | None = None,
    timeout: float = 60.0,
    retries: int = 3,
) -> HttpResult:
    last = HttpResult(0, b"", "not-attempted")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return HttpResult(resp.status, resp.read(), headers=dict(resp.headers))
        except urllib.error.HTTPError as exc:  # 4xx/5xx 也读体，便于定位
            body = b""
            try:
                body = exc.read()
            except Exception:  # pragma: no cover - 体读取失败不影响判定
                pass
            last = HttpResult(exc.code, body, f"HTTP {exc.code}", headers=dict(exc.headers or {}))
            if exc.code in (408, 429) or 500 <= exc.code < 600:
                time.sleep(1.5 * (attempt + 1))
                continue
            return last
        except Exception as exc:  # 网络层错误（DNS/TLS/超时）
            last = HttpResult(0, b"", f"{type(exc).__name__}: {exc}")
            time.sleep(1.0 * (attempt + 1))
    return last


def _json_body(res: HttpResult) -> dict:
    try:
        return json.loads(res.body.decode("utf-8", "replace"))
    except Exception:
        return {}


def _err_brief(res: HttpResult) -> str:
    if res.body:
        try:
            return res.body.decode("utf-8", "replace")[:180]
        except Exception:  # pragma: no cover
            return res.error or "unknown"
    return res.error or "unknown"


# ------------------------------------------------------- 合成素材（stdlib） ----
def minimal_pdf(pages: int, text: str = "arcanum ic27 compliance page") -> bytes:
    """生成 pages 页的最小合法 PDF（每页一行文本），供 Document Intelligence 读页计费。"""
    if pages < 1:
        raise ValueError("pages must be >= 1")
    objs: list[bytes] = []
    kids = " ".join(f"{3 + 2 * i} 0 R" for i in range(pages))
    objs.append(f"<< /Type /Catalog /Pages 2 0 R >>".encode())  # 1
    objs.append(f"<< /Type /Pages /Kids [{kids}] /Count {pages} >>".encode())  # 2
    font_num = 3 + 2 * pages
    for i in range(pages):
        content_num = 4 + 2 * i
        objs.append(
            (
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
                f"/Resources << /Font << /F1 {font_num} 0 R >> >> "
                f"/Contents {content_num} 0 R >>"
            ).encode()
        )
        stream = f"BT /F1 12 Tf 72 720 Td ({text} {i + 1}) Tj ET".encode()
        objs.append(b"<< /Length %d >>\nstream\n%s\nendstream" % (len(stream), stream))
    objs.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % number + body + b"\nendobj\n"
    xref_at = len(out)
    out += b"xref\n0 %d\n" % (len(objs) + 1)
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += b"%010d 00000 n \n" % off
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (
        len(objs) + 1,
        xref_at,
    )
    return bytes(out)


def blank_png(width: int = 320, height: int = 120) -> bytes:
    """生成纯白 PNG（无第三方依赖），供 OCR 计页。"""
    raw = bytearray()
    for _ in range(height):
        raw.append(0)  # filter type 0
        raw.extend(b"\xff\xff\xff" * width)

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


def speech_wav(seconds: int = 30, rate: int = 16000) -> bytes:
    """生成 seconds 秒 16k/mono/16bit 纯音 WAV（Speech STT 按音频时长计费）。"""
    frames = bytearray()
    total = rate * seconds
    for i in range(total):
        value = int(2000 * math.sin(2 * math.pi * 440 * i / rate))
        frames += struct.pack("<h", value)
    buf = _BytesBuffer()
    with wave.open(buf, "wb") as handle:  # type: ignore[arg-type]
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(bytes(frames))
    return buf.getvalue()


class _BytesBuffer:
    """wave 模块需要一个类文件对象；这里给最小实现（write/tell/seek/flush）。"""

    def __init__(self) -> None:
        self._buf = bytearray()
        self._pos = 0

    def write(self, data: bytes) -> int:
        end = self._pos + len(data)
        if end > len(self._buf):
            self._buf.extend(b"\x00" * (end - len(self._buf)))
        self._buf[self._pos:end] = data
        self._pos = end
        return len(data)

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        else:
            self._pos = len(self._buf) + offset
        return self._pos

    def flush(self) -> None:
        return None

    def getvalue(self) -> bytes:
        return bytes(self._buf)


# --------------------------------------------------------- 各服务跑量实现 ----
CS_TEXT = (
    "The release notes describe a bug fix in the parser and a documentation update. "
    "No user data is included in this sample."
)
LANGUAGE_DOC = (
    "Contact support at {mail} for account questions. The office is in {city} and "
    "the ticket reference is {ref}."
)


def run_cs(endpoint: str, key: str, target_usd: float, workers: int, dry: bool) -> dict:
    total = calls_needed("cs", target_usd)
    if dry:
        return _dry("cs", total, target_usd)
    url = endpoint.rstrip("/") + "/contentsafety/text:analyze?api-version=2024-09-01"
    headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/json"}
    payload = json.dumps({"text": CS_TEXT}).encode()

    def one(_: int) -> bool:
        return _http("POST", url, headers, payload).ok

    return _drive("cs", total, one, workers)


def run_language(endpoint: str, key: str, target_usd: float, workers: int, dry: bool) -> dict:
    total = calls_needed("language", target_usd)
    if dry:
        return _dry("language", total, target_usd)
    url = endpoint.rstrip("/") + "/language/:analyze-text?api-version=2024-11-01"
    headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/json"}

    def one(n: int) -> bool:
        docs = [
            {
                "id": str(i),
                "text": LANGUAGE_DOC.format(
                    mail=f"user{i}@example.com", city="North University", ref=f"T-{n}-{i}"
                ),
            }
            for i in range(UNITS_PER_CALL["language"])
        ]
        body = json.dumps(
            {"kind": "PiiEntityRecognition", "analysisInput": {"documents": docs}}
        ).encode()
        return _http("POST", url, headers, body).ok

    return _drive("language", total, one, workers)


def run_docintel(endpoint: str, key: str, target_usd: float, workers: int, dry: bool) -> dict:
    total = calls_needed("docintel", target_usd)
    if dry:
        return _dry("docintel", total, target_usd)
    base = endpoint.rstrip("/")
    pdf = minimal_pdf(UNITS_PER_CALL["docintel"])
    headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/pdf"}
    # 2024-11-30 是新版路径；旧资源只有 formrecognizer 前缀，逐个试一次并记住
    candidates = [
        base + "/documentintelligence/documentModels/prebuilt-read:analyze?api-version=2024-11-30",
        base + "/formrecognizer/documentModels/prebuilt-read:analyze?api-version=2024-11-30",
        base + "/formrecognizer/documentModels/prebuilt-read:analyze?api-version=2023-07-31",
    ]
    state = {"url": ""}

    def submit(n: int) -> bool:
        urls = [state["url"]] if state["url"] else candidates
        for url in urls:
            res = _http("POST", url, headers, pdf)
            if res.status == 202:
                state["url"] = url
                op = _header_value(res, "operation-location")
                if not op:
                    return False
                return _poll_docintel(op, key)
            if res.status == 404:  # 该前缀不存在，换下一个
                continue
            return False
        return False

    return _drive("docintel", total, submit, workers)


def _header_value(res: HttpResult, name: str) -> str:
    return res.headers.get(name.lower(), "")


def _poll_docintel(operation_url: str, key: str, timeout_s: float = 180.0) -> bool:
    headers = {"Ocp-Apim-Subscription-Key": key}
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        res = _http("GET", operation_url, headers)
        if not res.ok:
            time.sleep(1.0)
            continue
        status = str(_json_body(res).get("status", "")).lower()
        if status == "succeeded":
            return True
        if status == "failed":
            return False
        time.sleep(1.0)
    return False


def run_vision(endpoint: str, key: str, target_usd: float, workers: int, dry: bool) -> dict:
    total = calls_needed("vision", target_usd)
    if dry:
        return _dry("vision", total, target_usd)
    url = (
        endpoint.rstrip("/")
        + "/vision/v3.2/ocr?language=en&detectOrientation=true&model-version=latest"
    )
    headers = {"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/octet-stream"}
    png = blank_png()

    def one(_: int) -> bool:
        return _http("POST", url, headers, png).ok

    return _drive("vision", total, one, workers)


def run_speech(region: str, key: str, target_usd: float, workers: int, dry: bool) -> dict:
    total = calls_needed("speech", target_usd)
    if dry:
        return _dry("speech", total, target_usd)
    url = (
        f"https://{region}.stt.speech.microsoft.com/speech/recognition/"
        "conversation/cognitiveservices/v1?language=en-US"
    )
    headers = {
        "Ocp-Apim-Subscription-Key": key,
        "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
        "Accept": "application/json",
    }
    wav = speech_wav(UNITS_PER_CALL["speech"])

    def one(_: int) -> bool:
        return _http("POST", url, headers, wav, timeout=120.0).ok

    return _drive("speech", total, one, workers)


# ------------------------------------------------------------- 驱动/汇报 ----
def _dry(service: str, total: int, target_usd: float) -> dict:
    meta = PRICES[service]
    return {
        "service": service,
        "meter": meta["meter"],
        "mode": "dry-run",
        "calls": total,
        "units": total * UNITS_PER_CALL[service],
        "target_usd": target_usd,
    }


def _drive(service: str, total: int, one, workers: int) -> dict:
    done = 0
    failed = 0
    t0 = time.perf_counter()
    with futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for ok in pool.map(one, range(total)):
            done += 1
            if not ok:
                failed += 1
            if done % PROGRESS_EVERY == 0:
                rate = done / max(time.perf_counter() - t0, 1e-9)
                print(
                    f"  [{service}] {done}/{total} calls, failed={failed}, {rate:.1f}/s",
                    file=sys.stderr,
                )
    elapsed = round(time.perf_counter() - t0, 1)
    units = (done - failed) * UNITS_PER_CALL[service]
    return {
        "service": service,
        "meter": PRICES[service]["meter"],
        "calls": done,
        "failed": failed,
        "units": units,
        "estimated_usd": round(units * float(PRICES[service]["unit_usd"]), 4),  # type: ignore[arg-type]
        "elapsed_s": elapsed,
        "ok": failed == 0,
    }


def _require(value: str | None, name: str) -> str:
    if not value:
        raise SystemExit(f"缺少参数 {name}（也可用 --env-file 提供）")
    return value


def read_env_file(path: Path) -> dict[str, str]:
    """读取 provision 脚本落盘的 KEY=VALUE 文件；不打印值。"""
    data: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        data[key.strip()] = value.strip()
    return data


def _from_env(env: dict[str, str], name: str) -> str:
    return env.get(f"ARCA_IC27_{name}", "")


def _common_options() -> argparse.ArgumentParser:
    """公共选项挂在每个子命令上（这样 `cs --endpoint ... --dry-run` 顺序随意）。"""
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--env-file", type=Path, help="provision 脚本落盘的 KEY=VALUE 文件")
    common.add_argument("--target-usd", type=float, default=DEFAULT_TARGET_USD)
    common.add_argument("--workers", type=int, default=MAX_WORKERS)
    common.add_argument("--dry-run", action="store_true", help="只打印计划，不发请求")
    common.add_argument("--json", action="store_true", help="只输出 JSON 汇总")
    return common


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        description="IC27 合规用量生成器：按实测单价把每项服务的 $1.00 换算成调用量"
    )
    sub = ap.add_subparsers(dest="cmd", required=True)
    common = _common_options()

    sub.add_parser("plan", parents=[common], help="打印 5 项 AI 服务的换算与计划调用量")

    for name in ("cs", "language", "docintel", "vision", "speech"):
        p = sub.add_parser(name, parents=[common], help=f"跑 {name} 的用量")
        p.add_argument("--endpoint")
        p.add_argument("--key")
        p.add_argument("--region", help="speech 用（默认取 env 的 SPEECH_REGION）")

    sub.add_parser("all-ai", parents=[common], help="一次跑完 5 项 AI 服务（需要 --env-file）")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    env = read_env_file(args.env_file) if args.env_file and args.env_file.exists() else {}

    if args.cmd == "plan":
        table = plan(args.target_usd)
        print(json.dumps(table, ensure_ascii=False, indent=2))
        return 0

    if args.cmd == "all-ai":
        if not args.env_file or not env:
            print("all-ai 需要 --env-file（先跑 provision_10_services.sh）", file=sys.stderr)
            return 2
        results = []
        runners = [
            ("cs", lambda: run_cs(_from_env(env, "CS_ENDPOINT"), _from_env(env, "CS_KEY"),
                                  args.target_usd, args.workers, args.dry_run)),
            ("language", lambda: run_language(_from_env(env, "LANGUAGE_ENDPOINT"),
                                              _from_env(env, "LANGUAGE_KEY"),
                                              args.target_usd, args.workers, args.dry_run)),
            ("docintel", lambda: run_docintel(_from_env(env, "DOCINTEL_ENDPOINT"),
                                              _from_env(env, "DOCINTEL_KEY"),
                                              args.target_usd, args.workers, args.dry_run)),
            ("vision", lambda: run_vision(_from_env(env, "VISION_ENDPOINT"),
                                          _from_env(env, "VISION_KEY"),
                                          args.target_usd, args.workers, args.dry_run)),
            ("speech", lambda: run_speech(_from_env(env, "SPEECH_REGION") or "uaenorth",
                                          _from_env(env, "SPEECH_KEY"),
                                          args.target_usd, args.workers, args.dry_run)),
        ]
        for name, fn in runners:
            try:
                results.append(fn())
            except SystemExit as exc:  # 缺 env 的一项不拖垮其余
                print(f"  [{name}] skipped: {exc}", file=sys.stderr)
                results.append({"service": name, "ok": False, "error": str(exc)})
        return _report(results, args.json)

    endpoint, key = args.endpoint, args.key
    if env:
        prefix = {"cs": "CS", "language": "LANGUAGE", "docintel": "DOCINTEL",
                  "vision": "VISION", "speech": "SPEECH"}[args.cmd]
        endpoint = endpoint or _from_env(env, f"{prefix}_ENDPOINT")
        key = key or _from_env(env, f"{prefix}_KEY")

    if not args.dry_run:
        _require(endpoint, "--endpoint")
        _require(key, "--key")

    if args.cmd == "cs":
        result = run_cs(endpoint or "", key or "", args.target_usd, args.workers, args.dry_run)
    elif args.cmd == "language":
        result = run_language(endpoint or "", key or "", args.target_usd, args.workers, args.dry_run)
    elif args.cmd == "docintel":
        result = run_docintel(endpoint or "", key or "", args.target_usd, args.workers, args.dry_run)
    elif args.cmd == "vision":
        result = run_vision(endpoint or "", key or "", args.target_usd, args.workers, args.dry_run)
    elif args.cmd == "speech":
        region = args.region or _from_env(env, "SPEECH_REGION") or "uaenorth"
        result = run_speech(region, key or "", args.target_usd, args.workers, args.dry_run)
    else:  # pragma: no cover - argparse 已限制
        print(f"unknown command {args.cmd}", file=sys.stderr)
        return 2
    return _report([result], args.json)


def _report(results: list[dict], as_json: bool) -> int:
    if as_json:
        print(json.dumps({"results": results}, ensure_ascii=False))
    else:
        for item in results:
            if item.get("mode") == "dry-run":
                print(f"{item['service']:<10} dry-run calls={item['calls']} units={item['units']}")
            elif item.get("ok"):
                print(
                    f"{item['service']:<10} OK calls={item['calls']} "
                    f"units={item['units']} est=${item['estimated_usd']}"
                )
            else:
                print(f"{item['service']:<10} FAILED {item.get('error', '')}")
    return 0 if all(item.get("ok", item.get("mode") == "dry-run") for item in results) else 1


if __name__ == "__main__":
    sys.exit(main())
