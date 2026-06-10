from copy import deepcopy

from analysis.redline_check import run_redline_check


FINANCIAL_FACTS = {
    "tier": "full",
    "product_lines": [
        {
            "name": "淋浴隔断五金",
            "full_cost_net": 1160,
            "revenue": 6800,
            "revenue_share": 0.366,
            "unit": "万元",
            "is_loss": False,
        },
        {
            "name": "法兰/排水配件",
            "full_cost_net": -410,
            "revenue": 4200,
            "revenue_share": 0.226,
            "unit": "万元",
            "is_loss": True,
        }
    ],
    "customer_concentration": {
        "top3_pct": 65,
        "top1_pct": 35,
        "benchmark_healthy": 40,
    },
    "cash_runway_months": 1.6,
    "ar": {
        "balance": 4960,
        "days": 97,
        "releasable_at_60days": 1892,
        "unit": "万元",
    },
}

SOURCE_CORPORA = {
    "market": [
        {
            "claim": "美国淋浴隔断市场稳定增长",
            "value": "$3.8B(2022)→$5.15B(2028),CAGR 5.2%",
            "source_url": "researchandmarkets.com/report/shower-enclosure",
            "source_tier": "可信二手",
        }
    ],
    "competition": [
        {
            "claim": "浙江淋浴房出口均价较低",
            "value": "出口均价仅65.9%",
            "source_url": "ceramicschina.com/PG_ViewNews_128452",
            "source_tier": "可信二手",
        }
    ],
}


def _evidence(claim, value, source_type, source, benchmark=""):
    return {
        "claim": claim,
        "value": value,
        "benchmark": benchmark,
        "source_type": source_type,
        "source": source,
    }


def _dimension(dimension, score, evidence):
    return {
        "dimension": dimension,
        "framework": ["测试框架"],
        "core_judgment": f"{dimension} 判断",
        "reasoning_chain": ["第1环", "第2环", "第3环"],
        "evidence": evidence,
        "reversal_candidate": None,
        "score": {"value": score, "label": "亚健康", "rubric_basis": "测试"},
        "degradation": {"degraded": False, "missing_plus": [], "upgrade_hook": ""},
        "strength": "high",
        "open_questions": [],
    }


def _clean_dimension_outputs():
    return [
        _dimension(
            "market",
            6,
            [
                _evidence(
                    "美国淋浴隔断市场稳定增长",
                    "$3.8B(2022)→$5.15B(2028),CAGR 5.2%",
                    "verified",
                    "researchandmarkets.com/report/shower-enclosure",
                    "可信二手报告数据",
                )
            ],
        ),
        _dimension(
            "competition",
            6,
            [
                _evidence(
                    "浙江淋浴房出口均价较低",
                    "65.9%",
                    "verified",
                    "ceramicschina.com/PG_ViewNews_128452",
                    "可信二手报告数据",
                ),
                _evidence(
                    "前三大客户集中度为65%",
                    "65%",
                    "computed",
                    "financial_facts.customer_concentration.top3_pct",
                    "财务模块原值",
                ),
            ],
        ),
        _dimension(
            "business_model",
            4,
            [
                _evidence("法兰线亏损印证模式错配", "亏410万", "computed", "financial_facts.product_lines"),
                _evidence("主力产品收入占比", "36.6%", "computed", "financial_facts.product_lines"),
            ],
        ),
        _dimension(
            "capability",
            5,
            [_evidence("营销能力偏弱", "弱", "client_provided", "diagnosis_intake.capability")],
        ),
        _dimension(
            "finance",
            3,
            [_evidence("现金跑道偏紧", "1.6个月", "computed", "financial_facts.cash_runway_months")],
        ),
    ]


def _clean_synthesis():
    return {
        "findings": [
            {
                "id": "F01",
                "dimension": "finance",
                "statement": "现金跑道低于2个月",
                "type": "judgment",
                "strength": "high",
                "quant_value": "1.6个月",
            },
            {
                "id": "F02",
                "dimension": "competition",
                "statement": "客户集中度65%也是壁垒候选",
                "type": "reversal",
                "strength": "high",
                "quant_value": "65%",
            },
            {
                "id": "F03",
                "dimension": "business_model",
                "statement": "法兰线亏损印证模式错配",
                "type": "evidence",
                "strength": "high",
                "quant_value": "-410万",
            },
        ],
        "overall_judgment": "外部机会尚可,内部模式和财务承压",
        "overall_score": 4.8,
        "score_label": "警告",
        "cross_resonances": [
            {
                "fact": "客户集中度65%",
                "finding_ids": ["F01", "F02"],
                "dim_a": "finance",
                "meaning_a": "风险",
                "dim_b": "competition",
                "meaning_b": "壁垒资产",
            }
        ],
        "confirmed_reversals": [
            {
                "finding_id": "F02",
                "naive_reading": "客户集中度65%是风险",
                "reframe": "深度绑定形成切换成本",
                "mechanism": "认证、合作年限和定制适配共同绑定客户",
                "falsifier": "大客户正在询价竞品或认证被同行普遍获得",
                "confidence": 0.7,
                "status": "needs_human_falsifier_check",
                "depends_on": ["competition.unique_assets"],
            }
        ],
        "three_key_findings": [
            {"finding_id": "F01", "title": "现金跑道警告", "why_surprising": "订单不等于安全"},
            {"finding_id": "F02", "title": "集中度也是壁垒候选", "why_surprising": "风险可被重读"},
            {"finding_id": "F03", "title": "亏损线暴露模式错配", "why_surprising": "收入不等于利润"},
        ],
        "consistency_flags": [],
        "transition_to_solution": "先止血,再围绕高值机会重排增长方向",
    }


