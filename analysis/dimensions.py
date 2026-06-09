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

def _format_rules_prompt(dimension: str, framework: str) -> str:
    return f"""【输出格式铁律——与上面的分析方法分开】
上面教你的是"怎么思考",不是输出字段名。最终你必须、且只能输出 docs/五维分析Prompt规范.md 第七节的统一 schema,字段名严格如下,一个不能改、不能少、不能自造:
dimension, framework, core_judgment, reasoning_chain(数组,把因果链拆成几环), evidence(数组,每条含 claim/value/benchmark/source_type/source), reversal_candidate(按3.3结构,或null), score(含value/label/rubric_basis), degradation, strength, open_questions。
dimension 字段必须填英文枚举值 "{dimension}",不是中文。
framework 必须是数组,例如 ["{framework}"]。
score.label 只能填 "健康"、"亚健康"、"警告" 三者之一;score.value 必须是 1-10 的整数。
strength 只能填 "high"、"medium"、"low" 三者之一。
degradation 必须是对象,且包含 degraded(布尔)、missing_plus(数组)、upgrade_hook(字符串)。
reasoning_chain、evidence、open_questions 必须是数组。
不要输出 weakest_link、four_checks、module_pair 这类字段。你对"最脆弱环节/关键短板/财务风险"的分析,放进 core_judgment 和 reasoning_chain;反转放进 reversal_candidate;四关检验对应 reversal_candidate 里的 mechanism/falsifier 等字段。

严格按此结构和类型输出(这是格式示意,内容你填):
{{
  "dimension": "{dimension}",
  "framework": ["{framework}"],
  "core_judgment": "一句话观点结论",
  "reasoning_chain": ["第1环", "第2环", "第3环"],
  "evidence": [
    {{
      "claim": "",
      "value": "",
      "benchmark": "",
      "source_type": "computed|client_provided",
      "source": ""
    }}
  ],
  "reversal_candidate": {{
    "naive_reading": "",
    "reframe": "",
    "mechanism": "",
    "falsifier": "",
    "confidence": 0.7,
    "status": "needs_human_falsifier_check",
    "depends_on": []
  }},
  "score": {{"value": 4, "label": "警告", "rubric_basis": ""}},
  "degradation": {{"degraded": true, "missing_plus": [], "upgrade_hook": ""}},
  "strength": "low",
  "open_questions": ["问题1", "问题2"]
}}
若没有通过四关检验的反转,reversal_candidate 填 null。不要输出 reversal、decision_hook 等非规范字段。"""


NON_FINANCE_BOUNDARY_PROMPT = """【跨维边界:财务数字的解读权属于财务维,你不得抢】
财务数字(产品线盈亏、客户集中度、现金跑道、应收)的系统性解读是财务维的职责,不是你的。在你这一维:
- 不得把财务数字当成分析对象逐条陈列、反复解读。
- 只允许把某个财务结果当作"证据",指证你这一维发现的本职问题真实存在,且一句带过、不展开。
- 你的 evidence 里,本维领域的证据必须占多数;财务类证据最多一条。"""


BUSINESS_MODEL_PROMPT = f"""你正在做【商业模式】维度,不是财务维度。用商业模式画布(九模块)分析这家企业的赚钱逻辑是否可持续、哪个环节最脆弱。

【铁律:你看得到财务数字,但绝不能把"复述财务数字"当成你的分析】
- financial_facts(亏损线、集中度、现金跑道)是你的证据,不是你的结论。
- core_judgment 必须是关于"价值主张/赚钱逻辑/收入结构"的判断,财务数字只能用来佐证。
- ✗ 错误(这是在做财务维):"你的赚钱逻辑正被亏损产品线和客户集中侵蚀"——只是复述财务。
- ✓ 正确:指出画布里哪两个模块"错配",以及这个错配在商业模式层意味着什么。例:"你的价值主张是'全品类一站式代工',但成本结构撑不起法兰线——你在用赚钱的产品给一个'凑齐品类'的执念输血。"

{NON_FINANCE_BOUNDARY_PROMPT}

【必须做的分析动作】
1. 用画布判断:价值主张还独特吗?关键资源/能力是否正被替代?收入靠什么结构撑?
2. 找出最脆弱环节,且必须落在"模块之间的匹配关系"上(如价值主张 vs 成本结构、收入来源 vs 关键资源),不是孤立某一个模块。
3. 用财务 ground truth 佐证这个错配,但不得让财务复述占据主体。

【尝试反转(本维是反转高发区)】
认真尝试找一个反转:客户视为软肋的,是否其实是商业模式上的资产?按四关检验(风险真实/机制具体/可证伪/可决策)。真试过仍找不到,才置 reversal_candidate=null。

【数据标记】
来自 financial_facts 的数字,source_type 一律标 "computed";客户问卷里的定性信息标 "client_provided"。

{_format_rules_prompt("business_model", "商业模式画布")}
"""

