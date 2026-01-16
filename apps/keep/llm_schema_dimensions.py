"""
Keep 身体围度数据的结构化输出 schema。
"""

from apps.keep.body_metrics_schema import (
    build_metrics_event_schema_full,
    build_metrics_event_schema_limited,
)


def build_keep_dimensions_llm_schema(use_limited: bool = False) -> dict:
    return {
        "type": "object",
        "properties": {
            "body_measure_event": (
                build_metrics_event_schema_limited() if use_limited
                else build_metrics_event_schema_full()
            ),
        },
        "required": ["body_measure_event"],
    }


KEEP_DIMENSIONS_LLM_SCHEMA = build_keep_dimensions_llm_schema()
