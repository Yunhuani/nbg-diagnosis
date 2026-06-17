from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from analysis.llm_client import call_deepseek_json


ACTION_MAP_SYSTEM_PROMPT = """你是「泽思 NBG 增长方案」的第三层四类行动地图引擎。

你的任务只做方案五层结构的第三层：action_map。输入是诊断 synthesis、第一层 strategic_thesis、第二层 lever_matrix；你要把选中的增长杠杆拆成具体行动，并归入四类行动之一。

四类行动定义：
- 战略方向：关乎「往哪走」的方向性动作。
- 战术方向：产品/业务/渠道/运营层面的打法动作。
- 管理方向：组织/人才/流程层面的动作。
- 风险财务：守住底线、保障现金/防范风险的动作。

铁律：
- 只输出严格 JSON，不要前言、解释或 Markdown。
- 每个行动必须具体可执行，有明确动作对象和动作方式，不得写「加强品牌」「优化运营」「提升效率」这类空泛口号。
- 行动必须由 strategic_thesis 和 lever_matrix.selected 推导，不得脱离前两层另起炉灶。
- grounded_in 必须引用 synthesis.findings[].id、strategic_thesis / from_to / tradeoffs / transition_to_solution，或 lever_matrix 中的杠杆名称。
- 四类不必平均分配，但战略方向、战术方向必须覆盖；管理方向、风险财务按本案例诊断真实需要配置。
- 不得输出阶段路径、90天路线图、预算表或项目排期。
"""

ACTION_MAP_USER_PROMPT = """你会收到诊断 synthesis、战略主张 strategic_thesis 和杠杆矩阵 lever_matrix。基于它们生成方案第三层「四类行动地图」。

输出 JSON schema：
{
  "actions": [
    {
      "action": "具体可执行动作，如：用50万私域会员的耗材复购故事做小红书成分党内容",
      "category": "战略方向|战术方向|管理方向|风险财务",
      "grounded_in": ["引用 synthesis.findings[].id、strategic_thesis 字段名、或 lever_matrix 中的杠杆名称"],
      "owner": "负责方向，如：品牌负责人/销售负责人/财务负责人/创始人",
      "expected_output": "明确产出物，如：复购内容选题库/工程客户白名单/接单底线表"
    }
  ]
}

质量要求：
1. actions 至少 4 个。
2. category 只能从四类定义中选择。
3. 每个行动必须能看出「做什么对象、用什么方式、产出什么」，不能只是方向词。
4. grounded_in 必须扣住前两层；优先引用 selected 杠杆名称和 synthesis.findings[].id。
5. 不要平均主义；按本案例真实短板和机会分布行动。
"""

REQUIRED_ACTION_MAP_KEYS = {"actions"}
REQUIRED_ACTION_KEYS = {"action", "category", "grounded_in", "owner", "expected_output"}
VALID_ACTION_CATEGORIES = {"战略方向", "战术方向", "管理方向", "风险财务"}
REQUIRED_COVERAGE_CATEGORIES = {"战略方向", "战术方向"}

ACTION_MECHANISM_MARKERS = (
    "把",
    "用",
    "将",
    "为",
    "对",
    "针对",
    "基于",
    "围绕",
    "通过",
    "设置",
    "建立",
    "推出",
    "设计",
    "梳理",
    "拆分",
    "绑定",
    "转成",
    "整理",
    "暂停",
    "砍掉",
    "筛选",
    "配置",
    "制定",
)


def call_action_map_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    return call_deepseek_json(
        system_prompt,
        user_prompt,
        model=os.environ.get("DEEPSEEK_ACTION_MAP_MODEL"),
    )


def generate_action_map(
    synthesis_output: dict[str, Any],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    *,
    llm_call: Callable[[str, str], dict[str, Any]] = call_action_map_json,
) -> dict[str, Any]:
    user_prompt = _build_action_map_user_prompt(synthesis_output, strategic_thesis_output, lever_matrix_output)
    result = llm_call(ACTION_MAP_SYSTEM_PROMPT, user_prompt)
    validate_action_map_output(result, synthesis_output, strategic_thesis_output, lever_matrix_output)
    return result


