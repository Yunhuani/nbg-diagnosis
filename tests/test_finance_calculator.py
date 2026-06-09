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
