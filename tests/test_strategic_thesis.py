import pytest

from solution.strategic_thesis import generate_strategic_thesis


def _synthesis_output():
    return {
        "findings": [
            {
                "id": "F01",
                "dimension": "finance",
                "statement": "现金安全边际已经进入警告区",
                "type": "judgment",
                "strength": "high",
                "quant_value": "1.6个月",
            },
            {
                "id": "F02",
                "dimension": "competition",
                "statement": "认证和大客户绑定形成工程渠道壁垒",
                "type": "reversal",
                "strength": "high",
                "quant_value": "65%",
            },
        ],
        "headline": "现金承压但认证可用",
        "overall_judgment": "公司不是没有增长机会，而是现金承压和通用代工模式限制了高值机会承接",
        "overall_score": 4.8,
        "score_label": "警告",
        "cross_resonances": [],
        "confirmed_reversals": [
            {
                "finding_id": "F02",
                "naive_reading": "大客户集中是风险",
                "reframe": "认证和多年适配形成切换成本",
                "mechanism": "认证、合作年限和定制适配叠加形成进入壁垒",
                "falsifier": "大客户正在询价竞品或认证已被同行普遍获得",
                "confidence": 0.7,
                "status": "needs_human_falsifier_check",
                "depends_on": ["competition.unique_assets"],
            }
        ],
        "three_key_findings": [
            {
                "finding_id": "F01",
                "title": "现金跑道不足",
                "why_surprising": "订单不少不等于现金安全",
            }
        ],
        "consistency_flags": [],
        "transition_to_solution": "先止住财务失血，再围绕认证壁垒重排增长方向",
    }


def test_generate_strategic_thesis_returns_schema_and_grounding():
    synthesis = _synthesis_output()

    def fake_llm(system_prompt, user_prompt):
        assert "只做方案五层结构的第一层" in system_prompt
        assert "synthesis_output" in user_prompt
        return {
            "strategic_thesis": "从消耗现金的通用件代工，转向认证壁垒支撑的中高端工程配套",
            "from_to": {
                "from": "继续用通用件和低毛利订单保规模",
                "to": "围绕认证和大客户适配能力承接中高端工程配套",
            },
            "reasoning": [
                "F01显示现金安全边际不足，不能继续靠低毛利规模消耗现金。",
                "F02显示认证和大客户绑定可能是壁垒，因此增长方向应围绕高切换成本客户展开。",
                "transition_to_solution已经收口为先止血再利用认证壁垒切高值。",
            ],
            "grounded_in": ["F01", "F02", "transition_to_solution"],
            "key_assumptions": ["F02的反转仍依赖人工核验：大客户没有转向竞品询价，认证未被同行普遍获得。"],
            "tradeoffs": ["放弃以低价通用件继续换规模。"],
        }

    result = generate_strategic_thesis(synthesis, llm_call=fake_llm)

    assert result["strategic_thesis"].startswith("从")
    assert result["from_to"]["to"] == "围绕认证和大客户适配能力承接中高端工程配套"
    assert "F01" in result["grounded_in"]


def test_generate_strategic_thesis_rejects_vague_thesis():
    synthesis = _synthesis_output()

    def fake_llm(_system_prompt, _user_prompt):
        return {
            "strategic_thesis": "加强品牌并优化运营提升增长质量",
            "from_to": {"from": "低效经营", "to": "高效经营"},
            "reasoning": ["overall_judgment指出需要改变。"],
            "grounded_in": ["overall_judgment"],
            "key_assumptions": [],
            "tradeoffs": ["放弃低效经营。"],
        }

    with pytest.raises(ValueError, match="从X转向Y|vague verb"):
        generate_strategic_thesis(synthesis, llm_call=fake_llm)
