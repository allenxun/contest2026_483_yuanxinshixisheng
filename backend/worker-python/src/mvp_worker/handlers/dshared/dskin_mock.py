"""V3 三组评分 **mock** 数据（仅 dev/test 显式开关 `MVP_D_SKIN_V3_MOCK=true` 时使用）。

来源与性质（**data only**）：由用户提供的精简样本
``.mvp-d-runtime/v3-probe-input/``（``三项评分_精简返回示例.json`` /
``精简评分字段说明.md``）派生；它**不是**在线算法证据，也**不**代表真实模型输出。
生产环境由 ``assert_no_double_injection_in_production`` 拒绝本开关（fail-closed）。

语义（按字段说明，绑定）：
- 顶层恰三组 ``pores`` / ``spots`` / ``surface_gloss``，**all-or-none**；
- ``score`` 0..100 **越高越好**、可空（``null`` = 缺测，**绝不**用 0 代替）；
- ``severity`` 词表 ``未见明显/轻度/中度/较明显/显著``、可空；
- ``regions[]`` 元素 ``{region, name, score, severity}``；``region`` 为 V3 原生英文 ID，
  ``name`` 保持样本的**画面左右**措辞（**不做** F/L/R 或本人左右转换，**不补**四区）。

本 mock 刻意保留一个 ``score=null`` / ``severity=null`` 的区域（缺测）以驱动 null 透传，
并保留若干“画面左/右”名称以驱动逐字透传断言。
"""
from __future__ import annotations

from typing import Any

#: 冻结的三组键（顺序即发布与校验顺序）。
V3_SKIN_GROUP_KEYS: tuple[str, ...] = ("pores", "spots", "surface_gloss")

#: 冻结的 severity 词表（字段说明第 8 行；null=缺测）。
V3_SKIN_SEVERITIES: tuple[str, ...] = ("未见明显", "轻度", "中度", "较明显", "显著")

#: mock 标记：发布后位于 ``report_payload.model_info.model_version``，含子串 ``mock``。
V3_SKIN_MOCK_MODEL_VERSION = "skin-v3-mock@0"

#: 三组 mock 载荷（派生自样本，非算法证据；缺测区域为 null）。
V3_SKIN_MOCK_GROUPS: dict[str, Any] = {
    "pores": {
        "score": 57.0,
        "severity": "中度",
        "name": "毛孔",
        "regions": [
            {"region": "forehead", "name": "额部", "score": 57.0, "severity": "中度"},
            {"region": "left_nasal", "name": "画面左鼻旁", "score": 61.0, "severity": "轻度"},
            {"region": "right_nasal", "name": "画面右鼻旁", "score": 57.0, "severity": "中度"},
            {"region": "chin", "name": "下巴", "score": 67.0, "severity": "轻度"},
        ],
    },
    "spots": {
        "score": 42.0,
        "severity": "中度",
        "name": "可见色斑",
        "regions": [
            {"region": "forehead", "name": "额部", "score": 38.0, "severity": "较明显"},
            {"region": "left_zygoma", "name": "画面左颧部", "score": 69.0, "severity": "轻度"},
            # 缺测：null（不是 0）
            {"region": "right_cheek", "name": "画面右面颊", "score": None, "severity": None},
            {"region": "perioral", "name": "口周", "score": 100.0, "severity": "未见明显"},
        ],
    },
    "surface_gloss": {
        "score": 72.0,
        "severity": "轻度",
        "name": "表面油光",
        "regions": [
            {"region": "forehead", "name": "额部", "score": 72.0, "severity": "轻度"},
            {"region": "left_cheek", "name": "画面左面颊", "score": 100.0, "severity": "未见明显"},
            {"region": "right_cheek", "name": "画面右面颊", "score": 100.0, "severity": "未见明显"},
            {"region": "chin", "name": "下巴", "score": 100.0, "severity": "未见明显"},
        ],
    },
}


__all__ = [
    "V3_SKIN_GROUP_KEYS",
    "V3_SKIN_SEVERITIES",
    "V3_SKIN_MOCK_MODEL_VERSION",
    "V3_SKIN_MOCK_GROUPS",
]