def validate_action_map_output(
    output: dict[str, Any],
    synthesis_output: dict[str, Any],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
) -> None:
    if not isinstance(output, dict):
        raise ValueError(f"action map output must be an object, got {type(output).__name__}")

    missing = REQUIRED_ACTION_MAP_KEYS - set(output)
    if missing:
        raise ValueError(f"action map output missing keys: {sorted(missing)}")

    actions = output["actions"]
    if not isinstance(actions, list):
        raise ValueError(f"actions must be an array, got {type(actions).__name__}")
    if len(actions) < 4:
        raise ValueError("actions must contain at least 4 actions")

    categories: set[str] = set()
    for index, item in enumerate(actions):
        _validate_action_item(item, index, synthesis_output, strategic_thesis_output, lever_matrix_output)
        categories.add(item["category"])

    missing_coverage = REQUIRED_COVERAGE_CATEGORIES - categories
    if missing_coverage:
        raise ValueError(f"actions must cover categories: {sorted(missing_coverage)}")


def _validate_action_item(
    item: Any,
    index: int,
    synthesis_output: dict[str, Any],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
) -> None:
    if not isinstance(item, dict):
        raise ValueError(f"actions[{index}] must be an object, got {type(item).__name__}")

    missing = REQUIRED_ACTION_KEYS - set(item)
    if missing:
        raise ValueError(f"actions[{index}] missing keys: {sorted(missing)}")

    action = item["action"]
    if not isinstance(action, str) or not action.strip():
        raise ValueError(f"actions[{index}].action must be a non-empty string")
    if not _has_specific_action_shape(action):
        raise ValueError(f"actions[{index}].action must include a concrete object and execution mechanism")

    category = item["category"]
    if category not in VALID_ACTION_CATEGORIES:
        raise ValueError(f"actions[{index}].category must be one of {sorted(VALID_ACTION_CATEGORIES)}")

    _validate_string_array(item["grounded_in"], f"actions[{index}].grounded_in")
    if not item["grounded_in"]:
        raise ValueError(f"actions[{index}].grounded_in must not be empty")
    _validate_grounding(item["grounded_in"], synthesis_output, strategic_thesis_output, lever_matrix_output)

    for key in ("owner", "expected_output"):
        value = item[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"actions[{index}].{key} must be a non-empty string")
    if not _has_specific_output_shape(item["expected_output"]):
        raise ValueError(f"actions[{index}].expected_output must name a concrete output")


def _has_specific_action_shape(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 10:
        return False
    return any(marker in stripped for marker in ACTION_MECHANISM_MARKERS)


def _has_specific_output_shape(text: str) -> bool:
    stripped = text.strip()
    if len(stripped) < 4:
        return False
    output_markers = ("表", "清单", "名单", "库", "包", "机制", "规则", "模板", "脚本", "素材", "看板", "标准", "方案")
    return any(marker in stripped for marker in output_markers)


def _build_action_map_user_prompt(
    synthesis_output: dict[str, Any],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
) -> str:
    payload = {
        "synthesis_output": synthesis_output,
        "strategic_thesis_output": strategic_thesis_output,
        "lever_matrix_output": lever_matrix_output,
    }
    return f"""{ACTION_MAP_USER_PROMPT}

输入如下：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def _validate_string_array(value: Any, field: str) -> None:
    if not isinstance(value, list):
        raise ValueError(f"{field} must be an array")
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field}[{index}] must be a non-empty string")


def _validate_grounding(
    grounded_in: list[str],
    synthesis_output: dict[str, Any],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
) -> None:
    finding_ids = {
        item["id"]
        for item in synthesis_output.get("findings", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    }
    known_synthesis = {
        "overall_judgment",
        "three_key_findings",
        "confirmed_reversals",
        "cross_resonances",
        "transition_to_solution",
    }
    known_strategy = {
        key
        for key in ("strategic_thesis", "from_to", "reasoning", "grounded_in", "key_assumptions", "tradeoffs")
        if key in strategic_thesis_output
    }
    lever_names = {
        lever["name"]
        for lever in lever_matrix_output.get("levers", [])
        if isinstance(lever, dict) and isinstance(lever.get("name"), str)
    }
    selected_names = {
        item["name"]
        for item in lever_matrix_output.get("selected", [])
        if isinstance(item, dict) and isinstance(item.get("name"), str)
    }
    known_lever_fields = {"levers", "selected", "lever_matrix"}

    allowed_terms = finding_ids | known_synthesis | known_strategy | lever_names | selected_names | known_lever_fields
    for index, item in enumerate(grounded_in):
        if item in allowed_terms:
            continue
        if any(term and term in item for term in allowed_terms):
            continue
        raise ValueError(
            f"grounded_in[{index}] must reference synthesis, strategy, or lever matrix fields, got {item!r}"
        )
