from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from analysis.llm_client import call_deepseek_json


ROADMAP_SYSTEM_PROMPT = """你是「泽思 NBG 增长方案」的第四层三阶段路线图引擎。

你的任务只做方案五层结构的第四层：roadmap。输入是诊断 synthesis、五维诊断输出，以及前三层 strategic_thesis、lever_matrix、action_map；你要把 action_map 中的全部行动按真实时间先后和依赖关系排入三个阶段。

铁律：
- 只输出严格 JSON，不要前言、解释或 Markdown。
- 阶段名称必须根据本案例的战略节奏命名，不得套用固定阶段名。
- action_map 中的每个行动必须且只能出现一次，actions 必须逐字引用 action_map.actions[].action，不得改写、缩写或新增行动。
- 阶段顺序必须体现真实依赖：先处理前置约束和资源释放，再推进依赖这些条件的投入与扩张。例如存在亏损线处置时，应先完成止损和资源释放，再安排依赖该资源的开发投入。
- 每阶段的 goal、rationale、milestone 必须具体，写清阶段要达成的状态、排序依据和可指认里程碑；禁止只写「夯实基础」「提升能力」「实现增长」等空泛表述。
- 所有判断只能来自当前输入。不得推翻 financial_facts 的产品线盈亏事实，不得引入本案例不存在的公司、产品、行业、市场、渠道或外部机会。
- 如引用依据，只能引用当前输入中真实存在的 synthesis finding、dimension_outputs 结论、战略主张、杠杆或行动。
- 不得输出 90 天详细任务排期、预算表或前三层的重写版本。
"""

ROADMAP_USER_PROMPT = """你会收到诊断 synthesis、五维诊断输出、战略主张 strategic_thesis、杠杆矩阵 lever_matrix 和四类行动地图 action_map。基于它们生成方案第四层「三阶段路线图」。

输出 JSON schema：
{
  "phases": [
    {
      "phase_name": "按本案例战略节奏命名的阶段名",
      "goal": "本阶段要达成的具体状态",
      "actions": ["逐字引用 action_map.actions[].action"],
      "rationale": "为什么这些行动必须排在此阶段，以及它们与前后阶段的依赖关系",
      "milestone": "完成本阶段时可指认、可审核的里程碑"
    }
  ]
}

质量要求：
1. phases 必须正好 3 个，并按执行先后排列。
2. action_map 的全部行动必须分配完毕，每个行动只出现一次。
3. actions 只能逐字引用 action_map 中真实存在的 action，不得创造新行动。
4. phase_name、goal、rationale、milestone 必须结合本案例和本阶段行动具体书写。
5. 阶段划分要体现现金、能力、资源和业务动作之间的真实依赖，不做平均分配。
"""

REQUIRED_ROADMAP_KEYS = {"phases"}
REQUIRED_PHASE_KEYS = {"phase_name", "goal", "actions", "rationale", "milestone"}


def call_roadmap_json(system_prompt: str, user_prompt: str) -> dict[str, Any]:
    return call_deepseek_json(
        system_prompt,
        user_prompt,
        model=os.environ.get("DEEPSEEK_ROADMAP_MODEL"),
    )


def generate_roadmap(
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
    *,
    llm_call: Callable[[str, str], dict[str, Any]] = call_roadmap_json,
    max_attempts: int = 3,
) -> dict[str, Any]:
    user_prompt = _build_roadmap_user_prompt(
        synthesis_output,
        dimension_outputs,
        strategic_thesis_output,
        lever_matrix_output,
        action_map_output,
    )
    last_error: ValueError | None = None

    for attempt in range(1, max_attempts + 1):
        prompt = user_prompt
        if last_error is not None:
            prompt += (
                "\n\n上一次输出未通过客观 schema 校验。"
                f"校验错误：{last_error}。"
                "请只修正字段、类型、阶段数量或行动引用错误，重新输出完整 JSON。"
            )

        result = llm_call(ROADMAP_SYSTEM_PROMPT, prompt)
        print("=== RAW ROADMAP RESULT ===\n" + json.dumps(result, ensure_ascii=False, indent=2))
        try:
            validate_roadmap_output(result, action_map_output)
        except ValueError as error:
            last_error = error
            if attempt < max_attempts:
                print(f"=== RETRY ROADMAP ATTEMPT {attempt + 1}/{max_attempts}: {error} ===")
                continue
            raise
        return result

    raise RuntimeError("roadmap generation exhausted without a result")


