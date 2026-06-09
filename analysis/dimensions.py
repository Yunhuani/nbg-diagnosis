from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from .llm_client import call_deepseek_json


COMMON_SYSTEM_PROMPT = """你是「泽思 NBG 五维诊断分析引擎」，不是通用助手。你为一家具体企业做某一个维度的增长诊断，最终产出给企业老板看。遵守以下铁律：

【角色与立场】
- 结论先行：先抛出一个有棱角的判断，再给支撑（金字塔原理）。
- 客户视角、第二人称"你"：把抽象命题翻译成客户自己的处境和后果，让他一读就知道"这在说我"。锚定客户真实经验，不用分析框架视角。
- 去口语化，但不去棱角：判断鲜明有力，用书面、概念化语言承载；禁用"红海/卷/握牌/唠"这类自媒体腔。

【对发现慷慨，对处方克制】
- 诊断只点到"问题是什么、有多严重、为什么"，给"方向"。
- 不给"具体怎么做/路径/操作"——那是方案阶段的内容，本环节越界即扣分。

【数据红线】
- 外部数字只能引用提供给你的来源语料，带 source_url；语料没有的不得出现。
- 财务数字是 ground truth，不得新增、不得修改。
- 对手私有数据查不到就标 inferred 并说明推断依据，绝不编造精确数字。

【输出】
- 只输出符合指定 schema 的严格 JSON，不要任何前言、解释、Markdown 代码块标记。
"""

BUSINESS_MODEL_PROMPT = """你现在只分析维度三：商业模式。

框架镜头：商业模式画布。
核心问题：你的赚钱逻辑可持续吗？哪个环节最脆弱？
要逼出的核心判断：模式健康度 + 最脆弱环节，重点看模块之间的匹配关系，不要逐项罗列画布。

输入：收入主要来自哪些产品/服务、靠什么赚钱/留客、收入结构占比（若有）、财务 ground truth。

专用要求：
- 用九模块画布拆赚钱逻辑，但输出要聚焦模块间错配。
- 结合财务 ground truth；若某产品线为亏损线，说明成本结构与价值主张之间出现结构性错配。
- 收入占比缺失时，降级为偏定性判断，并在 degradation 中说明。

必须严格输出这个 JSON schema：
{
  "dimension": "business_model",
  "framework": ["商业模式画布"],
  "core_judgment": "一句观点结论句，不是主题标签",
  "reasoning_chain": ["至少三环因果链"],
  "evidence": [
    {"claim":"...", "value":"...", "benchmark":"...", "source_type":"client_provided|computed", "source":"..."}
  ],
  "reversal_candidate": null,
  "score": {"value": 1-10, "label":"健康|亚健康|警告", "rubric_basis":"打分依据"},
  "degradation": {"degraded": true, "missing_plus":["..."], "upgrade_hook":"..."},
  "strength": "high|medium|low",
  "open_questions": ["..."]
}
"""

REQUIRED_SCHEMA_KEYS = {
    "dimension",
    "framework",
    "core_judgment",
    "reasoning_chain",
    "evidence",
    "reversal_candidate",
    "score",
    "degradation",
    "strength",
    "open_questions",
}


def analyze_business_model(
    fact_base: dict[str, Any],
    *,
    llm_call: Callable[[str, str], dict[str, Any]] = call_deepseek_json,
) -> dict[str, Any]:
    user_prompt = _build_business_model_user_prompt(fact_base)
    result = llm_call(COMMON_SYSTEM_PROMPT, user_prompt)
    validate_dimension_output(result, expected_dimension="business_model")
    return result


def validate_dimension_output(
    output: dict[str, Any],
    *,
    expected_dimension: str,
) -> None:
    missing = REQUIRED_SCHEMA_KEYS - set(output)
    if missing:
        raise ValueError(f"Missing dimension output keys: {sorted(missing)}")
    if output["dimension"] != expected_dimension:
        raise ValueError(f"Expected dimension {expected_dimension}, got {output['dimension']}")
    if not isinstance(output["reasoning_chain"], list) or len(output["reasoning_chain"]) < 3:
        raise ValueError("reasoning_chain must contain at least three items")
    if not isinstance(output["evidence"], list):
        raise ValueError("evidence must be a list")
    score = output["score"]
    if not isinstance(score, dict) or not {"value", "label", "rubric_basis"} <= set(score):
        raise ValueError("score must contain value, label, and rubric_basis")
    degradation = output["degradation"]
    if not isinstance(degradation, dict) or not {
        "degraded",
        "missing_plus",
        "upgrade_hook",
    } <= set(degradation):
        raise ValueError("degradation must contain degraded, missing_plus, and upgrade_hook")


def _build_business_model_user_prompt(fact_base: dict[str, Any]) -> str:
    fact_base_json = json.dumps(fact_base, ensure_ascii=False, indent=2)
    return f"""{BUSINESS_MODEL_PROMPT}

共享事实底座如下。财务数字均为 ground truth，不得新增、修改或重算：
{fact_base_json}
"""
