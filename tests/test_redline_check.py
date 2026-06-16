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

CHENGXU_FINANCIAL_FACTS = {
    "tier": "full",
    "product_lines": [
        {
            "name": "高速电吹风",
            "full_cost_net": 1800,
            "revenue": 8000,
            "revenue_share": 0.417,
            "unit": "万元",
            "is_loss": False,
        },
        {
            "name": "洁面仪",
            "full_cost_net": 1000,
            "revenue": 4500,
            "revenue_share": 0.234,
            "unit": "万元",
            "is_loss": False,
        },
        {
            "name": "美容仪",
            "full_cost_net": 600,
            "revenue": 3500,
            "revenue_share": 0.182,
            "unit": "万元",
            "is_loss": False,
        },
        {
            "name": "配套耗材",
            "full_cost_net": 1000,
            "revenue": 2000,
            "revenue_share": 0.104,
            "unit": "万元",
            "is_loss": False,
        },
        {
            "name": "联名礼盒",
            "full_cost_net": 200,
            "revenue": 1200,
            "revenue_share": 0.062,
            "unit": "万元",
            "is_loss": False,
        },
    ],
    "customer_concentration": {
        "top3_pct": 5,
        "top1_pct": 2.5,
        "benchmark_healthy": 40,
    },
    "cash_runway_months": 15,
    "ar": {
        "balance": 1400,
        "days": 28,
        "releasable_at_60days": 0,
        "unit": "万元",
    },
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
        "headline": "外部尚可内部承压",
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


def test_redline_check_single_scope_runs_dimension_checks_without_five_dimensions():
    dimension = _dimension(
        "competition",
        6,
        [_evidence("竞争态势", "定性", "client_provided", "survey.competition")],
    )
    dimension["degradation"]["missing_plus"] = ["business_model.revenue_mix"]

    report = run_redline_check(
        [dimension],
        None,
        financial_facts=FINANCIAL_FACTS,
        source_corpora=SOURCE_CORPORA,
        availability_map={"plus_missing": ["business_model.revenue_mix"]},
        scope="single",
    )

    assert report["passed"] is False
    assert report["score_check"] is None
    assert "degradation_missing_plus" in _checks(report)


def test_redline_check_full_scope_runs_cross_output_checks():
    synthesis = deepcopy(_clean_synthesis())
    synthesis["overall_score"] = 3.8

    report = run_redline_check(
        _clean_dimension_outputs(),
        synthesis,
        financial_facts=FINANCIAL_FACTS,
        source_corpora=SOURCE_CORPORA,
        scope="full",
    )

    assert report["passed"] is False
    assert report["score_check"]["computed_overall_score"] == 4.8
    assert "overall_score" in _checks(report)


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


def test_redline_check_accepts_source_paths_with_values_semicolons_and_shorthand():
    dimension = _dimension(
        "business_model",
        4,
        [
            _evidence(
                "收入结构引用",
                "配套耗材收入占比10.4%,高速电吹风收入占比41.7%",
                "computed",
                (
                    "financial_facts.product_lines[3].revenue_share=0.104; "
                    "product_lines[0].revenue_share=0.417"
                ),
            )
        ],
    )

    report = run_redline_check(
        [dimension],
        None,
        financial_facts=CHENGXU_FINANCIAL_FACTS,
        source_corpora=SOURCE_CORPORA,
        scope="single",
    )

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
    dimensions[2]["evidence"][0]["source"] = "financial_facts.product_lines[1].full_cost_net"

    report = _run(dimensions, _clean_synthesis())

    assert report["passed"] is False
    assert "computed_financial_consistency" in _checks(report)


def test_redline_check_allows_derived_financial_values_from_object_source():
    dimensions = [
        _dimension(
            "business_model",
            4,
            [
                _evidence(
                    "派生财务判断",
                    "两条高贡献产品合计贡献2000万,净贡献率约22.5%",
                    "computed",
                    "financial_facts.product_lines",
                )
            ],
        )
    ]

    report = run_redline_check(
        dimensions,
        None,
        financial_facts=CHENGXU_FINANCIAL_FACTS,
        source_corpora=SOURCE_CORPORA,
        scope="single",
    )

    assert report["passed"] is True


def test_redline_check_skips_diagnosis_intake_paths_in_computed_financial_source():
    dimensions = [
        _dimension(
            "finance",
            6,
            [
                _evidence(
                    "现金跑道结合收入趋势判断",
                    "现金跑道15个月,收入趋势转平",
                    "computed",
                    "financial_facts.cash_runway_months, diagnosis_intake.company.revenue_trend",
                )
            ],
        )
    ]

    report = run_redline_check(
        dimensions,
        None,
        financial_facts=CHENGXU_FINANCIAL_FACTS,
        source_corpora=SOURCE_CORPORA,
        scope="single",
    )

    assert report["passed"] is True


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


def test_redline_check_catches_overlong_synthesis_headline():
    synthesis = deepcopy(_clean_synthesis())
    synthesis["headline"] = "这是一个明显超过三十个字符并且会把封面标题位置挤坏的报告标题必须拦截"

    report = _run(_clean_dimension_outputs(), synthesis)

    assert report["passed"] is False
    assert "synthesis_headline" in _checks(report)


def test_redline_check_catches_loss_hallucination_for_profitable_product_line():
    dimensions = [
        _dimension("market", 6, [_evidence("市场趋势", "定性", "client_provided", "survey.market")]),
        _dimension("competition", 6, [_evidence("竞争态势", "定性", "client_provided", "survey.competition")]),
        _dimension("business_model", 4, [_evidence("模式判断", "定性", "client_provided", "survey.business_model")]),
        _dimension("capability", 5, [_evidence("能力判断", "定性", "client_provided", "survey.capability")]),
        _dimension("finance", 3, [_evidence("财务判断", "定性", "client_provided", "survey.finance")]),
    ]
    dimensions[4]["reasoning_chain"][0] = "美容仪和联名礼盒都是亏损产品线,需要压低评分"

    report = run_redline_check(
        dimensions,
        _clean_synthesis(),
        financial_facts=CHENGXU_FINANCIAL_FACTS,
        source_corpora=SOURCE_CORPORA,
    )

    assert report["passed"] is False
    assert "product_loss_consistency" in _checks(report)
    assert any("美容仪" in failure["reason"] for failure in report["failures"])
    assert any("联名礼盒" in failure["reason"] for failure in report["failures"])


def test_redline_check_catches_loss_hallucination_inside_evidence():
    dimensions = [
        _dimension("business_model", 4, [
            _evidence(
                "洁面仪亏损说明模式有问题",
                "美容仪和联名礼盒也在亏损",
                "computed",
                "financial_facts.product_lines",
            )
        ])
    ]

    report = run_redline_check(
        dimensions,
        None,
        financial_facts=CHENGXU_FINANCIAL_FACTS,
        source_corpora=SOURCE_CORPORA,
        scope="single",
    )

    assert report["passed"] is False
    assert "product_loss_consistency" in _checks(report)
    assert any("洁面仪" in failure["reason"] for failure in report["failures"])
    assert any("美容仪" in failure["reason"] for failure in report["failures"])
    assert any("联名礼盒" in failure["reason"] for failure in report["failures"])


def test_redline_check_catches_degradation_missing_plus_not_in_availability_map():
    dimensions = _clean_dimension_outputs()
    dimensions[2]["degradation"]["missing_plus"] = ["品牌建设能力"]

    report = run_redline_check(
        dimensions,
        _clean_synthesis(),
        financial_facts=FINANCIAL_FACTS,
        source_corpora=SOURCE_CORPORA,
        availability_map={"plus_missing": ["business_model.revenue_mix"]},
    )

    assert report["passed"] is False
    assert "degradation_missing_plus" in _checks(report)
    assert "品牌建设能力" in report["failures"][0]["reason"]


def test_redline_check_catches_cross_dimension_missing_plus_item():
    dimensions = _clean_dimension_outputs()
    dimensions[1]["degradation"]["missing_plus"] = ["business_model.revenue_mix"]

    report = run_redline_check(
        dimensions,
        _clean_synthesis(),
        financial_facts=FINANCIAL_FACTS,
        source_corpora=SOURCE_CORPORA,
        availability_map={"plus_missing": ["business_model.revenue_mix"]},
    )

    assert report["passed"] is False
    assert "degradation_missing_plus" in _checks(report)
    assert "competition" in report["failures"][0]["reason"]
    assert "business_model.revenue_mix" in report["failures"][0]["reason"]


def test_redline_check_catches_source_markers_in_reasoning_chain():
    dimensions = _clean_dimension_outputs()
    dimensions[1]["reasoning_chain"][0] = (
        "竞争格局高度内卷(source_url: finance.sina.com.cn/tech/roll/2025-09-25)"
    )

    report = _run(dimensions, _clean_synthesis())

    assert report["passed"] is False
    assert "reasoning_chain_source_leak" in _checks(report)


def test_redline_check_catches_diagnosis_intake_mislabelled_as_computed():
    dimensions = _clean_dimension_outputs()
    dimensions[3]["evidence"][0] = _evidence(
        "渠道运营能力来自问卷",
        "强",
        "computed",
        "diagnosis_intake.capability.function_strength",
    )

    report = _run(dimensions, _clean_synthesis())

    assert report["passed"] is False
    assert "evidence_source_type_mapping" in _checks(report)
def test_redline_check_normalizes_external_source_url_prefixes():
    dimensions = _clean_dimension_outputs()
    dimensions[1]["evidence"][0]["source"] = (
        "[https://www.ceramicschina.com/PG_ViewNews_128452/]"
        "(https://www.ceramicschina.com/PG_ViewNews_128452/)"
    )

    report = _run(dimensions, _clean_synthesis())

    assert report["passed"] is True


def test_redline_check_accepts_comma_separated_external_sources():
    source_corpora = {
        "market": [
            {
                "claim": "家用美容仪市场增长",
                "value": "300亿",
                "source_url": "21jingji.com/article/20240121",
                "source_tier": "可信二手",
            },
            {
                "claim": "射频美容仪监管延期",
                "value": "2026年4月",
                "source_url": "industrysourcing.cn/article/463883",
                "source_tier": "可信二手",
            },
        ],
        "competition": [],
    }
    dimensions = [
        _dimension(
            "market",
            6,
            [
                _evidence(
                    "市场与监管共同影响",
                    "2025年约300亿,2026年4月监管大限",
                    "verified",
                    "https://www.21jingji.com/article/20240121, https://industrysourcing.cn/article/463883/",
                )
            ],
        )
    ]

    report = run_redline_check(
        dimensions,
        None,
        financial_facts=FINANCIAL_FACTS,
        source_corpora=source_corpora,
        scope="single",
    )

    assert report["passed"] is True