def validate_roadmap_output(
    output: dict[str, Any],
    action_map_output: dict[str, Any],
) -> None:
    if not isinstance(output, dict):
        raise ValueError(f"roadmap output must be an object, got {type(output).__name__}")

    missing = REQUIRED_ROADMAP_KEYS - set(output)
    if missing:
        raise ValueError(f"roadmap output missing keys: {sorted(missing)}")

    phases = output["phases"]
    if not isinstance(phases, list):
        raise ValueError(f"phases must be an array, got {type(phases).__name__}")
    if len(phases) != 3:
        raise ValueError(f"phases must contain exactly 3 phases, got {len(phases)}")

    action_names = _action_names(action_map_output)
    assigned_actions: list[str] = []
    phase_names: set[str] = set()

    for index, phase in enumerate(phases):
        if not isinstance(phase, dict):
            raise ValueError(f"phases[{index}] must be an object, got {type(phase).__name__}")

        missing_phase = REQUIRED_PHASE_KEYS - set(phase)
        if missing_phase:
            raise ValueError(f"phases[{index}] missing keys: {sorted(missing_phase)}")

        for key in ("phase_name", "goal", "rationale", "milestone"):
            value = phase[key]
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"phases[{index}].{key} must be a non-empty string")

        phase_name = phase["phase_name"].strip()
        if phase_name in phase_names:
            raise ValueError(f"duplicate phase_name: {phase_name!r}")
        phase_names.add(phase_name)

        actions = phase["actions"]
        if not isinstance(actions, list):
            raise ValueError(f"phases[{index}].actions must be an array")
        if not actions:
            raise ValueError(f"phases[{index}].actions must not be empty")
        for action_index, action in enumerate(actions):
            if not isinstance(action, str) or not action.strip():
                raise ValueError(
                    f"phases[{index}].actions[{action_index}] must be a non-empty string"
                )
            if action not in action_names:
                raise ValueError(
                    f"phases[{index}].actions[{action_index}] must reference an action_map action, "
                    f"got {action!r}"
                )
            assigned_actions.append(action)

    if len(assigned_actions) != len(set(assigned_actions)):
        raise ValueError("each action_map action must appear in exactly one phase")
    if set(assigned_actions) != action_names:
        missing_actions = sorted(action_names - set(assigned_actions))
        raise ValueError(f"roadmap must include every action_map action, missing: {missing_actions}")


def _build_roadmap_user_prompt(
    synthesis_output: dict[str, Any],
    dimension_outputs: list[dict[str, Any]],
    strategic_thesis_output: dict[str, Any],
    lever_matrix_output: dict[str, Any],
    action_map_output: dict[str, Any],
) -> str:
    payload = {
        "synthesis_output": synthesis_output,
        "dimension_outputs": dimension_outputs,
        "strategic_thesis_output": strategic_thesis_output,
        "lever_matrix_output": lever_matrix_output,
        "action_map_output": action_map_output,
    }
    return f"""{ROADMAP_USER_PROMPT}

输入如下：
{json.dumps(payload, ensure_ascii=False, indent=2)}
"""


def _action_names(action_map_output: dict[str, Any]) -> set[str]:
    return {
        item["action"]
        for item in action_map_output.get("actions", [])
        if isinstance(item, dict) and isinstance(item.get("action"), str) and item["action"].strip()
    }
