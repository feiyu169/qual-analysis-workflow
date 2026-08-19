"""
Gate 0: 数据源验证

严苛模式+人工同意
"""

from typing import Dict, Any, List
from dataclasses import dataclass
from datetime import datetime
import logging
import time

from ..core.gate_engine import GateBase, GateSpec, GateResult
from ..core.circuit_breaker import CircuitBreaker, ErrorType
from ..core.error_classifier import ErrorClassifier

logger = logging.getLogger(__name__)


@dataclass
class DataSourceConfig:
    """数据源配置"""
    primary_source: str  # 主数据源
    fallback_sources: List[str]  # 备用数据源
    required_fields: List[str]  # 必填字段
    min_coverage: float  # 最小覆盖率
    max_deviation: float  # 最大偏差
    timeout: int  # 超时时间
    max_retries: int  # 最大重试次数


class Gate0DataSourceValidation(GateBase):
    """Gate 0: 数据源验证"""
    
    def __init__(self):
        spec = GateSpec(
            gate_num=0,
            name="数据源验证",
            description="严苛模式+人工同意",
            prerequisites=[],
            timeout=600,  # 10分钟
            max_retries=3,
            pass_criteria=[
                {"name": "财报文件存在", "type": "condition", "condition": "filing_exists"},
                {"name": "Wind字段覆盖率", "type": "quantitative", "metric": "wind_coverage", "threshold": 0.95},
                {"name": "必填字段存在", "type": "condition", "condition": "required_fields_exist"},
                {"name": "数值类型正确", "type": "condition", "condition": "value_types_correct"},
                {"name": "数据时间范围", "type": "condition", "condition": "data_range_covers_3_years"},
            ],
        )
        super().__init__(spec)
        
        self.config = DataSourceConfig(
            primary_source="wind_api",
            fallback_sources=["tushare", "eastmoney", "company_ir"],
            required_fields=["revenue", "net_income", "operating_cash_flow", "total_assets"],
            min_coverage=0.95,
            max_deviation=0.02,
            timeout=30,
            max_retries=3,
        )
        
        self.circuit_breaker = CircuitBreaker(
            name="data_source",
            failure_threshold=3,
            reset_timeout=60,
        )
        
        self.error_classifier = ErrorClassifier()
    
    def execute(self, context: Dict[str, Any]) -> GateResult:
        """执行Gate 0（真实数据源验证）"""
        errors = []
        warnings = []
        details = {}

        # 1. 尝试获取财报（从 context 取已下载数据）
        filing_result = self._fetch_filing(context)
        details["filing"] = filing_result

        if not filing_result["success"]:
            errors.append(f"财报获取失败: {filing_result.get('error', '未知错误')}")

        # 2. 尝试获取Wind数据（从 context 取已装配数据）
        wind_result = self._fetch_wind_data(context)
        details["wind"] = wind_result

        if not wind_result["success"]:
            errors.append(f"Wind数据获取失败: {wind_result.get('error', '未知错误')}")

        # 3. 验证数据完整性（真实：canonical 键覆盖率 + 3年范围）
        validation_result = self._validate_data(filing_result, wind_result, context)
        details["validation"] = validation_result

        if not validation_result["passed"]:
            errors.extend(validation_result["errors"])

        # 4. 计算得分
        score = 100.0
        if errors:
            score -= len(errors) * 20
        score = max(0.0, min(100.0, score))

        passed = len(errors) == 0

        # 5. 写入 context 供后续 Gate 与 check_criteria 使用
        context["gate_0_result"] = {
            "filing_exists": filing_result["success"],
            "wind_coverage": validation_result.get("coverage", 0.0),
            "missing_fields": validation_result.get("missing", []),
            "has_3y": validation_result.get("has_3y", False),
        }
        context["wind_coverage"] = validation_result.get("coverage", 0.0)

        return GateResult(
            gate_num=0,
            passed=passed,
            score=score,
            details=details,
            errors=errors,
            warnings=warnings,
            execution_time=0.0,
            timestamp=datetime.now().isoformat(),
        )

    def check_criteria(self, context: Dict[str, Any]) -> bool:
        """检查通过标准（真实）"""
        # 检查财报文件是否存在
        filing_exists = bool((context.get("filing_data") or {}).get("sections"))

        # 检查Wind字段覆盖率（从 execute 写入的 context 读取）
        wind_coverage = context.get("wind_coverage", 0.0)

        # 检查必填字段
        required_fields_exist = wind_coverage >= self.config.min_coverage

        # 检查数值类型
        value_types_correct = self._check_value_types(context.get("wind_data", {}))

        # 检查数据时间范围
        data_range_covers_3_years = self._check_data_range(context.get("wind_data", {}))

        return (
            filing_exists
            and wind_coverage >= self.config.min_coverage
            and required_fields_exist
            and value_types_correct
            and data_range_covers_3_years
        )

    def _fetch_filing(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """获取财报（从 context 取已下载/已解析数据）"""
        filing_data = context.get("filing_data")
        if not filing_data:
            return {"success": False, "error": "context 无 filing_data"}
        sections = filing_data.get("sections") or {}
        if not sections:
            return {"success": False, "error": "filing_data.sections 为空"}
        return {"success": True, "data": filing_data, "sections_count": len(sections)}

    def _fetch_wind_data(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """获取Wind数据（从 context 取已装配数据）"""
        wind_data = context.get("wind_data")
        if not wind_data:
            return {"success": False, "error": "context 无 wind_data"}
        return {"success": True, "data": wind_data}

    def _validate_data(self, filing_result: Dict, wind_result: Dict,
                       context: Dict[str, Any]) -> Dict[str, Any]:
        """验证数据（真实：canonical 键覆盖率 + 3年范围）"""
        errors = []

        if not filing_result["success"]:
            errors.append("财报数据缺失")

        coverage, missing = 0.0, []
        has_3y = False
        if wind_result["success"]:
            from ..adapters import wind_coverage, has_3y_range
            coverage, missing = wind_coverage(context.get("wind_data"))
            has_3y = has_3y_range(context.get("wind_data"))
            if coverage < self.config.min_coverage:
                errors.append(f"Wind字段覆盖率不足: {coverage:.0%} < {self.config.min_coverage:.0%}，缺失: {missing}")
            if not has_3y:
                errors.append("Wind数据未覆盖最近3年")

        return {
            "passed": len(errors) == 0,
            "errors": errors,
            "coverage": coverage,
            "missing": missing,
            "has_3y": has_3y,
        }

    def _check_value_types(self, wind_data: Dict) -> bool:
        """检查数值类型（真实：canonical 键的值应为数字列表）"""
        if not wind_data:
            return False
        from ..adapters import WIND_SECTIONS
        for section in WIND_SECTIONS:
            table = wind_data.get(section) or {}
            for field, value in table.items():
                if isinstance(value, list) and value:
                    if not all(isinstance(v, (int, float)) for v in value if v is not None):
                        return False
        return True

    def _check_data_range(self, wind_data: Dict) -> bool:
        """检查数据时间范围（真实：覆盖3年）"""
        from ..adapters import has_3y_range
        return has_3y_range(wind_data)
