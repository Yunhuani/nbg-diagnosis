from __future__ import annotations

import argparse
import json

from analysis import (
    assemble_fact_base,
    calculate_overall_score,
    run_redline_check,
    synthesize_diagnosis,
)
from analysis.dimensions import (
    analyze_business_model,
    analyze_capability,
    analyze_competition,
    analyze_finance,
    analyze_market,
)
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
    {
        "claim": "市场持续向高值产品迁移,无框与walk-in抢占有框份额",
        "value": "定性趋势",
        "source_url": "indexbox.io/blog/shower-enclosures-market-to-2035",
        "source_tier": "可信二手",
    },
    {
        "claim": "中东GCC需求集中在高端酒店、豪宅、政府基建",
        "value": "定性,高端导向",
        "source_url": "indexbox.io/blog/shower-enclosures-market-to-2035",
        "source_tier": "仅线索",
    },
    {
        "claim": "美国淋浴隔断市场稳定增长",
        "value": "$3.8B(2022)→$5.15B(2028),CAGR 5.2%",
        "source_url": "researchandmarkets.com/report/shower-enclosure",
        "source_tier": "可信二手",
    },
    {
        "claim": "五金配件趋向暖色金属饰面,成为差异化点",
        "value": "定性趋势",
        "source_url": "heirglass.com/top-glass-shower-design-trends-2026",
        "source_tier": "仅线索",
    },
]

SOURCE_CORPUS_COMPETITION = [
    {
        "claim": "高端市场由欧美品牌(Kohler、汉斯格雅、Grohe、Moen)主导,靠工程、设计、保固、专利建立壁垒",
        "value": "定性,高端标杆",
        "source_url": "hansgrohe-usa.com;kohler.com",
        "source_tier": "可信二手",
    },
    {
        "claim": "中国卫浴五金分高/中/低三层:高端欧美品牌、中端国产品牌、低端国内小厂拼价格",
        "value": "三层结构",
        "source_url": "chyxx.com",
        "source_tier": "可信二手",
    },
    {
        "claim": "中山淋浴房占全国中高端约70%、出口约40%(雅立、玫瑰岛等)",
        "value": "中高端70%/出口40%",
        "source_url": "zhihu.com/p/624308443",
        "source_tier": "仅线索",
    },
    {
        "claim": "浙江淋浴房出口量额全国第一(约32%/29%),但出口均价仅为全国平均的65.9%",
        "value": "出口第一但均价仅65.9%",
        "source_url": "ceramicschina.com/PG_ViewNews_128452",
        "source_tier": "可信二手",
    },
    {
        "claim": "厦门是卫浴五金OEM代工核心基地(路达、瑞尔特、松霖、建霖)",
        "value": "定性,OEM集群",
        "source_url": "zhihu.com/p/624308443",
        "source_tier": "仅线索",
    },
    {
        "claim": "中国卫浴五金出口年增约8-10%,行业整体长期中低端",
        "value": "出口增速8-10%",
        "source_url": "jc001.cn",
        "source_tier": "仅线索",
    },
]

SOURCE_CORPORA = {
    "market": SOURCE_CORPUS_MARKET,
    "competition": SOURCE_CORPUS_COMPETITION,
}


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
        "market": {
            "home_market": "欧美及中东",
            "expansion_intent": "中东高端工程与无框淋浴隔断配套五金",
            "demand_shift": None,
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
                "competition.self_scores",
                "competition.unique_assets",
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
    "competition": lambda fact_base: analyze_competition(
        fact_base,
        SOURCE_CORPUS_COMPETITION,
    ),
    "finance": analyze_finance,
    "market": lambda fact_base: analyze_market(fact_base, SOURCE_CORPUS_MARKET),
}

SYNTHESIS_DIMENSION_ORDER = [
    "market",
    "competition",
    "business_model",
    "capability",
    "finance",
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real DeepSeek dimension call.")
    parser.add_argument(
        "dimension",
        choices=sorted([*ANALYZERS, "synthesis"]),
        help="Dimension to run, or synthesis to run all five dimensions then synthesize.",
    )
    args = parser.parse_args()

    fact_base = build_yonghui_fact_base()
    print("=== INPUT FACT BASE ===")
    print(json.dumps(fact_base, ensure_ascii=False, indent=2))

    if args.dimension == "synthesis":
        dimension_outputs = []
        for dimension in SYNTHESIS_DIMENSION_ORDER:
            print(f"\n=== DEEPSEEK {dimension} OUTPUT ===")
            output = ANALYZERS[dimension](fact_base)
            dimension_outputs.append(output)
            print(json.dumps(output, ensure_ascii=False, indent=2))

        score_summary = calculate_overall_score(dimension_outputs)
        print("\n=== CODE-COMPUTED SCORE SUMMARY ===")
        print(json.dumps(score_summary, ensure_ascii=False, indent=2))
        print("\n=== DEEPSEEK SYNTHESIS OUTPUT ===")
        synthesis = synthesize_diagnosis(dimension_outputs)
        print(json.dumps(synthesis, ensure_ascii=False, indent=2))
        print("\n=== REDLINE CHECK REPORT ===")
        report = run_redline_check(
            dimension_outputs,
            synthesis,
            financial_facts=fact_base["financial_facts"],
            source_corpora=SOURCE_CORPORA,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    print(f"\n=== DEEPSEEK {args.dimension} OUTPUT ===")
    result = ANALYZERS[args.dimension](fact_base)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
