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

BUSINESS_MODEL_PROMPT = """你正在做【商业模式】维度,不是财务维度。用商业模式画布(九模块)分析这家企业的赚钱逻辑是否可持续、哪个环节最脆弱。

【铁律:你看得到财务数字,但绝不能把"复述财务数字"当成你的分析】
- financial_facts(亏损线、集中度、现金跑道)是你的证据,不是你的结论。
- core_judgment 必须是关于"价值主张/赚钱逻辑/收入结构"的判断,财务数字只能用来佐证。
- ✗ 错误(这是在做财务维):"你的赚钱逻辑正被亏损产品线和客户集中侵蚀"——只是复述财务。
- ✓ 正确:指出画布里哪两个模块"错配",以及这个错配在商业模式层意味着什么。例:"你的价值主张是'全品类一站式代工',但成本结构撑不起法兰线——你在用赚钱的产品给一个'凑齐品类'的执念输血。"

【必须做的分析动作】
1. 用画布判断:价值主张还独特吗?关键资源/能力是否正被替代?收入靠什么结构撑?
2. 找出最脆弱环节,且必须落在"模块之间的匹配关系"上(如价值主张 vs 成本结构、收入来源 vs 关键资源),不是孤立某一个模块。
3. 用财务 ground truth 佐证这个错配,但不得让财务复述占据主体。

【尝试反转(本维是反转高发区)】
认真尝试找一个反转:客户视为软肋的,是否其实是商业模式上的资产?按四关检验(风险真实/机制具体/可证伪/可决策)。真试过仍找不到,才置 reversal_candidate=null。

【数据标记】
来自 financial_facts 的数字,source_type 一律标 "computed";客户问卷里的定性信息标 "client_provided"。

【输出格式铁律——与上面的分析方法分开】
上面教你的是"怎么思考",不是输出字段名。最终你必须、且只能输出 docs/五维分析Prompt规范.md 第七节的统一 schema,字段名严格如下,一个不能改、不能少、不能自造:
dimension, framework, core_judgment, reasoning_chain(数组,把因果链拆成几环), evidence(数组,每条含 claim/value/benchmark/source_type/source), reversal_candidate(按3.3结构,或null), score(含value/label/rubric_basis), degradation, strength, open_questions。
dimension 字段必须填英文枚举值 "business_model",不是中文"商业模式"。
score.label 只能填 "健康"、"亚健康"、"警告" 三者之一;score.value 必须是 1-10 的整数。
strength 只能填 "high"、"medium"、"low" 三者之一。
degradation 必须是对象,且包含 degraded(布尔)、missing_plus(数组)、upgrade_hook(字符串)。
reasoning_chain、evidence、open_questions 必须是数组。
不要输出 weakest_link、four_checks、module_pair 这类字段。你对"最脆弱环节"的分析,放进 core_judgment 和 reasoning_chain;反转放进 reversal_candidate;四关检验对应 reversal_candidate 里的 mechanism/falsifier 等字段。

严格按此结构和类型输出(这是格式示意,内容你填):
{
  "dimension": "business_model",
  "framework": ["商业模式画布"],
  "core_judgment": "一句话观点结论",
  "reasoning_chain": ["第1环", "第2环", "第3环"],
  "evidence": [
    {
      "claim": "",
      "value": "",
      "benchmark": "",
      "source_type": "computed|client_provided",
      "source": ""
    }
  ],
  "reversal_candidate": {
    "naive_reading": "",
    "reframe": "",
    "mechanism": "",
    "falsifier": "",
    "confidence": 0.7,
    "status": "needs_human_falsifier_check",
    "depends_on": []
  },
  "score": {"value": 4, "label": "警告", "rubric_basis": ""},
  "degradation": {"degraded": true, "missing_plus": [], "upgrade_hook": ""},
  "strength": "low",
  "open_questions": ["问题1", "问题2"]
}
若没有通过四关检验的反转,reversal_candidate 填 null。不要输出 reversal、decision_hook 等非规范字段。
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

VALID_DIMENSIONS = {"market", "competition", "business_model", "capability", "finance"}
VALID_SCORE_LABELS = {"健康", "亚健康", "警告"}
VALID_STRENGTHS = {"high", "medium", "low"}


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
    if not isinstance(output, dict):
        raise ValueError(f"output must be an object, got {type(output).__name__}")

    missing = REQUIRED_SCHEMA_KEYS - set(output)
    if missing:
        raise ValueError(f"Missing dimension output keys: {sorted(missing)}")

    dimension = output["dimension"]
    if dimension not in VALID_DIMENSIONS:
        raise ValueError(
            f"dimension must be one of {sorted(VALID_DIMENSIONS)}, got {dimension!r}"
        )
    if dimension != expected_dimension:
        raise ValueError(f"dimension must be {expected_dimension!r}, got {dimension!r}")

    if not isinstance(output["framework"], list):
        raise ValueError(f"framework must be an array, got {type(output['framework']).__name__}")
    if not isinstance(output["core_judgment"], str):
        raise ValueError(
            f"core_judgment must be a string, got {type(output['core_judgment']).__name__}"
        )
    if not isinstance(output["reasoning_chain"], list):
        raise ValueError(
            f"reasoning_chain must be an array, got {type(output['reasoning_chain']).__name__}"
        )
    if len(output["reasoning_chain"]) < 3:
        raise ValueError("reasoning_chain must contain at least three items")
    if not isinstance(output["evidence"], list):
        raise ValueError(f"evidence must be an array, got {type(output['evidence']).__name__}")
    for index, item in enumerate(output["evidence"]):
        if not isinstance(item, dict):
            raise ValueError(f"evidence[{index}] must be an object, got {type(item).__name__}")
        required_evidence_keys = {"claim", "value", "benchmark", "source_type", "source"}
        missing_evidence = required_evidence_keys - set(item)
        if missing_evidence:
            raise ValueError(
                f"evidence[{index}] missing keys: {sorted(missing_evidence)}"
            )

    score = output["score"]
    if not isinstance(score, dict):
        raise ValueError(f"score must be an object, got {type(score).__name__}")
    missing_score = {"value", "label", "rubric_basis"} - set(score)
    if missing_score:
        raise ValueError(f"score missing keys: {sorted(missing_score)}")
    if not isinstance(score["value"], int) or not 1 <= score["value"] <= 10:
        raise ValueError(f"score.value must be an integer from 1 to 10, got {score['value']!r}")
    if score["label"] not in VALID_SCORE_LABELS:
        raise ValueError(
            f"score.label must be one of {sorted(VALID_SCORE_LABELS)}, got {score['label']!r}"
        )
    if not isinstance(score["rubric_basis"], str):
        raise ValueError(
            f"score.rubric_basis must be a string, got {type(score['rubric_basis']).__name__}"
        )

    degradation = output["degradation"]
    if not isinstance(degradation, dict):
        raise ValueError(f"degradation must be an object, got {type(degradation).__name__}")
    missing_degradation = {"degraded", "missing_plus", "upgrade_hook"} - set(degradation)
    if missing_degradation:
        raise ValueError(f"degradation missing keys: {sorted(missing_degradation)}")
    if not isinstance(degradation["degraded"], bool):
        raise ValueError(
            f"degradation.degraded must be a boolean, got {type(degradation['degraded']).__name__}"
        )
    if not isinstance(degradation["missing_plus"], list):
        raise ValueError(
            "degradation.missing_plus must be an array, "
            f"got {type(degradation['missing_plus']).__name__}"
        )
    if not isinstance(degradation["upgrade_hook"], str):
        raise ValueError(
            "degradation.upgrade_hook must be a string, "
            f"got {type(degradation['upgrade_hook']).__name__}"
        )

    if output["strength"] not in VALID_STRENGTHS:
        raise ValueError(
            f"strength must be one of {sorted(VALID_STRENGTHS)}, got {output['strength']!r}"
        )
    if not isinstance(output["open_questions"], list):
        raise ValueError(
            f"open_questions must be an array, got {type(output['open_questions']).__name__}"
        )


def _build_business_model_user_prompt(fact_base: dict[str, Any]) -> str:
    fact_base_json = json.dumps(fact_base, ensure_ascii=False, indent=2)
    return f"""{BUSINESS_MODEL_PROMPT}

共享事实底座如下。财务数字均为 ground truth，不得新增、修改或重算：
{fact_base_json}
"""
