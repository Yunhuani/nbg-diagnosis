from __future__ import annotations

import argparse
import json
import subprocess
from copy import deepcopy
from pathlib import Path

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
from solution import generate_strategic_thesis


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

SOURCE_CORPUS_MARKET_B = [
    {
        "claim": "高速吹风告别高增长,2025上半年市场规模43.5亿、同比下滑10.5%(2024为+10.4%)",
        "value": "43.5亿,2025H1同比-10.5%",
        "source_url": "finance.sina.com.cn/tech/roll/2025-09-25",
        "source_tier": "可信二手",
    },
    {
        "claim": "高速吹风300元以下占比近80%,差异化卖点已变基础配置,高端溢价消解",
        "value": "<300元占比~80%",
        "source_url": "finance.sina.com.cn/tech/roll/2025-09-25",
        "source_tier": "可信二手",
    },
    {
        "claim": "家用美容仪市场约从2021年100亿增至2025年约300亿,但增速因监管骤降",
        "value": "~300亿(2025)",
        "source_url": "21jingji.com/article/20240121",
        "source_tier": "可信二手",
    },
    {
        "claim": "射频美容仪三类医疗器械监管延期至2026年4月实施,无注册证不得销售",
        "value": "2026年4月大限",
        "source_url": "industrysourcing.cn/article/463883",
        "source_tier": "可信二手",
    },
    {
        "claim": "美容电器市场国内品牌与飞利浦、松下等外资仍有品牌和销量差距",
        "value": "定性,国产偏弱",
        "source_url": "cninfo360.com",
        "source_tier": "仅线索",
    },
]

SOURCE_CORPUS_COMPETITION_B = [
    {
        "claim": "高速吹风2024上半年戴森线上份额暴跌至7%,徕芬占超60%",
        "value": "徕芬>60%,戴森7%",
        "source_url": "m.daqihao.com/articles/keji/202503/6439",
        "source_tier": "可信二手",
    },
    {
        "claim": "徕芬靠硬核电机技术连续三年(2023-2025)国内线上销量第一,反超戴森",
        "value": "连续三年国内第一",
        "source_url": "m.tech.china.com/redian/2026/0410",
        "source_tier": "可信二手",
    },
    {
        "claim": "京东平台高速吹风在售品牌近500个,飞科追觅美的海尔等全面入局,高度内卷",
        "value": "~500个品牌",
        "source_url": "finance.sina.com.cn/tech/roll/2025-09-25",
        "source_tier": "可信二手",
    },
    {
        "claim": "徕芬靠重营销崛起(2022-24投流超10亿),但暴露质量投诉,低价低质模式脆弱",
        "value": "投流>10亿,投诉超2000条",
        "source_url": "m.daqihao.com/articles/keji/202503/6439",
        "source_tier": "仅线索",
    },
    {
        "claim": "美容仪头部品牌(玛丽仙、AMIRO觅光)已获三类医疗器械证,具研发壁垒",
        "value": "头部已拿证",
        "source_url": "m.chinabgao.com/info/1254560",
        "source_tier": "可信二手",
    },
]

SOURCE_CORPORA = {
    "market": SOURCE_CORPUS_MARKET,
    "competition": SOURCE_CORPUS_COMPETITION,
}

