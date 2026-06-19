import json
import subprocess
from pathlib import Path


def _solution_report_payload():
    return {
        "company": "测试企业",
        "synthesis_output": {
            "confirmed_reversals": [
                {
                    "finding_id": "F02",
                    "reframe": "认证客户关系可能形成切换成本",
                    "falsifier": "客户正在全面询价竞品",
                    "depends_on": ["competition.unique_assets"],
                    "status": "needs_human_falsifier_check",
                }
            ]
        },
        "dimension_outputs": [
            {
                "dimension": "finance",
                "core_judgment": "现金安全优先于新增投入",
            }
        ],
        "strategic_thesis": {
            "strategic_thesis": "从亏损通用件扩张转向认证工程配套",
            "from_to": {
                "from": "亏损通用件扩张",
                "to": "认证工程配套",
            },
            "reasoning": ["现金约束要求先止损", "认证资产可以支撑转向"],
            "key_assumptions": ["认证关系仍能形成客户切换成本"],
        },
        "lever_matrix": {
            "levers": [
                {
                    "name": "砍掉亏损线释放资源",
                    "description": "停止亏损订单并释放现金和产能",
                    "impact": {"level": "高", "reason": "恢复现金安全"},
                    "feasibility": {"level": "高", "reason": "无需新增投入"},
                    "priority": 1,
                },
                {
                    "name": "开发认证工程客户",
                    "description": "用认证材料和样品切入工程客户",
                    "impact": {"level": "高", "reason": "承接战略转向"},
                    "feasibility": {"level": "中", "reason": "需要样品验证"},
                    "priority": 2,
                },
                {
                    "name": "建立接单底线",
                    "description": "按毛利和账期筛选订单",
                    "impact": {"level": "中", "reason": "减少失血"},
                    "feasibility": {"level": "高", "reason": "规则可直接实施"},
                    "priority": 3,
                },
            ],
            "selected": [
                {"name": "砍掉亏损线释放资源", "reason": "最紧急"},
                {"name": "开发认证工程客户", "reason": "承接增长"},
            ],
        },
        "action_map": {
            "actions": [
                {
                    "action": "停止亏损产品的新订单",
                    "category": "战略方向",
                    "owner": "创始人",
                    "expected_output": "停单决议",
                },
                {
                    "action": "整理认证工程客户样品包",
                    "category": "战术方向",
                    "owner": "销售负责人",
                    "expected_output": "样品包",
                },
                {
                    "action": "建立订单审批流程",
                    "category": "管理方向",
                    "owner": "运营负责人",
                    "expected_output": "审批流程",
                },
                {
                    "action": "核对应收账款和清仓计划",
                    "category": "风险财务",
                    "owner": "财务负责人",
                    "expected_output": "账龄表和清仓表",
                },
            ]
        },
        "roadmap": {
            "phases": [
                {
                    "phase_name": "止损释放期",
                    "goal": "停止亏损并释放资源",
                    "actions": [{"action": "停止亏损产品的新订单"}],
                    "rationale": "先释放资源",
                    "milestone": "停单和清仓方案获批",
                },
                {
                    "phase_name": "样品验证期",
                    "goal": "完成样品验证",
                    "actions": [{"action": "整理认证工程客户样品包"}],
                    "rationale": "验证客户需求",
                    "milestone": "客户完成样品反馈",
                },
                {
                    "phase_name": "客户转化期",
                    "goal": "形成首批订单",
                    "actions": [{"action": "扩大认证工程客户转化"}],
                    "rationale": "验证后转化",
                    "milestone": "形成首批订单",
                },
            ]
        },
        "ninety_day_plan": {
            "plan": [
                {
                    "task": "核对在手订单并冻结亏损新单",
                    "owner": "财务负责人",
                    "timeframe": "0-30天",
                    "deliverable": "订单处置清单",
                    "metric": "全部订单完成标记",
                },
                {
                    "task": "完成库存清仓和客户协商",
                    "owner": "销售负责人",
                    "timeframe": "31-60天",
                    "deliverable": "清仓时间表",
                    "metric": "客户确认状态全部登记",
                },
                {
                    "task": "复盘现金和产能释放结果",
                    "owner": "创始人",
                    "timeframe": "61-90天",
                    "deliverable": "止损复盘报告",
                    "metric": "管理层确认释放数据",
                },
            ]
        },
    }


def test_solution_report_generator_creates_pptx(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    input_file = tmp_path / "solution_input.json"
    output_file = tmp_path / "solution_report.pptx"
    input_file.write_text(
        json.dumps(_solution_report_payload(), ensure_ascii=False),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "node",
            str(repo_root / "report" / "generate_solution_report.js"),
            "--input",
            str(input_file),
            "--out",
            str(output_file),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode == 0, result.stderr
    assert output_file.exists()
    assert output_file.stat().st_size > 20_000
    assert "Slides:" in result.stdout


def test_solution_report_generator_rejects_missing_layer(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    payload = _solution_report_payload()
    del payload["roadmap"]
    input_file = tmp_path / "invalid_solution_input.json"
    output_file = tmp_path / "invalid_solution_report.pptx"
    input_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    result = subprocess.run(
        [
            "node",
            str(repo_root / "report" / "generate_solution_report.js"),
            "--input",
            str(input_file),
            "--out",
            str(output_file),
        ],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert result.returncode != 0
    assert not output_file.exists()
