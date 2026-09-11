"""记忆系统层 — 可插拔后端（本地 + DynamoDB）。

蓝图 §5.7 记忆系统前馈（GLM 方法5）：
- 记忆从"过滤器"改为"主动注入约束"
- 历史误报模式注入假设生成器 prompt，避免重复犯错
- 正确模式优先考虑，提升命中率

设计（有卡无缝衔接）：
- 抽象 `MemoryBackend`：read_insights / record_finding / record_misdetection
- `LocalBackend`：现在无卡即可用（memory.json 持久化到本地）
- `DynamoDBBackend`：预写好，卡批后只需填 region/table 名即可用（boto3 延迟导入）
- 上层逻辑（MemoryService）与后端解耦，切换后端不碰业务代码
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

__all__ = [
    "MemoryService",
    "MemoryBackend",
    "LocalBackend",
    "DynamoDBBackend",
    "get_memory_service",
]

# 误报/确认记录结构
# { "pattern_key": { "hit_count", "last_seen", "misdetected", "notes" } }


class MemoryBackend:
    """记忆后端抽象接口。"""

    def read_all(self) -> dict[str, Any]:
        raise NotImplementedError

    def record(self, key: str, data: dict[str, Any]) -> None:
        raise NotImplementedError


class LocalBackend(MemoryBackend):
    """本地 JSON 持久化（无卡阶段默认）。"""

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path or os.environ.get("CODERISK_MEMORY", "memory.json"))
        self._cache: dict[str, Any] | None = None

    def read_all(self) -> dict[str, Any]:
        if self._cache is not None:
            return self._cache
        if self.path.exists():
            try:
                self._cache = json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                self._cache = {}
        else:
            self._cache = {}
        return self._cache

    def record(self, key: str, data: dict[str, Any]) -> None:
        store = self.read_all()
        store[key] = data
        self._cache = store
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")


class DynamoDBBackend(MemoryBackend):
    """DynamoDB 后端（预写，卡批后启用）。"""

    def __init__(
        self,
        table_name: str | None = None,
        region: str | None = None,
        partition_key: str = "pattern_key",
    ) -> None:
        self.table_name = table_name or os.environ.get("CODERISK_MEMORY_TABLE", "coderisk-memory")
        self.region = region or os.environ.get("AWS_REGION", "us-east-1")
        self.partition_key = partition_key
        self._client = None

    def _get_client(self):
        """延迟导入 boto3（无卡阶段不加载，卡批后自动可用）。"""
        if self._client is None:
            import boto3  # 仅在有 AWS 凭据时导入
            self._client = boto3.client("dynamodb", region_name=self.region)
        return self._client

    def read_all(self) -> dict[str, Any]:
        try:
            client = self._get_client()
            resp = client.scan(TableName=self.table_name)
            out = {}
            for item in resp.get("Items", []):
                key = item.get(self.partition_key, {}).get("S", "")
                payload = item.get("data", {}).get("M", {})
                # 简化：把 DynamoDB 类型映射回 dict
                out[key] = {k: list(v.values())[0] for k, v in payload.items()}
            return out
        except Exception:
            return {}

    def record(self, key: str, data: dict[str, Any]) -> None:
        try:
            client = self._get_client()
            # 用 marshal 序列化
            from boto3.dynamodb.types import TypeSerializer
            serializer = TypeSerializer()
            client.put_item(
                TableName=self.table_name,
                Item={
                    self.partition_key: {"S": key},
                    "data": serializer.serialize(data),
                    "updated_at": {"N": str(int(time.time()))},
                },
            )
        except Exception:
            pass  # 卡未到位/无权限时静默降级，不阻塞主流程


class MemoryService:
    """记忆服务 — 统一接口，后端可插拔。

    核心能力（蓝图 §5.7）：
    - 记录确认/误报，形成模式记忆
    - 为假设生成器注入历史约束，避免重复误报
    """

    def __init__(self, backend: MemoryBackend | None = None) -> None:
        self.backend = backend or LocalBackend()
        self._insights_cache: dict[str, Any] | None = None

    def _load(self) -> dict[str, Any]:
        if self._insights_cache is None:
            self._insights_cache = self.backend.read_all()
        return self._insights_cache

    def record_finding(self, pattern_key: str, misdetected: bool = False, note: str = "") -> None:
        """记录一次命中/误报，更新模式记忆。"""
        store = self._load()
        entry = store.get(pattern_key, {"hit_count": 0, "misdetected": 0, "notes": []})
        entry["hit_count"] = entry.get("hit_count", 0) + 1
        if misdetected:
            entry["misdetected"] = entry.get("misdetected", 0) + 1
        if note:
            entry["notes"] = entry.get("notes", []) + [note]
        entry["last_seen"] = time.strftime("%Y-%m-%d %H:%M")
        self.backend.record(pattern_key, entry)

    def build_insight_prompt(self) -> str:
        """生成记忆前馈约束文本，注入假设生成器 prompt（蓝图 §5.7）。"""
        store = self._load()
        if not store:
            return ""
        lines = ["【历史记忆约束】"]
        for key, entry in store.items():
            hits = entry.get("hit_count", 0)
            mis = entry.get("misdetected", 0)
            if mis > 0:
                lines.append(f"- 模式 {key}: 命中 {hits} 次，其中误报 {mis} 次 → 优先证实再下结论")
            else:
                lines.append(f"- 模式 {key}: 命中 {hits} 次（历史可靠）→ 可正常引用")
        return "\n".join(lines)

    def stats(self) -> dict[str, Any]:
        store = self._load()
        return {
            "total_patterns": len(store),
            "total_hits": sum(e.get("hit_count", 0) for e in store.values()),
            "total_misdetections": sum(e.get("misdetected", 0) for e in store.values()),
        }


# ── 单例获取 ──
_default_service: MemoryService | None = None


def get_memory_service() -> MemoryService:
    """获取全局记忆服务（默认本地后端，卡批后切 DynamoDB）。"""
    global _default_service
    if _default_service is None:
        use_dynamodb = os.environ.get("CODERISK_MEMORY_BACKEND", "local") == "dynamodb"
        backend = DynamoDBBackend() if use_dynamodb else LocalBackend()
        _default_service = MemoryService(backend)
    return _default_service