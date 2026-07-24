from finance import calculate_financial_facts


def test_calculate_financial_facts_for_sample_case():
    facts = calculate_financial_facts(
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

    loss_lines = [line for line in facts["product_lines"] if line["is_loss"]]

    assert facts["tier"] == "full"
    assert loss_lines == [
        {
            "name": "法兰/排水配件",
            "full_cost_net": -410.0,
            "revenue": 4200.0,
            "revenue_share": 0.226,
            "unit": "万元",
            "is_loss": True,
        }
    ]
    assert facts["customer_concentration"]["top3_pct"] == 65.0
    assert facts["cash_runway_months"] == 1.6
    assert facts["cash_position"] == {
        "cash": 1180.0,
        "monthly_fixed": 720.0,
        "runway_months": 1.6,
        "unit": "万元",
    }
    assert facts["ar"]["releasable_at_60days"] == 1892


def test_calculate_financial_facts_caps_ar_release_at_zero_when_days_under_60():
    facts = calculate_financial_facts(
        product_lines=[
            {"name": "高速电吹风", "revenue": 8000, "total_cost": 6200},
            {"name": "洁面仪", "revenue": 4500, "total_cost": 3500},
            {"name": "美容仪", "revenue": 3500, "total_cost": 2900},
            {"name": "配套耗材", "revenue": 2000, "total_cost": 1000},
            {"name": "联名礼盒", "revenue": 1200, "total_cost": 1000},
        ],
        customers=[
            {"name": "经销商A", "pct": 2.5},
            {"name": "经销商B", "pct": 1.5},
            {"name": "经销商C", "pct": 1},
            {"name": "C端散客", "pct": 95},
        ],
        cash=6000,
        monthly_fixed=400,
        ar_balance=1400,
        ar_days=28,
    )

    product_lines = {line["name"]: line for line in facts["product_lines"]}

    assert product_lines["美容仪"]["full_cost_net"] == 600.0
    assert product_lines["美容仪"]["is_loss"] is False
    assert product_lines["联名礼盒"]["full_cost_net"] == 200.0
    assert product_lines["联名礼盒"]["is_loss"] is False
    assert facts["ar"]["releasable_at_60days"] == 0


def test_calculate_financial_facts_omits_cash_runway_when_basic_inputs_are_missing():
    facts = calculate_financial_facts(
        product_lines=None,
        customers=None,
        cash=None,
        monthly_fixed=None,
        ar_balance=None,
        ar_days=None,
    )

    assert facts["tier"] == "basic_only"
    assert facts["cash_runway_months"] is None
    assert facts["cash_position"] is None
