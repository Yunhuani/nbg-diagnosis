from analysis import analyze_business_model, assemble_fact_base
from finance import calculate_financial_facts


def test_business_model_dimension_returns_required_schema():
    financial_facts = calculate_financial_facts(
        product_lines=[
            {"name": "淋浴隔断五金", "revenue": 6800, "total_cost": 5640},
            {"name": "法兰/排水配件", "revenue": 4200, "total_cost": 4610},
            {"name": "浴室置物架", "revenue": 3500, "total_cost": 2830},
            {"name": "龙头配件", "revenue": 2600, "total_cost": 2082},
            {"name": "定制小单/杂项", "revenue": 1500, "total_cost": 1365},
        ],
        customers=[
            {"name": "北美A", "pct": 35},
            {"name": "北美B", "pct": 20},
            {"name": "欧洲C", "pct": 10},
            {"name": "中东D", "pct": 8},
            {"name": "散客", "pct": 27},
        ],
        cash=1180,
        monthly_fixed=720,
        ar_balance=4960,
        ar_days=97,
    )
    intake = {
        "company": {
            "name": "甬辉",
            "industry_sub": "浙江卫浴五金出口商",
            "region": "欧美及中东",
        },
        "business_model": {
            "revenue_sources": "主营淋浴隔断五金、法兰配件、浴室置物架、龙头配件等",
            "how_earn_retain": "靠 OEM 代工、稳定交付和老客户复购赚钱",
            "revenue_mix": None,
        },
        "availability_map": {
            "plus_present": ["finance.product_lines", "finance.customers", "finance.ar"],
            "plus_missing": ["business_model.revenue_mix"],
        },
    }
    fact_base = assemble_fact_base(intake, financial_facts)

    def fake_llm(system_prompt, user_prompt):
        assert "泽思 NBG 五维诊断分析引擎" in system_prompt
        assert "商业模式画布" in user_prompt
        assert "【产品线盈亏事实,代码计算,只能引用不得推翻】" in user_prompt
        assert "淋浴隔断五金=盈利" in user_prompt
        assert "financial_facts.cash_position.cash" in user_prompt
        assert "financial_facts.cash_position.monthly_fixed" in user_prompt
        assert "financial_facts.cash_runway_months" in user_prompt
        assert "法兰/排水配件=亏损" in user_prompt
        assert "浴室置物架=盈利" in user_prompt
        assert "龙头配件=盈利" in user_prompt
        assert "定制小单/杂项=盈利" in user_prompt
        assert "把盈利产品线说成亏损=严重错误" in user_prompt
        assert "法兰/排水配件" in user_prompt
        return {
            "dimension": "business_model",
            "framework": ["商业模式画布"],
            "core_judgment": "你靠 OEM 保住了量，却让亏损产品侵蚀了模式",
            "reasoning_chain": [
                "主营收入来自卫浴五金 OEM 与老客户复购",
                "OEM 模式把议价空间压缩到成本和交付效率上",
                "法兰/排水配件全成本净贡献为 -410 万，说明部分收入没有转化为利润",
            ],
            "evidence": [
                {
                    "claim": "法兰/排水配件是亏损线",
                    "value": "-410 万",
                    "benchmark": "财务模块 ground truth",
                    "source_type": "computed",
                    "source": "financial_facts.product_lines",
                }
            ],
            "reversal_candidate": None,
            "score": {
                "value": 4,
                "label": "警告",
                "rubric_basis": "存在亏损产品线，且商业模式依赖 OEM 代工的成本效率",
            },
            "degradation": {
                "degraded": True,
                "missing_plus": ["business_model.revenue_mix"],
                "upgrade_hook": "提供各产品/渠道收入占比，可进一步判断模式脆弱环节",
            },
            "strength": "high",
            "open_questions": ["亏损产品线是否承担客户绑定或订单入口作用"],
        }

    result = analyze_business_model(fact_base, llm_call=fake_llm)

    assert result["dimension"] == "business_model"
    assert result["core_judgment"] != "商业模式分析"
    assert result["score"]["value"] == 4
    assert result["evidence"][0]["source_type"] == "computed"


def test_business_model_profit_loss_anchor_is_dynamic_per_case():
    financial_facts = calculate_financial_facts(
        product_lines=[
            {"name": "高速电吹风", "revenue": 8000, "total_cost": 6200},
            {"name": "洁面仪", "revenue": 4500, "total_cost": 3500},
            {"name": "美容仪", "revenue": 3500, "total_cost": 2900},
        ],
        customers=[{"name": "C端散客", "pct": 100}],
        cash=6000,
        monthly_fixed=400,
        ar_balance=1400,
        ar_days=28,
    )
    intake = {
        "company": {"name": "橙序", "industry_sub": "国产个护小家电", "region": "国内"},
        "business_model": {
            "revenue_sources": "高速电吹风、洁面仪、美容仪",
            "how_earn_retain": "靠平台投流获客",
            "revenue_mix": None,
        },
        "availability_map": {
            "plus_present": ["finance.product_lines"],
            "plus_missing": ["business_model.revenue_mix"],
        },
    }
    fact_base = assemble_fact_base(intake, financial_facts)

    def fake_llm(_system_prompt, user_prompt):
        assert "高速电吹风=盈利" in user_prompt
        assert "洁面仪=盈利" in user_prompt
        assert "美容仪=盈利" in user_prompt
        assert "淋浴隔断五金" not in user_prompt
        assert "法兰/排水配件" not in user_prompt
        return {
            "dimension": "business_model",
            "framework": ["商业模式画布"],
            "core_judgment": "你靠投流拉动销量,但收入结构还没有形成复购闭环",
            "reasoning_chain": [
                "高速电吹风、洁面仪和美容仪均为盈利产品线",
                "盈利事实说明问题不是单线亏损,而是增长来源过度依赖投流",
                "商业模式需要识别复购与留存环节是否能承接获客成本",
            ],
            "evidence": [
                {
                    "claim": "三条产品线均为盈利",
                    "value": "盈利",
                    "benchmark": "产品线盈亏事实清单",
                    "source_type": "computed",
                    "source": "financial_facts.product_lines",
                }
            ],
            "reversal_candidate": None,
            "score": {"value": 5, "label": "亚健康", "rubric_basis": "增长依赖投流但产品线未亏损"},
            "degradation": {
                "degraded": True,
                "missing_plus": ["business_model.revenue_mix"],
                "upgrade_hook": "提供收入占比可判断复购结构",
            },
            "strength": "medium",
            "open_questions": [],
        }

    result = analyze_business_model(fact_base, llm_call=fake_llm)

    assert result["dimension"] == "business_model"
