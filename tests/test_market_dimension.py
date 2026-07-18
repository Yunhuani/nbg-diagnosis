from analysis import assemble_fact_base
from analysis.dimensions import MARKET_PROMPT, analyze_market
from finance import calculate_financial_facts


SOURCE_CORPUS_MARKET = [
    {
        "claim": "全球淋浴隔断市场低到中个位数稳定增长",
        "value": "约4.2% CAGR(2026-2035)",
        "source_url": "indexbox.io/blog/shower-enclosures-market-to-2035",
        "source_tier": "可信二手",
    },
    {
        "claim": "无框淋浴隔断增速显著高于有框,是结构性升级方向",
        "value": "无框约7.4-8% CAGR,快于整体",
        "source_url": "verifiedmarketreports.com/product/shower-glass-door-market",
        "source_tier": "可信二手",
    },
]


def test_market_prompt_forbids_cross_dimension_missing_plus_fields():
    assert "不得照抄 availability_map.plus_missing 整个列表" in MARKET_PROMPT
    assert "competition.self_scores" in MARKET_PROMPT
    assert "competition.unique_assets" in MARKET_PROMPT
    assert "business_model.revenue_mix" in MARKET_PROMPT
    assert "degradation.missing_plus 必须是 []" in MARKET_PROMPT


def test_market_prompt_forbids_unsupported_opportunities_without_source_corpus():
    assert "source_corpus 为空" in MARKET_PROMPT
    assert "不得自行补充任何具体外部数字、地区、渠道、场景、品类或行业机会词" in MARKET_PROMPT
    assert "只能基于 diagnosis_intake 中客户明确提供的信息做结构性定性判断" in MARKET_PROMPT
    assert "客户可见表述不得出现" in MARKET_PROMPT
    assert "该机会方向可在方案深化阶段结合目标市场订单、渠道反馈与价格带数据进一步量化" in MARKET_PROMPT
    assert "不得伪装成有外部来源支持的事实" in MARKET_PROMPT


def _yonghui_fact_base():
    financial_facts = calculate_financial_facts(
        product_lines=[
            {"name": "淋浴隔断五金", "revenue": 6800, "direct_cost": 4760, "allocated": 880},
            {"name": "法兰/排水配件", "revenue": 4200, "direct_cost": 3990, "allocated": 620},
        ],
        customers=[
            {"name": "北美A", "pct": 35},
            {"name": "北美B", "pct": 20},
            {"name": "欧洲C", "pct": 10},
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
        "market": {
            "home_market": "欧美及中东",
            "expansion_intent": "中东高端工程与无框淋浴隔断配套五金",
            "demand_shift": None,
        },
        "availability_map": {
            "plus_present": ["finance.product_lines"],
            "plus_missing": ["market.demand_shift"],
        },
    }
    return assemble_fact_base(intake, financial_facts)


def test_market_dimension_returns_required_schema_with_source_corpus():
    fact_base = _yonghui_fact_base()

    def fake_llm(system_prompt, user_prompt):
        assert "MECE 机会拆解 + 波特行业分析" in user_prompt
        assert "source_corpus" in user_prompt
        assert "【产品线盈亏事实,代码计算,只能引用不得推翻】" in user_prompt
        assert "淋浴隔断五金=盈利" in user_prompt
        assert "法兰/排水配件=亏损" in user_prompt
        assert "verifiedmarketreports.com/product/shower-glass-door-market" in user_prompt
        return {
            "dimension": "market",
            "framework": ["MECE 机会拆解 + 波特行业分析"],
            "core_judgment": "你盯着通用五金价格战,却错过无框高值升级窗口",
            "reasoning_chain": [
                "整体淋浴隔断市场保持低到中个位数稳定增长",
                "无框淋浴隔断增速高于整体,说明增长正在从通用有框转向高值结构",
                "甬辉若只围绕通用五金接 OEM 订单,会错过更适配能力和利润空间的升级支线",
            ],
            "evidence": [
                {
                    "claim": "无框淋浴隔断增速显著高于整体",
                    "value": "无框约7.4-8% CAGR,快于整体",
                    "benchmark": "整体约4.2% CAGR",
                    "source_type": "verified",
                    "source": "verifiedmarketreports.com/product/shower-glass-door-market",
                },
                {
                    "claim": "甬辉当前品类与无框升级方向相关",
                    "value": "浙江卫浴五金出口商",
                    "benchmark": "客户填报品类",
                    "source_type": "client_provided",
                    "source": "diagnosis_intake.company.industry_sub",
                },
            ],
            "reversal_candidate": None,
            "score": {
                "value": 6,
                "label": "亚健康",
                "rubric_basis": "行业仍有增长窗口,但现有注意力可能偏向低值通用机会",
            },
            "degradation": {
                "degraded": True,
                "missing_plus": ["market.demand_shift"],
                "upgrade_hook": "补充客户感知的需求变化,可判断升级机会是否已在订单端出现",
            },
            "strength": "high",
            "open_questions": ["中东高端工程是否已有稳定询盘或样品反馈"],
        }

    result = analyze_market(fact_base, SOURCE_CORPUS_MARKET, llm_call=fake_llm)

    assert result["dimension"] == "market"
    assert result["framework"] == ["MECE 机会拆解 + 波特行业分析"]
    assert result["evidence"][0]["source_type"] == "verified"
