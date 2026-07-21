from analysis import assemble_fact_base
from analysis.dimensions import analyze_competition
from finance import calculate_financial_facts


SOURCE_CORPUS_COMPETITION = [
    {
        "claim": "高端市场由欧美品牌(Kohler、汉斯格雅、Grohe、Moen)主导,靠工程、设计、保固、专利建立壁垒",
        "value": "定性,高端标杆",
        "source_url": "hansgrohe-usa.com;kohler.com",
        "source_tier": "可信二手",
    },
    {
        "claim": "浙江淋浴房出口量额全国第一(约32%/29%),但出口均价仅为全国平均的65.9%",
        "value": "出口第一但均价仅65.9%",
        "source_url": "ceramicschina.com/PG_ViewNews_128452",
        "source_tier": "可信二手",
    },
]


def _yonghui_fact_base():
    financial_facts = calculate_financial_facts(
        product_lines=[
            {"name": "淋浴隔断五金", "revenue": 6800, "total_cost": 5640},
            {"name": "法兰/排水配件", "revenue": 4200, "total_cost": 4610},
        ],
        customers=[
            {"name": "北美A", "pct": 35},
            {"name": "北美B", "pct": 20},
            {"name": "欧洲C", "pct": 10},
            {"name": "散客", "pct": 35},
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
        "competition": {
            "competitors": [
                "浙江同省淋浴房出口同行(低价走量)",
                "中山中高端淋浴房厂(雅立、玫瑰岛等)",
                "欧美高端品牌(Kohler、汉斯格雅,主要在高端工程)",
            ],
            "customer_values": ["价格", "交付稳定性", "可定制化", "认证齐全度"],
            "self_scores": {
                "价格": "强(低)",
                "交付稳定": "强",
                "定制能力": "中",
                "品牌": "弱",
                "认证齐全": "强",
            },
            "unique_assets": [
                "北美主要建材连锁的合格供应商认证",
                "欧盟CE/REACH等出口认证齐全",
                "与北美大客户7年以上合作、定制化适配经验",
                "稳定大批量交付能力",
            ],
        },
        "availability_map": {
            "plus_present": ["competition.self_scores", "competition.unique_assets"],
            "plus_missing": [],
        },
    }
    return assemble_fact_base(intake, financial_facts)


def test_competition_dimension_returns_required_schema_with_reversal():
    fact_base = _yonghui_fact_base()

    def fake_llm(system_prompt, user_prompt):
        assert "波特五力 + 蓝海客户价值曲线" in user_prompt
        assert "source_corpus" in user_prompt
        assert "unique_assets" in user_prompt
        return {
            "dimension": "competition",
            "framework": ["波特五力 + 蓝海客户价值曲线"],
            "core_judgment": "你不该继续只做低价出口,认证和交付才是差异化入口",
            "reasoning_chain": [
                "浙江出口同行普遍以低价走量竞争,价格维度很难形成长期优势",
                "客户同时看重交付稳定性、可定制化和认证齐全度,这让价值曲线不只由价格决定",
                "甬辉在认证齐全和稳定交付上有真实资产,应把竞争从低价转向合规交付壁垒",
            ],
            "evidence": [
                {
                    "claim": "甬辉具备北美合格供应商认证和欧盟出口认证",
                    "value": "认证齐全",
                    "benchmark": "客户提供的 unique_assets",
                    "source_type": "client_provided",
                    "source": "diagnosis_intake.competition.unique_assets",
                },
                {
                    "claim": "浙江出口量额领先但均价低于全国平均",
                    "value": "出口第一但均价仅65.9%",
                    "benchmark": "可信二手报告数据",
                    "source_type": "verified",
                    "source": "ceramicschina.com/PG_ViewNews_128452",
                },
            ],
            "reversal_candidate": {
                "naive_reading": "前三大客户集中度高,说明甬辉过度依赖大客户",
                "reframe": "若认证、定制适配和多年合作绑定成立,大客户依赖也是高切换成本壁垒",
                "mechanism": "北美合格供应商认证、7年以上合作、定制化适配和稳定大批量交付共同提高客户切换成本",
                "falsifier": "若大客户正在询价竞品、认证已被同行普遍获得、合同可随时切换,则该反转不成立",
                "confidence": 0.7,
                "status": "needs_human_falsifier_check",
                "depends_on": ["competition.unique_assets", "financial_facts.customer_concentration"],
            },
            "score": {
                "value": 6,
                "label": "亚健康",
                "rubric_basis": "低价竞争压力明显,但认证和交付资产提供差异化机会",
            },
            "degradation": {
                "degraded": False,
                "missing_plus": [],
                "upgrade_hook": "",
            },
            "strength": "high",
            "open_questions": ["北美大客户是否存在竞品询价或认证替代方案"],
        }

    result = analyze_competition(fact_base, SOURCE_CORPUS_COMPETITION, llm_call=fake_llm)

    assert result["dimension"] == "competition"
    assert result["reversal_candidate"]["status"] == "needs_human_falsifier_check"
    assert result["evidence"][0]["source_type"] == "client_provided"
