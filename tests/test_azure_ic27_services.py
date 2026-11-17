"""IC27 合规底座脚本的回归锚（scripts/azure/）。

只锁"能机器验的算术与结构"，不联网：
  * 单价→调用量的换算（$1.25 目标下每项的计划调用数）
  * 合成素材的合法性（最小 PDF 的页数、PNG 签名、WAV 头与时长）
  * check_usage 的明细归类与门槛判定（含未达标退出码）
  * 两个 bash 脚本的语法（有 bash 才跑）
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
AZDIR = REPO_ROOT / "scripts" / "azure"


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, AZDIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def gen():
    return _load("generate_usage")


@pytest.fixture(scope="module")
def chk():
    return _load("check_usage")


# ------------------------------------------------------------- 换算与计划 ----
def test_plan_calls_at_target(gen):
    table = gen.plan(1.25)
    assert table["cs"]["calls"] == 3334          # $0.375/1K 文本记录
    assert table["language"]["calls"] == 1000    # 5 篇/请求 × 5,000 条
    assert table["docintel"]["calls"] == 209     # 10 页/请求 × 2,084 页
    assert table["vision"]["calls"] == 1250      # 1 页/请求
    assert table["speech"]["calls"] == 150       # 30 秒/请求 × 4,500 秒


def test_units_needed_never_zero(gen):
    assert gen.units_needed("cs", 0.0) == 1
    assert gen.calls_needed("cs", 0.0) == 1


def test_estimated_usd_meets_target(gen):
    for key, row in gen.plan(1.25).items():
        assert row["estimated_usd"] >= 1.25, key


# ------------------------------------------------------------- 合成素材 ----
def test_minimal_pdf_pages_and_trailer(gen):
    pdf = gen.minimal_pdf(3)
    assert pdf.startswith(b"%PDF-1.4")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert pdf.count(b"/Type /Page ") == 3
    assert b"/Count 3" in pdf
    # xref 偏移必须落在文件内，且 startxref 指向的字节是 "xref"
    tail = pdf.rsplit(b"startxref\n", 1)[1].split(b"\n", 1)[0]
    offset = int(tail)
    assert pdf[offset:offset + 4] == b"xref"


def test_png_signature_and_ihdr(gen):
    png = gen.blank_png(8, 4)
    assert png.startswith(b"\x89PNG\r\n\x1a\n")
    assert b"IHDR" in png and b"IEND" in png


def test_wav_header_and_duration(gen):
    wav = gen.speech_wav(2)
    assert wav[:4] == b"RIFF" and wav[8:12] == b"WAVE"
    rate = int.from_bytes(wav[24:28], "little")
    assert rate == 16000
    # 16-bit mono：帧数 = 采样率 × 秒数
    data = wav[44:]
    assert len(data) == 16000 * 2 * 2


# ------------------------------------------------------------- 归类与判定 ----
RES = [
    ("arca-cs-usage", "content_safety"),
    ("arca-ai-usage", "language"),
    ("arca-di-usage", "docintel"),
    ("arca-cv-usage", "vision"),
    ("arca-sp-usage", "speech"),
    ("arcaacric27", "acr"),
    ("arca-aca-logflood", "aca"),
    ("arca-law-ic27", "log_analytics"),
    ("arca-sb-ic27", "service_bus"),
    ("arca-eh-ic27", "event_hubs"),
]


def _rid(name: str) -> str:
    return f"/subscriptions/x/resourceGroups/rg-arcanum-ic27/providers/Microsoft.X/accounts/{name}"


def _payload(cost_map: dict[str, float], currency: str = "CNY") -> dict:
    return {"properties": {
        "columns": [{"name": "Cost"}, {"name": "ResourceId"}, {"name": "Currency"}],
        "rows": [[cost, _rid(name), currency] for name, cost in cost_map.items()],
    }}


def test_service_for_resource_mapping(chk):
    for name, expected in RES:
        assert chk.service_for_resource(_rid(name)) == (expected, chk.service_for_resource(_rid(name))[1])


def test_service_for_resource_unknown(chk):
    assert chk.service_for_resource(_rid("some-other-vm")) is None


def test_aggregate_by_resource_id(chk):
    payload = _payload({"arca-cs-usage": 8.0, "arca-acr-other": 0, "arca-ai-usage": 4.0})
    table = chk.aggregate(payload, 7.2)
    assert table["content_safety"]["cost"] == 8.0
    assert table["content_safety"]["cost_usd"] == round(8.0 / 7.2, 4)
    assert table["language"]["cost"] == 4.0
    assert table["content_safety"]["resources"] == {"arca-cs-usage": 8.0}


def test_aggregate_usd_currency_no_conversion(chk):
    table = chk.aggregate(_payload({"arca-cs-usage": 2.0}, currency="USD"), 7.2)
    assert table["content_safety"]["cost_usd"] == 2.0


def test_check_usage_all_reached_exit_zero(chk, tmp_path, capsys):
    path = tmp_path / "cost.json"
    path.write_text(json.dumps(_payload({name: 8.0 for name, _ in RES})), encoding="utf-8")
    assert chk.main(["--input", str(path), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["all_reached"] is True and payload["reached"] == 10


def test_check_usage_short_fails(chk, tmp_path, capsys):
    path = tmp_path / "cost.json"
    path.write_text(json.dumps(_payload({"arca-cs-usage": 1.0})), encoding="utf-8")
    assert chk.main(["--input", str(path), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["reached"] == 0


def test_az_command_wraps_cmd_on_windows(chk):
    assert chk.az_command("C:/x/az.cmd")[:2] == ["cmd", "/c"]
    assert chk.az_command("/usr/bin/az") == ["/usr/bin/az"]
    assert chk.az_command("C:/nonexistent/az.exe") == ["C:/nonexistent/az.exe"]


def test_env_file_parser_ignores_comments(gen, tmp_path):
    env = tmp_path / "a.env"
    env.write_text(
        "# comment\nARCA_IC27_CS_ENDPOINT=https://x.example\n\nARCA_IC27_CS_KEY=abc=def\n",
        encoding="utf-8",
    )
    data = gen.read_env_file(env)
    assert data["ARCA_IC27_CS_ENDPOINT"] == "https://x.example"
    assert data["ARCA_IC27_CS_KEY"] == "abc=def"


def test_all_ai_dry_run_exit_zero(gen, tmp_path, capsys):
    env = tmp_path / "e.env"
    env.write_text(
        "\n".join(
            [
                "ARCA_IC27_CS_ENDPOINT=https://a.example/",
                "ARCA_IC27_CS_KEY=f",
                "ARCA_IC27_LANGUAGE_ENDPOINT=https://b.example/",
                "ARCA_IC27_LANGUAGE_KEY=f",
                "ARCA_IC27_DOCINTEL_ENDPOINT=https://c.example/",
                "ARCA_IC27_DOCINTEL_KEY=f",
                "ARCA_IC27_VISION_ENDPOINT=https://d.example/",
                "ARCA_IC27_VISION_KEY=f",
                "ARCA_IC27_SPEECH_REGION=uaenorth",
                "ARCA_IC27_SPEECH_KEY=f",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    # 0.5 秒级：dry-run 不发请求；返回 0 表示五项计划齐全
    assert gen.main(["all-ai", "--env-file", str(env), "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert "speech" in out and "calls=150" in out


# ------------------------------------------------------------- 脚本语法 ----
def _find_bash() -> str | None:
    """找 MSYS/Git Bash；Windows 的 System32\\bash.exe 是 WSL 桩（看不到 D: 路径）。"""
    found = shutil.which("bash")
    if found and "system32" not in found.lower():
        return found
    for candidate in (
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ):
        if Path(candidate).exists():
            return candidate
    return None


BASH = _find_bash()


@pytest.mark.skipif(BASH is None, reason="需要 Git Bash / MSYS bash（WSL 桩不算）")
@pytest.mark.parametrize("script", ["provision_10_services.sh", "cleanup_10_services.sh"])
def test_shell_scripts_syntax(script):
    done = subprocess.run(
        [BASH, "-n", (AZDIR / script).as_posix()],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    assert done.returncode == 0, done.stderr


@pytest.mark.skipif(BASH is None, reason="需要 Git Bash / MSYS bash（WSL 桩不算）")
def test_provision_dry_run_exits_zero(tmp_path):
    done = subprocess.run(
        [
            BASH, (AZDIR / "provision_10_services.sh").as_posix(),
            "--dry-run", "--env-out", (tmp_path / "e.env").as_posix(),
        ],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=tmp_path,
    )
    assert done.returncode == 0, done.stderr
    assert "dry-run" in done.stderr
