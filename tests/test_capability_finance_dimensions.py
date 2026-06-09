import pytest

from analysis import assemble_fact_base
from analysis.dimensions import analyze_capability, analyze_finance
from finance import calculate_financial_facts


def _yonghui_fact_base():
    financial_facts = calculate_financial_facts(
        product_lines=[
            {"name": "淋浴隔断五金", "revenue": 6800, "direct_cost": 4760, "allocated": 880},
            {"name": "法兰/排水配件", "revenue": 4200, "direct_cost": 3990, "allocated": 620},
            {"name": "浴室置物架", "revenue": 3500, "direct_cost": 2380, "allocated": 450},
            {"name": "龙头配件", "revenue": 2600, "direct_cost": 1742, "allocated": 340},
            {"name": "定制小单/杂项", "revenue": 1500, "direct_cost": 1155, "allocated": 210},
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
        "capability": {
            "team_structure": {
                "production": "强",
                "supply_chain": "中",
                "sales": "中",
                "marketing": "弱",
                "finance_management": "弱",
            },
            "function_strength": {
                "product": "中",
                "supply_chain": "中",
                "channel": "中",
                "marketing": "弱",
                "finance_management": "弱",
            },
            "digital_keyperson": None,
        },
        "availability_map": {
            "plus_present": ["finance.product_lines", "finance.customers", "finance.ar"],
            "plus_missing": ["capability.digital_keyperson"],
        },
    }
    return assemble_fact_base(intake, financial_facts)


def test_capability_dimension_returns_required_schema():
    fact_base = _yonghui_fact_base()

    def fake_llm(system_prompt, user_prompt):
        assert "能力-资源矩阵" in user_prompt
        assert "capability" in user_prompt
        return {
            "dimension": "capability",
            "framework": ["能力-资源矩阵"],
            "core_judgment": "你的交付能力还能撑订单,但营销与财务管理拖住增长",
            "reasoning_chain": [
                "生产与供应链能力较强,说明现有组织更擅长履约交付",
                "营销和财务管理偏弱,增长所需的获客与经营控制能力不足",
                "越依赖 OEM 老客户,越需要补足主动经营能力,否则增长只能跟着客户走",
            ],
            "evidence": [
                {
                    "claim": "营销与财务管理自评偏弱",
                    "value": "弱",
                    "benchmark": "客户问卷能力自评",
                    "source_type": "client_provided",
                    "source": "diagnosis_intake.capability.function_strength",
                }
            ],
            "reversal_candidate": None,
            "score": {
                "value": 5,
                "label": "亚健康",
                "rubric_basis": "交付能力尚可,但营销与财务管理短板限制增长主动性",
            },
            "degradation": {
                "degraded": True,
                "missing_plus": ["capability.digital_keyperson"],
                "upgrade_hook": "补充数字化程度与关键人依赖,可更精确判断能力瓶颈",
            },
            "strength": "medium",
            "open_questions": ["增长短板应优先自建、外包还是寻找渠道伙伴"],
        }

    result = analyze_capability(fact_base, llm_call=fake_llm)

    assert result["dimension"] == "capability"
    assert result["framework"] == ["能力-资源矩阵"]
    assert result["degradation"]["degraded"] is True


def test_finance_dimension_returns_required_schema_and_respects_score_cap():
    fact_base = _yonghui_fact_base()

    def fake_llm(system_prompt, user_prompt):
        assert "解读,不计算" in user_prompt
        assert "score.value 必须 ≤ 3" in user_prompt
        return {
            "dimension": "finance",
            "framework": ["杜邦分析 + 全成本作业法 + 营运资金周期模型"],
            "core_judgment": "你的现金安全边际已经被亏损线和集中度同时压低",
            "reasoning_chain": [
                "现金跑道只有 1.6 个月,说明财务缓冲很薄",
                "法兰/排水配件年亏 -410 万且收入占比 0.226,说明亏损不是边角问题",
                "前三大客户 65% 让现金回收和议价压力集中,转型容错空间被压到警告区",
            ],
            "evidence": [
                {
                    "claim": "现金跑道低于 2 个月",
                    "value": "1.6 个月",
                    "benchmark": "财务硬规则: <2 个月评分上限为 3",
                    "source_type": "computed",
                    "source": "financial_facts.cash_runway_months",
                },
                {
                    "claim": "法兰/排水配件为亏损线且收入占比超过 15%",
                    "value": "-410 万; revenue_share 0.226",
                    "benchmark": "财务硬规则: 亏损线收入占比 >0.15 评分上限为 4",
                    "source_type": "computed",
                    "source": "financial_facts.product_lines",
                },
            ],
            "reversal_candidate": None,
            "score": {
                "value": 3,
                "label": "警告",
                "rubric_basis": "现金跑道 <2 个月触发最严格评分上限",
            },
            "degradation": {
                "degraded": False,
                "missing_plus": [],
                "upgrade_hook": "",
            },
            "strength": "high",
            "open_questions": ["亏损线是否承担客户绑定作用,以及能否在不丢客户的前提下止血"],
        }

    result = analyze_finance(fact_base, llm_call=fake_llm)

    assert result["dimension"] == "finance"
    assert result["score"]["value"] == 3
    assert result["evidence"][0]["source_type"] == "computed"


def test_finance_dimension_rejects_score_above_hard_cap():
    fact_base = _yonghui_fact_base()

    def fake_llm(system_prompt, user_prompt):
        return {
            "dimension": "finance",
            "framework": ["杜邦分析 + 全成本作业法 + 营运资金周期模型"],
            "core_judgment": "你的现金安全边际已经进入警告区",
            "reasoning_chain": [
                "现金跑道只有 1.6 个月",
                "亏损线收入占比超过 15%",
                "客户集中度超过 60%",
            ],
            "evidence": [
                {
                    "claim": "现金跑道低于 2 个月",
                    "value": "1.6 个月",
                    "benchmark": "财务硬规则",
                    "source_type": "computed",
                    "source": "financial_facts.cash_runway_months",
                }
            ],
            "reversal_candidate": None,
            "score": {
                "value": 4,
                "label": "警告",
                "rubric_basis": "故意给高于现金跑道硬规则上限的分数",
            },
            "degradation": {
                "degraded": False,
                "missing_plus": [],
                "upgrade_hook": "",
            },
            "strength": "high",
            "open_questions": [],
        }

    with pytest.raises(ValueError, match="finance score.value must be <= 3"):
        analyze_finance(fact_base, llm_call=fake_llm)
