"""strands SDK 兼容性回归 — 锁定会随 SDK 升级漂移的序列化行为。

背景（2026-10-05）：strands openai 适配层对消息历史中的 reasoningContent 块
打 warning 后自动剥离（strands/models/openai.py _format_regular_messages），
调用不受影响；该 warning 曾两度被误判为服务端拒收故障。本测试锁定剥离行为，
SDK 升级若改变行为即红（此时需重新评估 factory.py 的降噪配置是否仍成立）。
"""
import json

from strands.models import OpenAIModel


def test_format_regular_messages_strips_reasoning_content():
    messages = [
        {
            "role": "assistant",
            "content": [
                {"reasoningContent": {"text": "internal thinking"}},
                {"text": "visible answer"},
            ],
        },
        {"role": "user", "content": [{"text": "next question"}]},
    ]
    out = OpenAIModel._format_regular_messages(messages)
    serialized = json.dumps(out)
    # reasoning 块被剥离，思考文本不出现在发往 API 的载荷中
    assert "reasoningContent" not in serialized
    assert "internal thinking" not in serialized
    # 可见文本必须完整保留
    assert "visible answer" in serialized
    assert "next question" in serialized


def test_format_regular_messages_reasoning_only_assistant_message():
    """只有 reasoning 块的 assistant 消息剥离后 content 为空——不炸、不产出空 content 键污染。"""
    messages = [
        {
            "role": "assistant",
            "content": [{"reasoningContent": {"text": "only thinking"}}],
        },
        {"role": "user", "content": [{"text": "question"}]},
    ]
    out = OpenAIModel._format_regular_messages(messages)
    serialized = json.dumps(out)
    assert "reasoningContent" not in serialized
    assert "only thinking" not in serialized
    assert "question" in serialized
    assistant_msgs = [m for m in out if m.get("role") == "assistant"]
    for m in assistant_msgs:
        assert m.get("content") in (None, [],), "剥离后不应残留空 content 块"
