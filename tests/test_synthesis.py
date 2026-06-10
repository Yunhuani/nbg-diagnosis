from analysis.synthesis import calculate_overall_score, synthesize_diagnosis


def _dimension_output(dimension, score, core_judgment, reversal_candidate=None):
    return {
        "dimension": dimension,
        "framework": ["测试框架"],
        "core_judgment": core_judgment,
        "reasoning_chain": ["第1环", "第2环", "第3环"],
        "evidence": [
            {
                "claim": f"{dimension} 关键证据",
                "value": "",
                "benchmark": "",
                "source_type": "client_provided",
                "source": "test",
            }
        ],
        "reversal_candidate": reversal_candidate,
        "score": {
            "value": score,
            "label": "亚健康" if score >= 5 else "警告",
            "rubric_basis": "测试分数",
        },
        "degradation": {
            "degraded": False,
            "missing_plus": [],
            "upgrade_hook": "",
        },
        "strength": "high",
        "open_questions": [],
    }


def test_synthesis_returns_schema_and_references_findings_ids():
    dimensions = [
        _dimension_output("market", 6, "市场有升级窗口"),
        _dimension_output(
            "competition",
            6,
            "大客户依赖可能是壁垒",
            {
                "naive_reading": "客户集中度65%是风险",
                "reframe": "深度绑定形成切换成本",
                "mechanism": "认证、合作年限、定制适配和稳定交付共同绑定客户",
                "falsifier": "大客户正在询价竞品或认证被同行普遍获得",
                "confidence": 0.7,
                "status": "needs_human_falsifier_check",
                "depends_on": ["competition.unique_assets"],
            },
        ),
        _dimension_output("business_model", 4, "全品类代工与成本结构错配"),
        _dimension_output("capability", 5, "营销和财务管理能力偏弱"),
        _dimension_output("finance", 3, "现金安全边际进入警告区"),
    ]
    score_summary = calculate_overall_score(dimensions)

    def fake_llm(system_prompt, user_prompt):
        assert "overall_score" in user_prompt
        assert "findings[] 是 finding_id 的唯一户口" in system_prompt
        return {
            "findings": [
                {
                    "id": "F01",
                    "dimension": "finance",
                    "statement": "现金安全边际进入警告区",
                    "type": "judgment",
                    "strength": "high",
                    "quant_value": "1.6个月",
                },
                {
                    "id": "F02",
                    "dimension": "competition",
                    "statement": "客户集中度65%也是认证和定制绑定下的壁垒候选",
                    "type": "reversal",
                    "strength": "high",
                    "quant_value": "65%",
                },
            ],
            "overall_judgment": "甬辉不是没有市场机会,而是外部窗口尚可、内部模式和财务承压",
            "overall_score": score_summary["overall_score"],
            "score_label": score_summary["score_label"],
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
                    "mechanism": "认证、合作年限、定制适配和稳定交付共同绑定客户",
                    "falsifier": "大客户正在询价竞品或认证被同行普遍获得",
                    "confidence": 0.7,
                    "status": "needs_human_falsifier_check",
                    "depends_on": ["competition.unique_assets"],
                }
            ],
            "three_key_findings": [
                {
                    "finding_id": "F01",
                    "title": "现金安全边际已经进入警告区",
                    "why_surprising": "订单不少不等于现金安全",
                }
            ],
            "consistency_flags": [],
            "transition_to_solution": "先止住财务失血,再围绕高端机会重排增长方向",
        }

    result = synthesize_diagnosis(dimensions, llm_call=fake_llm)
    finding_ids = {item["id"] for item in result["findings"]}

    assert result["overall_score"] == 4.8
    assert result["score_label"] == "警告"
    assert result["three_key_findings"][0]["finding_id"] in finding_ids
