from finance import calculate_financial_facts


def test_calculate_financial_facts_for_sample_case():
    facts = calculate_financial_facts(
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
    assert facts["ar"]["releasable_at_60days"] == 1892


def test_calculate_financial_facts_caps_ar_release_at_zero_when_days_under_60():
    facts = calculate_financial_facts(
        product_lines=[
            {"name": "高速电吹风", "revenue": 8000, "direct_cost": 4000, "allocated": 2200},
            {"name": "洁面仪", "revenue": 4500, "direct_cost": 2000, "allocated": 1500},
            {"name": "美容仪", "revenue": 3500, "direct_cost": 1400, "allocated": 1500},
            {"name": "配套耗材", "revenue": 2000, "direct_cost": 600, "allocated": 400},
            {"name": "联名礼盒", "revenue": 1200, "direct_cost": 700, "allocated": 300},
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
