from __future__ import annotations

import json
import time
from pathlib import Path
from urllib import error, request


BASE_URL = "http://127.0.0.1:8000"
POLL_INTERVAL_SECONDS = 5
TIMEOUT_SECONDS = 900
CASES_DIR = Path(__file__).resolve().parent / "cases"
OUTPUT_DIR = CASES_DIR / "output"
CASES = [
    ("餐饮连锁", "restaurant"),
    ("电商", "ecommerce"),
    ("实体零售", "retail"),
    ("本地服务", "local_service"),
    ("科技公司", "tech_saas"),
]
DIMENSION_LABELS = {
    "market": "市场",
    "competition": "竞争",
    "business_model": "商业模式",
    "capability": "能力",
    "finance": "财务",
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
        raise RuntimeError(
            f"{method} {path} failed: HTTP {exc.code}: {detail}"
        ) from exc


def redline_counts(result: dict) -> tuple[int, int]:
    report = result.get("redline_report") or result.get("redline") or {}
    return len(report.get("failures") or []), len(report.get("warnings") or [])


def quality_levels(result: dict) -> dict[str, str]:
    dimensions = result.get("data_quality", {}).get("dimensions") or []
    levels = {
        item.get("dimension"): item.get("level", "unknown")
        for item in dimensions
    }
    return {
        key: levels.get(key, "unknown")
        for key in DIMENSION_LABELS
    }


def run_case(industry: str, stem: str) -> dict:
    intake = json.loads((CASES_DIR / f"{stem}.json").read_text(encoding="utf-8"))
    started = time.monotonic()
    created = call_json(
        "POST",
        "/diagnose",
        {"diagnosis_intake": intake, "market_brief": None},
    )
    job_id = created["job_id"]
    deadline = started + TIMEOUT_SECONDS
    final_job = None

    while time.monotonic() < deadline:
        job = call_json("GET", f"/diagnose/{job_id}")
        status = job["status"]
        if status == "done":
            final_job = job
            break
        if status == "error":
            raise RuntimeError(job.get("error") or "diagnosis failed without an error message")
        time.sleep(POLL_INTERVAL_SECONDS)

    if final_job is None:
        raise TimeoutError(
            f"{industry} diagnosis did not finish within {TIMEOUT_SECONDS} seconds"
        )

    elapsed = time.monotonic() - started
    result = final_job["result"]
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{stem}_result.json"
    output_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    failures, warnings = redline_counts(result)
    levels = quality_levels(result)

    print(f"行业名: {industry}")
    print(f"最终状态: {final_job['status']}")
    print(f"耗时: {elapsed:.1f}秒")
    print(f"红线 failures: {failures}")
    print(f"红线 warnings: {warnings}")
    print(
        "五维 data_quality: "
        + "，".join(
            f"{DIMENSION_LABELS[key]}={levels[key]}"
            for key in DIMENSION_LABELS
        )
    )
    print()

    return {
        "industry": industry,
        "status": final_job["status"],
        "elapsed": elapsed,
        "failures": failures,
        "warnings": warnings,
        "levels": levels,
    }


def print_summary(rows: list[dict]) -> None:
    headers = [
        "行业",
        "状态",
        "耗时(秒)",
        "failures",
        "warnings",
        "市场",
        "竞争",
        "商业模式",
        "能力",
        "财务",
    ]
    values = [
        headers,
        *[
            [
                row["industry"],
                row["status"],
                f"{row['elapsed']:.1f}",
                str(row["failures"]),
                str(row["warnings"]),
                row["levels"]["market"],
                row["levels"]["competition"],
                row["levels"]["business_model"],
                row["levels"]["capability"],
                row["levels"]["finance"],
            ]
            for row in rows
        ],
    ]
    widths = [
        max(len(item[index]) for item in values)
        for index in range(len(headers))
    ]
    print("汇总表")
    for row_index, row in enumerate(values):
        print(" | ".join(item.ljust(widths[index]) for index, item in enumerate(row)))
        if row_index == 0:
            print("-+-".join("-" * width for width in widths))


def main() -> None:
    rows = [run_case(industry, stem) for industry, stem in CASES]
    print_summary(rows)


if __name__ == "__main__":
    main()
