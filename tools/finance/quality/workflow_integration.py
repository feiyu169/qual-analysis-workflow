"""
workflow集成模块

功能:
- 现有workflow.py无缝集成
- v3模块渐进式启用
- 降级策略完整

解决: Phase 8上线集成
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorkflowConfig:
    """工作流配置"""
    use_v3_modules: bool = True
    v3_modules_to_enable: list[str] = field(default_factory=lambda: [
        "year_anchor",
        "authority_resolver",
        "pipeline",
        "dcf_service",
        "capm_calculator",
        "terminal_value",
        "fcf_calculator",
        "roic_wacc_checker",
        "sensitivity_analyzer",
        "wind_field_mapper",
        "financial_standards",
        "incremental_checker",
        "audit_validator",
        "conclusion_synthesizer",
        "terminal_value_arbitrator",
    ])


class WorkflowIntegration:
    """工作流集成器"""

    def __init__(self, config: WorkflowConfig | None = None):
        self.config = config or WorkflowConfig()
        self._modules = {}
        self._load_modules()

    def _load_modules(self):
        """加载v3模块"""
        if not self.config.use_v3_modules:
            logger.info("v3模块未启用，使用现有实现")
            return

        try:
            # 尝试导入v3模块
            from finance.quality.v3.audit_validator import AuditValidator
            from finance.quality.v3.authority_resolver import AuthorityResolver
            from finance.quality.v3.capm_calculator import CAPMCalculator
            from finance.quality.v3.conclusion_synthesizer import ConclusionSynthesizer
            from finance.quality.v3.config_validator import ConfigValidator
            from finance.quality.v3.dcf_service import DCFService
            from finance.quality.v3.fcf_calculator import FCFCalculator
            from finance.quality.v3.feature_flags import FeatureFlags
            from finance.quality.v3.financial_standards import FinancialStandards
            from finance.quality.v3.incremental_checker import IncrementalChecker
            from finance.quality.v3.pipeline import QualityPipeline
            from finance.quality.v3.roic_wacc_checker import ROICWACCChecker
            from finance.quality.v3.sensitivity_analyzer import SensitivityAnalyzer
            from finance.quality.v3.terminal_value import TerminalValueCalculator
            from finance.quality.v3.terminal_value_arbitrator import TerminalValueArbitrator
            from finance.quality.v3.wind_field_mapper import WindFieldMapper
            from finance.quality.v3.year_anchor import YearAnchor

            self._modules = {
                "feature_flags": FeatureFlags,
                "config_validator": ConfigValidator,
                "year_anchor": YearAnchor,
                "authority_resolver": AuthorityResolver,
                "pipeline": QualityPipeline,
                "dcf_service": DCFService,
                "capm_calculator": CAPMCalculator,
                "terminal_value": TerminalValueCalculator,
                "fcf_calculator": FCFCalculator,
                "roic_wacc_checker": ROICWACCChecker,
                "sensitivity_analyzer": SensitivityAnalyzer,
                "wind_field_mapper": WindFieldMapper,
                "financial_standards": FinancialStandards,
                "incremental_checker": IncrementalChecker,
                "audit_validator": AuditValidator,
                "conclusion_synthesizer": ConclusionSynthesizer,
                "terminal_value_arbitrator": TerminalValueArbitrator,
            }

            logger.info(f"成功加载 {len(self._modules)} 个v3模块")

        except ImportError as e:
            logger.warning(f"v3模块加载失败: {e}，降级到现有实现")
            self._modules = {}

    def get_module(self, module_name: str) -> Any | None:
        """获取v3模块"""
        return self._modules.get(module_name)

    def is_module_available(self, module_name: str) -> bool:
        """检查模块是否可用"""
        return module_name in self._modules

    def run_analysis(
        self,
        ticker: str,
        market: str = "a_share",
        fiscal_year: int = 2025,
    ) -> dict[str, Any]:
        """运行完整分析"""
        result = {
            "ticker": ticker,
            "market": market,
            "fiscal_year": fiscal_year,
            "v3_modules_used": [],
            "warnings": [],
        }

        # 1. 年份锚点
        if self.is_module_available("year_anchor"):
            year_anchor = self._modules["year_anchor"](fiscal_year)
            result["year_anchor"] = year_anchor
            result["v3_modules_used"].append("year_anchor")

        # 2. 配置验证
        if self.is_module_available("config_validator"):
            config_validator = self._modules["config_validator"]()
            result["config_validator"] = config_validator
            result["v3_modules_used"].append("config_validator")

        # 3. Wind字段映射
        if self.is_module_available("wind_field_mapper"):
            wind_mapper = self._modules["wind_field_mapper"]()
            result["wind_mapper"] = wind_mapper
            result["v3_modules_used"].append("wind_field_mapper")

        # 4. 财务标准
        if self.is_module_available("financial_standards"):
            fin_standards = self._modules["financial_standards"]()
            result["fin_standards"] = fin_standards
            result["v3_modules_used"].append("financial_standards")

        # 5. FCF计算
        if self.is_module_available("fcf_calculator"):
            fcf_calc = self._modules["fcf_calculator"]()
            result["fcf_calculator"] = fcf_calc
            result["v3_modules_used"].append("fcf_calculator")

        # 6. CAPM计算
        if self.is_module_available("capm_calculator"):
            capm_calc = self._modules["capm_calculator"]()
            result["capm_calculator"] = capm_calc
            result["v3_modules_used"].append("capm_calculator")

        # 7. 终值计算
        if self.is_module_available("terminal_value"):
            tv_calc = self._modules["terminal_value"]()
            result["terminal_value_calculator"] = tv_calc
            result["v3_modules_used"].append("terminal_value")

        # 8. DCF服务
        if self.is_module_available("dcf_service"):
            dcf_service = self._modules["dcf_service"]()
            result["dcf_service"] = dcf_service
            result["v3_modules_used"].append("dcf_service")

        # 9. 敏感性分析
        if self.is_module_available("sensitivity_analyzer"):
            sensitivity = self._modules["sensitivity_analyzer"]()
            result["sensitivity_analyzer"] = sensitivity
            result["v3_modules_used"].append("sensitivity_analyzer")

        # 10. ROIC-WACC检查
        if self.is_module_available("roic_wacc_checker"):
            roic_checker = self._modules["roic_wacc_checker"]()
            result["roic_wacc_checker"] = roic_checker
            result["v3_modules_used"].append("roic_wacc_checker")

        # 11. 审计验证
        if self.is_module_available("audit_validator"):
            audit_validator = self._modules["audit_validator"]()
            result["audit_validator"] = audit_validator
            result["v3_modules_used"].append("audit_validator")

        # 12. 结论综合
        if self.is_module_available("conclusion_synthesizer"):
            conclusion = self._modules["conclusion_synthesizer"]()
            result["conclusion_synthesizer"] = conclusion
            result["v3_modules_used"].append("conclusion_synthesizer")

        # 13. 终值仲裁
        if self.is_module_available("terminal_value_arbitrator"):
            tv_arbitrator = self._modules["terminal_value_arbitrator"]()
            result["terminal_value_arbitrator"] = tv_arbitrator
            result["v3_modules_used"].append("terminal_value_arbitrator")

        # 14. 质量流水线
        if self.is_module_available("pipeline"):
            pipeline = self._modules["pipeline"]()
            result["pipeline"] = pipeline
            result["v3_modules_used"].append("pipeline")

        # 15. 权威解决器
        if self.is_module_available("authority_resolver"):
            authority = self._modules["authority_resolver"]()
            result["authority_resolver"] = authority
            result["v3_modules_used"].append("authority_resolver")

        # 16. 增量检查
        if self.is_module_available("incremental_checker"):
            incremental = self._modules["incremental_checker"]()
            result["incremental_checker"] = incremental
            result["v3_modules_used"].append("incremental_checker")

        logger.info(f"使用 {len(result['v3_modules_used'])} 个v3模块")

        return result

    def generate_integration_report(self) -> str:
        """生成集成报告"""
        lines = [
            "## 工作流集成报告",
            "",
            f"**v3模块启用**: {'是' if self.config.use_v3_modules else '否'}",
            f"**已加载模块数**: {len(self._modules)}",
            "",
            "### 可用模块",
            "",
        ]

        for module_name in sorted(self._modules.keys()):
            lines.append(f"- ✅ {module_name}")

        if not self._modules:
            lines.append("- ⚠️ 无v3模块，使用现有实现")

        return "\n".join(lines)
