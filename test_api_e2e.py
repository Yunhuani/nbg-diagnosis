from __future__ import annotations

import json
import time
from urllib import error, request


BASE_URL = "http://127.0.0.1:8000"
POLL_INTERVAL_SECONDS = 5
TIMEOUT_SECONDS = 900

DIAGNOSIS_INTAKE = {
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
    "market": {
        "home_market": "欧美及中东",
        "expansion_intent": "中东高端工程与无框淋浴隔断配套五金",
        "demand_shift": None,
    },
    "competition": {
        "competitors": [
            "浙江同省淋浴房出口同行（低价走量）",
            "中山中高端淋浴房厂",
            "欧美高端卫浴品牌",
        ],
        "customer_values": ["价格", "交付稳定性", "可定制化", "认证齐全度"],
        "self_scores": None,
        "unique_assets": None,
    },
    "business_model": {
        "revenue_sources": "淋浴隔断五金、排水配件、浴室置物架、龙头配件及定制小单",
        "how_earn_retain": "依靠OEM代工、稳定交付和老客户复购赚钱",
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
    "finance_basic": {
        "net_margin_band": "5%以下",
        "cost_structure": "原材料和人工为主，管理费用较高",
        "cash": 1180,
        "monthly_fixed": 720,
    },
    "finance_plus": None,
    "availability_map": {
        "plus_present": [],
        "plus_missing": [
            "competition.self_scores",
            "competition.unique_assets",
            "business_model.revenue_mix",
            "capability.digital_keyperson",
            "finance.product_lines",
            "finance.customers",
            "finance.ar",
        ],
    },
}


def call_json(method: str, path: str, payload: dict | None = None) -> dict:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"

    http_request = request.Request(
        f"{BASE_URL}{path}",
        data=body,
        headers=headers,
        method=method,
    )
    try:
        with request.urlopen(http_request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} failed: HTTP {exc.code}: {detail}") from exc


def main() -> None:
    created = call_json(
        "POST",
        "/diagnose",
        {
            "diagnosis_intake": DIAGNOSIS_INTAKE,
            "market_brief": None,
        },
    )
    job_id = created["job_id"]
    print(f"job_id: {job_id}")

    deadline = time.monotonic() + TIMEOUT_SECONDS
    last_status = None
    while time.monotonic() < deadline:
        job = call_json("GET", f"/diagnose/{job_id}")
        status = job["status"]
        if status != last_status:
            print(f"status: {status}")
            last_status = status

        if status == "done":
            print(json.dumps(job["result"], ensure_ascii=False, indent=2))
            return
        if status == "error":
            raise RuntimeError(job["error"] or "diagnosis failed without an error message")

        time.sleep(POLL_INTERVAL_SECONDS)

    raise TimeoutError(f"diagnosis job did not finish within {TIMEOUT_SECONDS} seconds")


if __name__ == "__main__":
    main()
