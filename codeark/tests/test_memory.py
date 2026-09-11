"""记忆系统层测试（确定性，本地后端无需 AWS）。

验证：
  1. 本地后端记录/读取
  2. 记忆前馈 prompt 生成（误报标记优先证实，可靠标记正常引用）
  3. stats 统计
  4. DynamoDB 后端可实例化且无卡静默降级（不崩）
  5. get_memory_service 单例
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))  # 跨环境便携路径(原 WSL 硬编码)

from memory.memory import MemoryService, LocalBackend, DynamoDBBackend, get_memory_service


def test_local_record_and_read() -> None:
    tmp = tempfile.mktemp(suffix=".json")
    ms = MemoryService(LocalBackend(tmp))
    ms.record_finding("PIT-E-23", misdetected=True, note="误报过")
    ms.record_finding("PIT-T-51", misdetected=False)
    # 新实例能读到持久化的记忆
    ms2 = MemoryService(LocalBackend(tmp))
    store = ms2._load()
    assert "PIT-E-23" in store and "PIT-T-51" in store
    assert store["PIT-E-23"]["hit_count"] == 1
    assert store["PIT-E-23"]["misdetected"] == 1
    print("  ✅ 本地记录/读取")


def test_insight_prompt() -> None:
    tmp = tempfile.mktemp(suffix=".json")
    ms = MemoryService(LocalBackend(tmp))
    ms.record_finding("PIT-E-23", misdetected=True)
    ms.record_finding("PIT-T-51", misdetected=False)
    prompt = ms.build_insight_prompt()
    assert "【历史记忆约束】" in prompt
    assert "PIT-E-23" in prompt and "优先证实" in prompt, "误报模式应标记优先证实"
    assert "PIT-T-51" in prompt and "历史可靠" in prompt, "可靠模式应正常引用"
    # 空记忆 → 空提示
    assert MemoryService(LocalBackend(tempfile.mktemp())).build_insight_prompt() == ""
    print("  ✅ 记忆前馈 prompt")


def test_stats() -> None:
    tmp = tempfile.mktemp(suffix=".json")
    ms = MemoryService(LocalBackend(tmp))
    ms.record_finding("A", misdetected=True)
    ms.record_finding("A", misdetected=False)
    ms.record_finding("B", misdetected=False)
    s = ms.stats()
    assert s["total_patterns"] == 2
    assert s["total_hits"] == 3
    assert s["total_misdetections"] == 1
    print("  ✅ stats 统计")


def test_dynamodb_no_creds_safe() -> None:
    # 无 AWS 凭据时，DynamoDB 后端实例化 + 读写应静默降级不崩
    old = os.environ.pop("AWS_ACCESS_KEY_ID", None)
    db = DynamoDBBackend(table_name="test-mem", region="us-east-1")
    assert db.read_all() == {}  # 无凭据 → 返回空，不抛异常
    db.record("k", {"a": 1})  # 不抛异常
    if old is not None:
        os.environ["AWS_ACCESS_KEY_ID"] = old
    print("  ✅ DynamoDB 后端无卡静默降级（不崩）")


def test_get_service_singleton() -> None:
    s1 = get_memory_service()
    s2 = get_memory_service()
    assert s1 is s2, "单例应返回同一实例"
    print("  ✅ get_memory_service 单例")


if __name__ == "__main__":
    print("=== 记忆系统层测试 ===")
    test_local_record_and_read()
    test_insight_prompt()
    test_stats()
    test_dynamodb_no_creds_safe()
    test_get_service_singleton()
    print("\n全部通过 ✅")