SOURCE_CORPORA_BY_CASE = {
    "A": SOURCE_CORPORA,
    "B": {
        "market": SOURCE_CORPUS_MARKET_B,
        "competition": SOURCE_CORPUS_COMPETITION_B,
    },
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


def build_chengxu_fact_base() -> dict:
    financial_facts = calculate_financial_facts(
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

    intake = {
        "company": {
            "name": "橙序",
            "industry_sub": "国产个护小家电(美容个护电器)",
            "region": "国内(线上为主,全国)",
            "revenue_band": "1亿-3亿元",
            "revenue_trend": "flat(从高增长断崖式转平)",
            "headcount_band": "100-300人",
            "channels": ["抖音电商", "天猫", "京东", "线下集合店"],
            "top_anxiety": "增长停下来了,投流越来越贵,利润被营销吃光",
        },
        "business_model": {
            "revenue_sources": "高速电吹风、洁面仪、美容仪、配套耗材、联名礼盒",
            "how_earn_retain": "靠颜值设计+达人种草+平台投流获客,耗材复购沉淀利润",
            "revenue_mix": {
                "抖音": 0.45,
                "天猫": 0.30,
                "京东": 0.12,
                "线下": 0.13,
            },
        },
        "market": {
            "home_market": "国内线上个护小家电",
            "expansion_intent": "在高速电吹风、美容仪和配套耗材中重新找到增长曲线",
            "demand_shift": "从高增长断崖式转平,平台投流效率下降",
        },
        "competition": {
            "competitors": [
                "戴森(高端标杆)",
                "徕芬(国产高速吹风性价比颠覆者)",
                "其他国货个护新品牌(同质化)",
                "传统个护品牌延伸线",
            ],
            "customer_values": ["颜值设计", "价格", "功效", "品牌信任", "达人推荐"],
            "self_scores": {
                "颜值": "强",
                "价格": "中",
                "功效": "中",
                "品牌": "弱",
                "渠道运营": "强",
            },
            "unique_assets": [
                "50万私域会员沉淀",
                "耗材复购的用户黏性",
                "无技术专利、无独家渠道",
            ],
        },
        "capability": {
            "team_structure": {
                "production": "弱(代工不自产)",
                "supply_chain": "中",
                "sales": "强",
                "marketing": "强",
                "finance_management": "中",
            },
            "function_strength": {
                "product": "中",
                "supply_chain": "中",
                "channel": "强",
                "brand": "弱",
                "marketing": "强",
            },
            "digital_keyperson": "高度依赖2名抖音操盘手",
        },
        "availability_map": {
            "plus_present": [
                "business_model.revenue_mix",
                "capability.digital_keyperson",
                "finance.product_lines",
                "finance.customers",
                "finance.ar",
                "competition.self_scores",
                "competition.unique_assets",
            ],
            "plus_missing": [],
        },
    }
    return assemble_fact_base(intake, financial_facts)


CASE_BUILDERS = {
    "A": build_yonghui_fact_base,
    "B": build_chengxu_fact_base,
}


ANALYZERS = {
    "business_model": analyze_business_model,
    "capability": analyze_capability,
    "competition": analyze_competition,
    "finance": analyze_finance,
    "market": analyze_market,
}

SYNTHESIS_DIMENSION_ORDER = [
    "market",
    "competition",
    "business_model",
    "capability",
    "finance",
]

RETRY_GUARDRAIL = (
    "上一次输出未通过单维红线自检。务必严格按 financial_facts.product_lines[i].is_loss "
    "判断产品线盈亏：is_loss=false 的产品线绝不能写成亏损、亏钱、负贡献或利润黑洞；"
    "computed evidence 的 source 若混合问卷来源,仍只把 financial_facts 路径作为财务数字依据。"
)


def run_dimension(dimension: str, fact_base: dict, case: str) -> dict:
    if dimension == "market":
        return analyze_market(fact_base, SOURCE_CORPORA_BY_CASE[case]["market"])
    if dimension == "competition":
        return analyze_competition(fact_base, SOURCE_CORPORA_BY_CASE[case]["competition"])
    return ANALYZERS[dimension](fact_base)


def _fact_base_with_retry_instruction(fact_base: dict, report: dict) -> dict:
    retry_fact_base = deepcopy(fact_base)
    retry_fact_base["llm_retry_instruction"] = {
        "message": RETRY_GUARDRAIL,
        "previous_redline_failures": report.get("failures", []),
    }
    return retry_fact_base


def _single_redline_report(dimension_output: dict, fact_base: dict, source_corpora: dict) -> dict:
    return run_redline_check(
        [dimension_output],
        None,
        financial_facts=fact_base["financial_facts"],
        source_corpora=source_corpora,
        availability_map=fact_base.get("availability_map", {}),
        scope="single",
    )


def _mark_dimension_for_human_check(output: dict) -> None:
    output.setdefault("open_questions", [])
    output["open_questions"].append("该维度多次未通过幻读检查,需人工核验")
    degradation = output.setdefault("degradation", {})
    degradation["degraded"] = True
    hook = degradation.get("upgrade_hook", "")
    marker = "该维度多次未通过单维红线自检,需人工核验。"
    degradation["upgrade_hook"] = f"{hook} {marker}".strip()


def run_dimension_with_retry(
    dimension: str,
    fact_base: dict,
    case: str,
    source_corpora: dict,
    *,
    max_attempts: int = 3,
) -> dict:
    current_fact_base = fact_base
    last_output: dict | None = None
    last_report: dict | None = None
    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            print(f"\n=== RETRY {dimension} ATTEMPT {attempt}/{max_attempts} ===")
        output = run_dimension(dimension, current_fact_base, case)
        last_output = output
        report = _single_redline_report(output, fact_base, source_corpora)
        last_report = report
        if report["passed"]:
            if attempt > 1:
                print(f"=== {dimension} RETRY PASSED SINGLE REDLINE ===")
            return output

        print(f"\n=== {dimension} SINGLE REDLINE FAILED (attempt {attempt}/{max_attempts}) ===")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if attempt < max_attempts:
            current_fact_base = _fact_base_with_retry_instruction(fact_base, report)

    assert last_output is not None
    print(f"\n⚠️ {dimension} 多次未通过幻读检查,需人工核验")
    if last_report is not None:
        print(json.dumps(last_report, ensure_ascii=False, indent=2))
    _mark_dimension_for_human_check(last_output)
    return last_output


def print_redline_report(
    dimension_outputs: list[dict],
    synthesis_output: dict | None,
    fact_base: dict,
    source_corpora: dict,
    scope: str,
) -> dict:
    print(f"\n=== REDLINE CHECK REPORT ({scope}) ===")
    report = run_redline_check(
        dimension_outputs,
        synthesis_output,
        financial_facts=fact_base["financial_facts"],
        source_corpora=source_corpora,
        availability_map=fact_base.get("availability_map", {}),
        scope=scope,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if report["passed"]:
        return report

    print("\n⚠️ 红线自检未通过")
    for index, failure in enumerate(report["failures"], start=1):
        print(
            f"{index}. [{failure['check']}] {failure['path']} - {failure['reason']}"
        )
    raise SystemExit(1)


def run_full_synthesis_flow(fact_base: dict, case: str) -> tuple[list[dict], dict, dict]:
    dimension_outputs = []
    source_corpora = SOURCE_CORPORA_BY_CASE[case]
    for dimension in SYNTHESIS_DIMENSION_ORDER:
        print(f"\n=== DEEPSEEK {dimension} OUTPUT ===")
        output = run_dimension_with_retry(dimension, fact_base, case, source_corpora)
        dimension_outputs.append(output)
        print(json.dumps(output, ensure_ascii=False, indent=2))

    score_summary = calculate_overall_score(dimension_outputs)
    print("\n=== CODE-COMPUTED SCORE SUMMARY ===")
    print(json.dumps(score_summary, ensure_ascii=False, indent=2))
    print("\n=== DEEPSEEK SYNTHESIS OUTPUT ===")
    synthesis = synthesize_diagnosis(dimension_outputs)
    print(json.dumps(synthesis, ensure_ascii=False, indent=2))
    return dimension_outputs, synthesis, score_summary


def generate_report(
    *,
    case: str,
    fact_base: dict,
    dimension_outputs: list[dict],
    synthesis: dict,
    score_summary: dict,
) -> Path:
    output_dir = Path("report") / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    company_name = fact_base.get("diagnosis_intake", {}).get("company", {}).get("name", f"case_{case}")
    input_file = output_dir / f"{company_name}_case_{case}_report_input.json"
    output_file = output_dir / f"{company_name}_完整诊断报告_12页.pptx"
    payload = {
        "case": case,
        "fact_base": fact_base,
        "financial_facts": fact_base["financial_facts"],
        "dimension_outputs": dimension_outputs,
        "synthesis_output": synthesis,
        "score_summary": score_summary,
    }
    input_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    result = subprocess.run(
        [
            "node",
            str(Path("report") / "generate_sample.js"),
            "--input",
            str(input_file),
            "--out",
            str(output_file),
        ],
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    print("\n=== REPORT GENERATION OUTPUT ===")
    if result.stdout:
        print(result.stdout)
    if result.stderr:
        print(result.stderr)
    if result.returncode != 0:
        raise SystemExit(result.returncode)
    return output_file


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real DeepSeek dimension call.")
    parser.add_argument(
        "dimension",
        choices=sorted([*ANALYZERS, "synthesis", "offline_subset", "report", "thesis"]),
        help="Dimension to run, or synthesis to run all five dimensions then synthesize.",
    )
    parser.add_argument(
        "--case",
        choices=sorted(CASE_BUILDERS),
        default="A",
        help="Test case to run: A=甬辉(default), B=橙序.",
    )
    args = parser.parse_args()

    fact_base = CASE_BUILDERS[args.case]()
    source_corpora = SOURCE_CORPORA_BY_CASE[args.case]
    print(f"=== INPUT FACT BASE (CASE {args.case}) ===")
    print(json.dumps(fact_base, ensure_ascii=False, indent=2))

    if args.dimension == "offline_subset":
        dimension_outputs = []
        for dimension in ["capability", "business_model", "finance"]:
            print(f"\n=== DEEPSEEK {dimension} OUTPUT ===")
            output = run_dimension_with_retry(dimension, fact_base, args.case, source_corpora)
            dimension_outputs.append(output)
            print(json.dumps(output, ensure_ascii=False, indent=2))
        print_redline_report(dimension_outputs, None, fact_base, source_corpora, scope="single")
        return

    if args.dimension == "synthesis":
        dimension_outputs, synthesis, _score_summary = run_full_synthesis_flow(fact_base, args.case)
        print_redline_report(dimension_outputs, synthesis, fact_base, source_corpora, scope="full")
        return

    if args.dimension == "report":
        dimension_outputs, synthesis, score_summary = run_full_synthesis_flow(fact_base, args.case)
        redline_report = print_redline_report(
            dimension_outputs,
            synthesis,
            fact_base,
            source_corpora,
            scope="full",
        )
        if not redline_report["passed"]:
            raise SystemExit(1)
        output_file = generate_report(
            case=args.case,
            fact_base=fact_base,
            dimension_outputs=dimension_outputs,
            synthesis=synthesis,
            score_summary=score_summary,
        )
        print(f"\n=== REPORT FILE ===\n{output_file.resolve()}")
        return

    if args.dimension == "thesis":
        dimension_outputs, synthesis, _score_summary = run_full_synthesis_flow(fact_base, args.case)
        print_redline_report(dimension_outputs, synthesis, fact_base, source_corpora, scope="full")
        print("\n=== DEEPSEEK STRATEGIC THESIS OUTPUT ===")
        thesis = generate_strategic_thesis(synthesis, dimension_outputs)
        print(json.dumps(thesis, ensure_ascii=False, indent=2))
        return

    print(f"\n=== DEEPSEEK {args.dimension} OUTPUT ===")
    result = run_dimension_with_retry(args.dimension, fact_base, args.case, source_corpora)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print_redline_report([result], None, fact_base, source_corpora, scope="single")


if __name__ == "__main__":
    main()
