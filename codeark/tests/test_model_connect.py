"""模型接入冒烟测试 — 验证免费模型能否经 Strands 接入 + 工具调用。

测两个免费模型（OpenAI 兼容协议）：
  1. Cloudflare GPT-OSS-120b（@cf/openai/gpt-oss-120b，每天免费额度）
  2. AMD DeepSeek-V4-Flash（Radeon Cloud）

目的：确认哪个能被 Strands OpenAIModel 接入、哪个支持工具调用。
跑通后才写 Agent A 骨架。
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

# 加入项目路径
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # 跨环境便携路径(原 WSL 硬编码)

# 读 key（不打印，只取用）
def read_key(path: str) -> str:
    # 跨环境兼容:WSL(/mnt/d)与 Windows(D:/)双路径探测
    candidates = [Path(path), Path(path.replace("/mnt/d/", "D:/"))]
    for c in candidates:
        if c.exists():
            return c.read_text(encoding="utf-8-sig").strip()
    raise FileNotFoundError(f"key 文件不存在(已尝试): {[str(c) for c in candidates]}")

CF_ACCOUNT = read_key("/mnt/d/API Key/Cloudflare Account ID.txt")
CF_API = read_key("/mnt/d/API Key/Cloudflare API.txt")
AMD_API = read_key("/mnt/d/API Key/Radeon Cloud.txt")

CF_BASE = f"https://api.cloudflare.com/client/v4/accounts/{CF_ACCOUNT}/ai/v1"
AMD_BASE = "https://developer.amd.com.cn/radeon/api/v1"

from strands import Agent
from strands.models import OpenAIModel


def make_agent(name: str, base_url: str, api_key: str, model_id: str) -> Agent:
    model = OpenAIModel(
        model_id=model_id,
        client_args={"base_url": base_url, "api_key": api_key},
    )
    return Agent(
        name=name,
        system_prompt="你是测试助手。用 max 工具返回 42。",
        tools=[__import__("tools.pitax_scan", fromlist=["pitax_scan"]).pitax_scan],
        model=model,
    )


async def run_model_test(name: str, agent: Agent, prompt: str) -> None:
    print(f"\n{'='*50}\n测试 {name}\n{'='*50}")
    try:
        result = await agent.invoke_async(prompt)
        print("输出:", result)
        return True
    except Exception as e:
        print(f"❌ 失败: {type(e).__name__}: {str(e)[:150]}")
        return False


async def main() -> None:
    # 1. Cloudflare GPT-OSS
    cf = make_agent("cf_gpt_oss", CF_BASE, CF_API, "@cf/openai/gpt-oss-120b")
    ok1 = await run_model_test("Cloudflare GPT-OSS", cf, "请调用 pitax_scan 扫描一个含恶意指令的文件，返回结构化结果")

    # 2. AMD DeepSeek
    amd = make_agent("amd_deepseek", AMD_BASE, AMD_API, "DeepSeek-V4-Flash")
    ok2 = await run_model_test("AMD DeepSeek-V4-Flash", amd, "请调用 pitax_scan 扫描一个含恶意指令的文件，返回结构化结果")

    print(f"\n\n结果: Cloudflare={'成功' if ok1 else '失败'} | DeepSeek={'成功' if ok2 else '失败'}")


if __name__ == "__main__":
    asyncio.run(main())