def _run(dimensions, synthesis):
    return run_redline_check(
        dimensions,
        synthesis,
        financial_facts=FINANCIAL_FACTS,
        source_corpora=SOURCE_CORPORA,
    )


def _checks(report):
    return {failure["check"] for failure in report["failures"]}


def test_redline_check_passes_clean_sample():
    report = _run(_clean_dimension_outputs(), _clean_synthesis())

    assert report["passed"] is True
    assert report["failures"] == []
    assert report["score_check"]["dimension_scores"] == {
        "market": 6,
        "competition": 6,
        "business_model": 4,
        "capability": 5,
        "finance": 3,
    }
    assert report["score_check"]["computed_overall_score"] == 4.8


def test_redline_check_accepts_indexed_financial_fact_path():
    dimensions = _clean_dimension_outputs()
    dimensions[2]["evidence"][0]["source"] = "financial_facts.product_lines[1].full_cost_net"

    report = _run(dimensions, _clean_synthesis())

    assert report["passed"] is True


def test_redline_check_accepts_comma_separated_financial_fact_paths():
    dimensions = _clean_dimension_outputs()
    dimensions[1]["evidence"][1]["value"] = "65%和35%"
    dimensions[1]["evidence"][1]["source"] = (
        "financial_facts.customer_concentration.top3_pct, "
        "financial_facts.customer_concentration.top1_pct"
    )

    report = _run(dimensions, _clean_synthesis())

    assert report["passed"] is True


def test_redline_check_accepts_shorthand_after_comma_by_inheriting_parent_path():
    dimensions = _clean_dimension_outputs()
    dimensions[2]["evidence"][0]["value"] = "亏410万,收入占比22.6%"
    dimensions[2]["evidence"][0]["source"] = (
        "financial_facts.product_lines[1].full_cost_net, revenue_share"
    )

    report = _run(dimensions, _clean_synthesis())

    assert report["passed"] is True


def test_redline_check_rejects_invalid_computed_financial_path():
    dimensions = _clean_dimension_outputs()
    dimensions[2]["evidence"][0]["source"] = "financial_facts.product_lines[99].full_cost_net"

    report = _run(dimensions, _clean_synthesis())

    assert report["passed"] is False
    assert "computed_financial_consistency" in _checks(report)


def test_redline_check_catches_brainmade_external_number():
    dimensions = _clean_dimension_outputs()
    dimensions[0]["evidence"][0]["source"] = "made-up-source.example"

    report = _run(dimensions, _clean_synthesis())

    assert report["passed"] is False
    assert "brainmade_external_number" in _checks(report)


def test_redline_check_catches_rewritten_financial_number():
    dimensions = _clean_dimension_outputs()
    dimensions[2]["evidence"][0]["value"] = "亏400万"

    report = _run(dimensions, _clean_synthesis())

    assert report["passed"] is False
    assert "computed_financial_consistency" in _checks(report)


def test_redline_check_catches_market_percent_mislabelled_as_computed():
    dimensions = _clean_dimension_outputs()
    dimensions[0]["evidence"][0] = _evidence(
        "市场机会错误标注为财务计算值",
        "17%",
        "computed",
        "financial_facts",
    )

    report = _run(dimensions, _clean_synthesis())

    assert report["passed"] is False
    assert "computed_financial_consistency" in _checks(report)


def test_redline_check_catches_missing_reversal_falsifier():
    synthesis = _clean_synthesis()
    synthesis["confirmed_reversals"][0]["falsifier"] = ""

    report = _run(_clean_dimension_outputs(), synthesis)

    assert report["passed"] is False
    assert "reversal_integrity" in _checks(report)


def test_redline_check_catches_bad_finding_id_reference():
    synthesis = _clean_synthesis()
    synthesis["three_key_findings"][0]["finding_id"] = "F99"

    report = _run(_clean_dimension_outputs(), synthesis)

    assert report["passed"] is False
    assert "finding_id_reference" in _checks(report)


def test_redline_check_catches_wrong_overall_score():
    synthesis = deepcopy(_clean_synthesis())
    synthesis["overall_score"] = 3.8

    report = _run(_clean_dimension_outputs(), synthesis)

    assert report["passed"] is False
    assert "overall_score" in _checks(report)
    assert "expected 4.8" in report["failures"][0]["reason"]
