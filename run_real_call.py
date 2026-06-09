from __future__ import annotations

import argparse
import json

from analysis import assemble_fact_base
from analysis.dimensions import analyze_business_model, analyze_capability, analyze_finance
from finance import calculate_financial_facts


def build_yonghui_fact_base() -> dict:
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
            "revenue_band": "1亿-3亿元",
            "revenue_trend": "flat",
            "headcount_band": "100-300人",
            "channels": ["B端工程", "经销", "OEM"],
            "top_anxiety": "订单不少但利润越来越薄",
        },
        "business_model": {
            "revenue_sources": "主营淋浴隔断五金、法兰/排水配件、浴室置物架、龙头配件、定制小单/杂项",
            "how_earn_retain": "靠 OEM 代工、稳定交付和老客户复购赚钱",
            "revenue_mix": None,
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
            "plus_present": [
                "finance.product_lines",
                "finance.customers",
                "finance.ar",
            ],
            "plus_missing": [
                "business_model.revenue_mix",
                "capability.digital_keyperson",
            ],
        },
    }
    return assemble_fact_base(intake, financial_facts)


ANALYZERS = {
    "business_model": analyze_business_model,
    "capability": analyze_capability,
    "finance": analyze_finance,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real DeepSeek dimension call.")
    parser.add_argument(
        "dimension",
        choices=sorted(ANALYZERS),
        help="Dimension to run: business_model, capability, or finance.",
    )
    args = parser.parse_args()

    fact_base = build_yonghui_fact_base()
    print("=== INPUT FACT BASE ===")
    print(json.dumps(fact_base, ensure_ascii=False, indent=2))
    print(f"\n=== DEEPSEEK {args.dimension} OUTPUT ===")
    result = ANALYZERS[args.dimension](fact_base)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