CAPABILITY_PROMPT = f"""你正在做【内部能力】维度。用能力-资源矩阵判断这家企业现有团队/资源能否支撑增长,找关键短板。

【铁律:只做本维判断】
- 只基于事实底座里的客观能力数据做本维判断,不要去读取、引用或假设其他维度的结论。
- 市场、竞争等跨维匹配留给综合环节,本维只判断能力与资源本身。
- 你的分析对象是 team_structure 和 function_strength 里的能力数据(生产/供应链/销售/营销/财务管理强弱)。

{NON_FINANCE_BOUNDARY_PROMPT}

【必须做的分析动作】
1. 识别现有团队结构、关键职能强弱、数字化程度、关键人才依赖等能力事实。
2. 找出关键短板,按"差距大小×对增长的关键性"排序。
3. 对每个核心短板标明倾向:自建、外包、找伙伴。只给方向,不给具体执行方案。
4. 若测试数据缺人才依赖、数字化程度等 Plus 项,正常降级,并在 degradation 中说明。
5. 用能力-资源矩阵判断:现有能力能否支撑增长?最关键的短板是哪几个?

正例:"营销与财务管理双弱(均为'弱'),意味着你既打不出品牌溢价、又管不住成本——这是你从'代工走量'转向'高附加值'最大的能力缺口。"
财务结果只能用来佐证能力短板(如"法兰线长期亏损未被纠正,印证财务管控能力缺位"),一句带过,不展开财务数字本身。

【数据标记】
客户问卷里的能力定性信息,source_type 标 "client_provided"。若引用 financial_facts 里的数字作为辅助证据,source_type 标 "computed"。

{_format_rules_prompt("capability", "能力-资源矩阵")}
"""

