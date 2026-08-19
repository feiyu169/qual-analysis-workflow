"""
MCP Server 核心 - V3.0 方案
5个核心工具：classify_task, assess_risk, execute_gates, verify_tdd, check_security
"""

import json
import os
import sqlite3
import sys
import time
from datetime import datetime

# 添加模块路径（相对本文件，兼容任意部署位置）
# noqa: E402 —— 路径引导必须在 workflow 模块导入之前执行，属刻意顺序
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

import structlog  # noqa: E402

from gate_executor import GateExecutor, GateExecutorError  # noqa: E402

logger = structlog.get_logger()

# MCP Server 配置
DB_PATH = os.path.join(_HERE, "workflow.db")
GATES_CONFIG = os.path.join(_HERE, "config", "mcp-gates.yaml")


class WorkflowError(Exception):
    """工作流错误"""


class AuditLogger:
    """审计日志记录器（V3.2.9 职责澄清）。

    与 .hgf/ 观测体系的关系（修复评审 I）：
    - gate_executor 统一写 `.hgf/runs.jsonl`（门禁结果历史，主观测，
      供 --history 趋势统计），本类**不再重复记录门禁结果**；
    - 本类只记录 MCP 服务的**调用审计**（谁在何时调用了哪个工具、
      输入/输出摘要、状态与耗时），用于 MCP 层自身的可追踪性。
    两套数据维度不同（结果历史 vs 调用审计），互不替代。
    """

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT,
                tool TEXT,
                input TEXT,
                output TEXT,
                status TEXT,
                duration REAL
            )
        """)
        # V3.3.1（复审共识：死代码清理）：gate_results 表在 V3.2.9 停止双写后
        # 从未再写入，删除表定义（门禁历史统一 .hgf/runs.jsonl）。
        conn.commit()
        conn.close()

    def log(
        self,
        tool: str,
        input_data: dict,
        output_data: dict,
        status: str,
        duration: float,
    ):
        """记录审计日志"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute(
                """
                INSERT INTO audit_log (timestamp, tool, input, output, status, duration)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    datetime.now().isoformat(),
                    tool,
                    json.dumps(input_data, ensure_ascii=False),
                    json.dumps(output_data, ensure_ascii=False),
                    status,
                    duration,
                ),
            )
            conn.commit()
            conn.close()
        except Exception as e:
            logger.error("audit_log_error", error=str(e))


# 初始化组件
audit_logger = AuditLogger(DB_PATH)
# V3.3-R4：DAG 接电经注入回调（执行器不再依赖生命周期模块）
try:
    import lifecycle as _lifecycle

    _matrix_cb = _lifecycle.record_matrix_evidence
except Exception:
    _matrix_cb = None
gate_executor = GateExecutor(GATES_CONFIG, matrix_evidence_callback=_matrix_cb)


def classify_task(
    description: str,
    files: list[str],
    lines: int = 0,
    affected_areas: list[str] = None,
    labels: list[str] = None,
) -> dict:
    """
    任务分级

    Args:
        description: 任务描述
        files: 文件列表
        lines: 变更行数
        affected_areas: 影响区域
        labels: PR 标签

    Returns:
        分级结果
    """
    start_time = time.time()

    try:
        # 导入任务分级器
        from task_classifier import Task, TaskClassifier

        classifier = TaskClassifier()

        task = Task(
            description=description,
            files=files,
            file_count=len(files),
            line_count=lines,
            affected_areas=affected_areas or [],
            labels=labels or [],
        )

        classification = classifier.classify_task(task)

        # 风险评估
        from risk_assessor import RiskAssessor

        assessor = RiskAssessor()
        risk_result = assessor.assess_risk(
            affected_areas=task.affected_areas, description=task.description
        )

        result = {
            "level": classification.level,
            "type": classification.type,
            "types": classification.types,
            "change_lines": classification.change_lines,
            "risk": risk_result.risk,
            "risk_score": risk_result.score,
            "matched_factors": risk_result.matched_factors,
        }

        duration = time.time() - start_time
        audit_logger.log(
            "classify_task",
            {
                "description": description,
                "files": files,
                "lines": lines,
            },
            result,
            "success",
            duration,
        )

        logger.info("task_classified", level=result["level"], risk=result["risk"])
        return result

    except Exception as e:
        duration = time.time() - start_time
        audit_logger.log(
            "classify_task",
            {
                "description": description,
            },
            {"error": str(e)},
            "error",
            duration,
        )
        logger.error("classification_failed", error=str(e))
        raise WorkflowError(f"任务分级失败: {e!s}")


def assess_risk(affected_areas: list[str], description: str = "") -> dict:
    """
    风险评估

    Args:
        affected_areas: 影响区域列表
        description: 任务描述

    Returns:
        风险评估结果
    """
    start_time = time.time()

    try:
        from risk_assessor import RiskAssessor

        assessor = RiskAssessor()

        result = assessor.assess_risk(affected_areas, description)

        output = {
            "risk": result.risk,
            "score": result.score,
            "matched_factors": result.matched_factors,
            "combination_bonus": result.combination_bonus,
            "reduction_applied": result.reduction_applied,
        }

        duration = time.time() - start_time
        audit_logger.log(
            "assess_risk",
            {
                "affected_areas": affected_areas,
                "description": description,
            },
            output,
            "success",
            duration,
        )

        return output

    except Exception as e:
        duration = time.time() - start_time
        audit_logger.log(
            "assess_risk",
            {
                "affected_areas": affected_areas,
            },
            {"error": str(e)},
            "error",
            duration,
        )
        raise WorkflowError(f"风险评估失败: {e!s}")


def execute_gates(level: str, files: list[str], working_dir: str = ".") -> dict:
    """
    执行质量门禁

    Args:
        level: 任务等级
        files: 变更文件列表
        working_dir: 工作目录

    Returns:
        门禁执行结果
    """
    start_time = time.time()

    try:
        report = gate_executor.execute_gates(level, files, working_dir)

        output = report.to_dict()

        duration = time.time() - start_time
        audit_logger.log(
            "execute_gates",
            {
                "level": level,
                "files": files,
                "working_dir": working_dir,
            },
            output,
            "success",
            duration,
        )

        # 门禁结果历史已由 gate_executor 统一写入 .hgf/runs.jsonl
        # （V3.2.9 修复 I：不再双写 sqlite gate_results 表）
        return output

    except GateExecutorError as e:
        # fail-closed: MUST_PASS 工具不可用，拒绝操作
        duration = time.time() - start_time
        audit_logger.log(
            "execute_gates",
            {
                "level": level,
            },
            {"error": str(e)},
            "rejected",
            duration,
        )
        raise WorkflowError(str(e))

    except Exception as e:
        duration = time.time() - start_time
        audit_logger.log(
            "execute_gates",
            {
                "level": level,
            },
            {"error": str(e)},
            "error",
            duration,
        )
        raise WorkflowError(f"门禁执行失败: {e!s}")


def verify_tdd(git_history: dict = None, working_dir: str = ".") -> dict:
    """
    验证 TDD 证据

    V3.2.9（修复评审 B）：委托 lifecycle._check_tdd_evidence 的 git 历史
    真实验证（测试文件首次提交 ≤ 实现文件首次提交），不再用
    "commit 消息含 test 字样"的弱判定。

    Args:
        git_history: 兼容参数（保留签名，实际以 git 历史为准）
        working_dir: 工作目录

    Returns:
        TDD 验证结果
    """
    start_time = time.time()

    try:
        import lifecycle as _lifecycle

        ok, issues = _lifecycle._check_tdd_evidence({}, working_dir, None)
        output = {
            "has_test_evidence": ok,
            "commits_analyzed": "git history (via lifecycle._check_tdd_evidence)",
            "recommendation": "通过" if ok else "; ".join(issues),
            "verifier": "lifecycle._check_tdd_evidence",
        }

        duration = time.time() - start_time
        audit_logger.log(
            "verify_tdd",
            {
                "working_dir": working_dir,
            },
            output,
            "success" if ok else "rejected",
            duration,
        )

        return output

    except Exception as e:
        duration = time.time() - start_time
        audit_logger.log("verify_tdd", {}, {"error": str(e)}, "error", duration)
        raise WorkflowError(f"TDD 验证失败: {e!s}")


def check_security(files: list[str], working_dir: str = ".") -> dict:
    """
    安全检查

    Args:
        files: 文件列表
        working_dir: 工作目录

    Returns:
        安全检查结果
    """
    start_time = time.time()

    try:
        # V3.3.1（复审共识：第三套执行路径）：check_security 改走
        # tool_runner.safe_run（argv + shell=False），与 gate_plugins/lifecycle
        # 统一，消灭 mcp_server 独立 subprocess 实现。
        import subprocess

        from . import tool_runner as _runner

        results = {}

        # 密钥扫描
        try:
            detect_secrets = _runner.safe_run(
                ["detect-secrets", "scan"] + files,
                working_dir,
                timeout=60,
            )
            results["secret_scan"] = {
                "tool": "detect-secrets",
                "exit_code": detect_secrets.returncode,
                "passed": detect_secrets.returncode == 0,
            }
        except FileNotFoundError:
            # fail-closed: MUST_PASS 工具不可用则拒绝
            raise WorkflowError("detect-secrets 不可用，安全检查被拒绝")
        except subprocess.TimeoutExpired:
            results["secret_scan"] = {"tool": "detect-secrets", "error": "timeout"}

        # 安全扫描
        try:
            semgrep = _runner.safe_run(
                ["semgrep", "--config=p/r2c-ci"] + files,
                working_dir,
                timeout=120,
            )
            results["security_scan"] = {
                "tool": "semgrep",
                "exit_code": semgrep.returncode,
                "passed": semgrep.returncode == 0,
            }
        except FileNotFoundError:
            # SHOULD_PASS 工具不可用则警告
            logger.warning("semgrep_not_available")
            results["security_scan"] = {"tool": "semgrep", "skipped": True}
        except subprocess.TimeoutExpired:
            results["security_scan"] = {"tool": "semgrep", "error": "timeout"}

        all_passed = all(
            r.get("passed", False) or r.get("skipped", False) for r in results.values()
        )

        output = {
            "files_checked": len(files),
            "all_passed": all_passed,
            "results": results,
        }

        duration = time.time() - start_time
        audit_logger.log(
            "check_security",
            {
                "files": files,
            },
            output,
            "success",
            duration,
        )

        return output

    except WorkflowError:
        raise
    except Exception as e:
        duration = time.time() - start_time
        audit_logger.log(
            "check_security",
            {
                "files": files,
            },
            {"error": str(e)},
            "error",
            duration,
        )
        raise WorkflowError(f"安全检查失败: {e!s}")


def get_workflow_status() -> dict:
    """
    获取工作流状态（V3.2.9：观测收敛——门禁趋势以 .hgf/runs.jsonl 为准，
    sqlite 仅作 MCP 调用审计，不再双写门禁结果）

    Returns:
        工作流统计信息
    """
    # 门禁结果历史（主观测）：.hgf/runs.jsonl 趋势
    hgf_stats = {}
    try:
        import run_history

        wd = os.path.dirname(os.path.abspath(__file__))
        entries = run_history.history(wd)
        hgf_stats = run_history.summarize(entries)
    except Exception:
        hgf_stats = {"error": "unable to read .hgf/runs.jsonl"}

    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # 获取总调用次数
        cursor.execute("SELECT COUNT(*) FROM audit_log")
        total_calls = cursor.fetchone()[0]

        # 获取成功/失败次数
        cursor.execute("SELECT status, COUNT(*) FROM audit_log GROUP BY status")
        status_counts = dict(cursor.fetchall())

        conn.close()

        return {
            "mcp_calls": {
                "total_calls": total_calls,
                "success_count": status_counts.get("success", 0),
                "error_count": status_counts.get("error", 0),
                "rejected_count": status_counts.get("rejected", 0),
            },
            "hgf_gate_history": hgf_stats,
        }

    except Exception as e:
        return {"error": str(e), "hgf_gate_history": hgf_stats}


# CLI 接口
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MCP Workflow Server")
    subparsers = parser.add_subparsers(dest="command")

    # classify 命令
    classify_parser = subparsers.add_parser("classify")
    classify_parser.add_argument("--task", required=True)
    classify_parser.add_argument("--files", required=True)
    classify_parser.add_argument("--lines", type=int, default=0)

    # execute 命令
    execute_parser = subparsers.add_parser("execute")
    execute_parser.add_argument("--level", required=True)
    execute_parser.add_argument("--files", required=True)

    # status 命令
    status_parser = subparsers.add_parser("status")

    args = parser.parse_args()

    if args.command == "classify":
        files = [f.strip() for f in args.files.split(",")]
        result = classify_task(args.task, files, args.lines)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "execute":
        files = [f.strip() for f in args.files.split(",")]
        result = execute_gates(args.level, files)
        print(json.dumps(result, indent=2, ensure_ascii=False))

    elif args.command == "status":
        result = get_workflow_status()
        print(json.dumps(result, indent=2, ensure_ascii=False))

    else:
        parser.print_help()
