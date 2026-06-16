from __future__ import annotations

from typing import Any


def calculate_financial_facts(
    *,
    product_lines: list[dict[str, Any]] | None,
    customers: list[dict[str, Any]] | None,
    cash: float,
    monthly_fixed: float,
    ar_balance: float | None = None,
    ar_days: float | None = None,
) -> dict[str, Any]:
    """Calculate deterministic financial facts in RMB 10k units."""
    facts: dict[str, Any] = {
        "tier": "full",
        "product_lines": _calculate_product_lines(product_lines),
        "customer_concentration": _calculate_customer_concentration(customers),
        "cash_runway_months": round(cash / monthly_fixed, 1),
        "ar": _calculate_ar(ar_balance, ar_days),
    }

    if (
        facts["product_lines"] is None
        and facts["customer_concentration"] is None
        and facts["ar"] is None
    ):
        facts["tier"] = "basic_only"

    return facts


def _calculate_product_lines(
    product_lines: list[dict[str, Any]] | None,
) -> list[dict[str, Any]] | None:
    if product_lines is None:
        return None

    total_revenue = sum(float(line["revenue"]) for line in product_lines)
    return [
        {
            "name": line["name"],
            "full_cost_net": float(line["revenue"])
            - float(line["direct_cost"])
            - float(line["allocated"]),
            "revenue": float(line["revenue"]),
            "revenue_share": round(float(line["revenue"]) / total_revenue, 3),
            "unit": "万元",
            "is_loss": (
                float(line["revenue"])
                - float(line["direct_cost"])
                - float(line["allocated"])
            )
            < 0,
        }
        for line in product_lines
    ]


def _calculate_customer_concentration(
    customers: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    if customers is None:
        return None

    named_customer_pcts = [
        float(customer["pct"])
        for customer in customers
        if str(customer["name"]) not in {"散客", "C端散客", "其他", "其他客户", "零散客户"}
    ]
    sorted_pcts = sorted(named_customer_pcts, reverse=True)
    return {
        "top3_pct": sum(sorted_pcts[:3]),
        "top1_pct": sorted_pcts[0] if sorted_pcts else 0,
        "benchmark_healthy": 40,
    }


def _calculate_ar(ar_balance: float | None, ar_days: float | None) -> dict[str, Any] | None:
    if ar_balance is None or ar_days is None:
        return None

    if float(ar_days) <= 60:
        releasable = 0
    else:
        releasable = float(ar_balance) * (float(ar_days) - 60) / float(ar_days)
    return {
        "balance": float(ar_balance),
        "days": float(ar_days),
        "releasable_at_60days": round(releasable),
        "unit": "万元",
    }