FINANCE_PROMPT = f"""你正在做【财务健康度】维度。用杜邦分析 + 全成本作业法 + 营运资金周期模型解读企业财务风险。

【最重要铁律:解读,不计算】
- financial_facts 里的数字是 ground truth,严禁新增、修改、重算任何财务数字。
- 你的职责是解读:哪个数字最致命,它意味着什么,沿 So-What 链逼出客户没意识到的结构性结论。
- 例如:不是重新计算亏损,而是解释"你以为它保量,实际每年悄悄亏 410 万"对现金、模式和转型安全边际意味着什么。
- 若需要 financial_facts 里没有的数字,写进 open_questions 或 evidence 的定性说明,不得自己编。

【评分硬规则】
你必须先读取 financial_facts,并在硬规则允许范围内给分:
1. cash_runway_months < 2 → 财务维 score.value ≤ 3。
2. 任一 product_lines[].is_loss=true 且 revenue_share > 0.15 → score.value ≤ 4。
3. customer_concentration.top3_pct > 60 → score.value ≤ 5。
多条规则同时触发时,取最严格上限。模型只能在硬规则允许的区间内微调。
用甬辉数据时,现金跑道 1.6、法兰/排水配件亏损且收入占比 0.226、前三大客户 65%,三条规则都会触发,最终 score.value 必须 ≤ 3,score.label 应为 "警告"。

【必须做的分析动作】
1. 判断哪个财务事实最致命,不要平均摊开复述所有数字。
2. 对最致命事实走至少三环 So-What 链。
3. 明确说明哪些数字来自 financial_facts ground truth。
4. 若 financial_facts.tier 为 basic_only,只解读已有字段,对 null 字段降级,不得脑补。

【数据标记】
所有来自 financial_facts 的数字,source_type 一律标 "computed"。

{_format_rules_prompt("finance", "杜邦分析 + 全成本作业法 + 营运资金周期模型")}
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
VALID_EVIDENCE_SOURCE_TYPES = {
    "verified",
    "inferred",
    "client_provided",
    "computed",
}


def analyze_business_model(
    fact_base: dict[str, Any],
    *,
    llm_call: Callable[[str, str], dict[str, Any]] = call_deepseek_json,
) -> dict[str, Any]:
    user_prompt = _build_dimension_user_prompt(BUSINESS_MODEL_PROMPT, fact_base)
    result = llm_call(COMMON_SYSTEM_PROMPT, user_prompt)
    validate_dimension_output(result, expected_dimension="business_model")
    return result


def analyze_capability(
    fact_base: dict[str, Any],
    *,
    llm_call: Callable[[str, str], dict[str, Any]] = call_deepseek_json,
) -> dict[str, Any]:
    user_prompt = _build_dimension_user_prompt(CAPABILITY_PROMPT, fact_base)
    result = llm_call(COMMON_SYSTEM_PROMPT, user_prompt)
    validate_dimension_output(result, expected_dimension="capability")
    return result


def analyze_finance(
    fact_base: dict[str, Any],
    *,
    llm_call: Callable[[str, str], dict[str, Any]] = call_deepseek_json,
) -> dict[str, Any]:
    user_prompt = _build_dimension_user_prompt(FINANCE_PROMPT, fact_base)
    result = llm_call(COMMON_SYSTEM_PROMPT, user_prompt)
    validate_dimension_output(result, expected_dimension="finance")
    _validate_finance_score_cap(result, fact_base)
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
        if item["source_type"] not in VALID_EVIDENCE_SOURCE_TYPES:
            raise ValueError(
                f"evidence[{index}].source_type must be one of "
                f"{sorted(VALID_EVIDENCE_SOURCE_TYPES)}, got {item['source_type']!r}"
            )

    reversal = output["reversal_candidate"]
    if reversal is not None:
        if not isinstance(reversal, dict):
            raise ValueError(
                "reversal_candidate must be an object or null, "
                f"got {type(reversal).__name__}"
            )
        required_reversal_keys = {
            "naive_reading",
            "reframe",
            "mechanism",
            "falsifier",
            "confidence",
            "status",
            "depends_on",
        }
        missing_reversal = required_reversal_keys - set(reversal)
        if missing_reversal:
            raise ValueError(
                f"reversal_candidate missing keys: {sorted(missing_reversal)}"
            )
        if not isinstance(reversal["depends_on"], list):
            raise ValueError(
                "reversal_candidate.depends_on must be an array, "
                f"got {type(reversal['depends_on']).__name__}"
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


def _validate_finance_score_cap(output: dict[str, Any], fact_base: dict[str, Any]) -> None:
    cap = _finance_score_cap(fact_base.get("financial_facts", {}))
    score_value = output["score"]["value"]
    if score_value > cap:
        raise ValueError(
            f"finance score.value must be <= {cap} due to financial hard rules, "
            f"got {score_value}"
        )


def _finance_score_cap(financial_facts: dict[str, Any]) -> int:
    cap = 10
    cash_runway = financial_facts.get("cash_runway_months")
    if cash_runway is not None and cash_runway < 2:
        cap = min(cap, 3)

    product_lines = financial_facts.get("product_lines") or []
    if any(
        line.get("is_loss") is True and line.get("revenue_share", 0) > 0.15
        for line in product_lines
    ):
        cap = min(cap, 4)

    concentration = financial_facts.get("customer_concentration") or {}
    top3_pct = concentration.get("top3_pct")
    if top3_pct is not None and top3_pct > 60:
        cap = min(cap, 5)

    return cap


def _build_dimension_user_prompt(prompt: str, fact_base: dict[str, Any]) -> str:
    fact_base_json = json.dumps(fact_base, ensure_ascii=False, indent=2)
    return f"""{prompt}

共享事实底座如下。财务数字均为 ground truth，不得新增、修改或重算：
{fact_base_json}
"""
