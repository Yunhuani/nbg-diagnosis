from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from analysis.dimensions import analyze_business_model
from analysis.fact_base import assemble_fact_base
from finance.calculator import calculate_financial_facts


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _build_fact_base() -> dict:
    financial_facts = calculate_financial_facts(
        product_lines=[
            {"name": "精密冲压结构件", "revenue": 4500, "total_cost": 3870},
            {"name": "机加工组件", "revenue": 1800, "total_cost": 1710},
            {"name": "表面处理服务", "revenue": 1200, "total_cost": 960},
            {"name": "模具开发", "revenue": 1500, "total_cost": 1200},
            {"name": "小批量定制", "revenue": 1000, "total_cost": 1070},
        ],
        customers=[
            {"name": "欧洲设备客户A", "pct": 32},
            {"name": "北美渠道客户B", "pct": 21},
            {"name": "东南亚客户C", "pct": 12},
            {"name": "国内配套客户D", "pct": 8},
            {"name": "其他客户", "pct": 27},
        ],
        cash=900,
        monthly_fixed=520,
        ar_balance=3600,
        ar_days=96,
    )
    intake = {
        "company": {
            "name": "宁波海拓精密制造有限公司",
            "industry_sub": "精密制造出口企业",
            "region": "欧美及东南亚",
        },
        "business_model": {
            "revenue_sources": "精密冲压结构件、机加工组件、表面处理服务、模具开发和小批量定制",
            "how_earn_retain": "依靠出口 OEM/ODM 订单、稳定交付、工程打样和老客户复购获得收入",
            "revenue_mix": (
                "精密冲压结构件45%、机加工组件18%、表面处理服务12%、模具开发15%、小批量定制10%；"
                "主要成本结构为原材料45%、人工18%、外协/表面处理12%、物流与报关8%、能源与设备折旧7%、其他10%。"
            ),
        },
        "availability_map": {
            "plus_present": [
                "business_model.revenue_mix",
                "finance.product_lines",
                "finance.customers",
                "finance.ar",
            ],
            "plus_missing": [],
        },
    }
    return assemble_fact_base(intake, financial_facts)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    _load_dotenv(Path(".env"))
    result = analyze_business_model(_build_fact_base())
    print(json.dumps(result.get("evidence", []), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
