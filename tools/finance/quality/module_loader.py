"""
模块加载器（动态路径+配置管理+启动自检）

功能：
1. 动态路径加载模块
2. 配置管理
3. 启动自检
4. 最小必备检查白名单
"""

import importlib
import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ModuleConfig:
    """模块配置"""
    paths: list[str]
    required: bool
    description: str


class ModuleLoader:
    """模块加载器"""

    # 模块路径配置（HGF P0-② 2026-08-22：候选路径指向平铺真实模块——
    # gate_checks 为纯幻想模块（无任何实现）→ 降级为非必需；review_integrator 指向平铺实现）
    MODULE_CONFIG: dict[str, ModuleConfig] = {
        "gate_checks": ModuleConfig(
            paths=[
                "finance.quality.gate_auto_check",
                "finance.quality.gate_evaluator",
                "quality.gate_auto_check",
            ],
            required=False,
            description="Gate Checks模块（HGF P0-②：hermes 版 gate_checks 未随迁，降级为非必需）",
        ),
        "review_integrator": ModuleConfig(
            paths=[
                "finance.quality.review_integrator",
                "quality.review_integrator",
                "finance.quality.v3.review_integrator",
            ],
            required=True,
            description="审查集成模块（必须加载）",
        ),
        "content_validator": ModuleConfig(
            paths=[
                "finance.quality.content_validator",
                "quality.content_validator",
                "finance.quality.v3.content_validator",
            ],
            required=True,
            description="内容验证模块（必须加载）",
        ),
        "exception_handler": ModuleConfig(
            paths=[
                "finance.quality.exception_handler",
                "quality.exception_handler",
                "finance.quality.v3.exception_handler",
            ],
            required=True,
            description="异常处理模块（必须加载）",
        ),
    }

    # 最小必备检查白名单（禁止通过配置禁用）
    # HGF P0-②：gate_checks 为 hermes 幻想模块（无实现）→ 移出白名单，降级非必需
    MINIMAL_REQUIRED_CHECKS = [
        "review_integrator",
        "content_validator",
        "exception_handler",
    ]

    # 已加载模块缓存
    _loaded_modules: dict[str, any] = {}

    @classmethod
    def load_module(cls, module_name: str):
        """加载模块（动态路径）"""
        # 检查缓存
        if module_name in cls._loaded_modules:
            return cls._loaded_modules[module_name]

        config = cls.MODULE_CONFIG.get(module_name)
        if not config:
            raise ValueError(f"未知模块: {module_name}")

        for path in config.paths:
            try:
                module = importlib.import_module(path)
                cls._loaded_modules[module_name] = module
                logger.info(f"模块'{module_name}'加载成功: {path}")
                return module
            except ImportError:
                continue

        if config.required:
            raise ImportError(
                f"必需模块'{module_name}'加载失败，所有路径都不可用: {config.paths}"
            )

        logger.warning(f"可选模块'{module_name}'加载失败")
        return None

    @classmethod
    def validate_paths(cls) -> list[str]:
        """验证所有必需模块路径（启动自检）"""
        errors = []
        for name, config in cls.MODULE_CONFIG.items():
            if config.required:
                try:
                    cls.load_module(name)
                except ImportError as e:
                    errors.append(str(e))
        return errors

    @classmethod
    def validate_minimal_checks(cls) -> list[str]:
        """验证最小必备检查（禁止禁用）"""
        errors = []
        for check_name in cls.MINIMAL_REQUIRED_CHECKS:
            if check_name not in cls.MODULE_CONFIG:
                errors.append(f"最小必备检查'{check_name}'未在配置中定义")
            elif not cls.MODULE_CONFIG[check_name].required:
                errors.append(
                    f"最小必备检查'{check_name}'被标记为非必需，这是不允许的"
                )
        return errors

    @classmethod
    def startup_self_check(cls):
        """启动自检"""
        logger.info("开始模块加载自检...")

        # 验证路径
        path_errors = cls.validate_paths()
        if path_errors:
            raise RuntimeError(
                "模块路径验证失败:\n" + "\n".join(path_errors)
            )

        # 验证最小必备检查
        check_errors = cls.validate_minimal_checks()
        if check_errors:
            raise RuntimeError(
                "最小必备检查验证失败:\n" + "\n".join(check_errors)
            )

        logger.info("模块加载自检通过")
        return True

    @classmethod
    def get_loaded_modules(cls) -> dict[str, str]:
        """获取已加载模块信息"""
        return {
            name: config.description
            for name, config in cls.MODULE_CONFIG.items()
            if name in cls._loaded_modules
        }

    @classmethod
    def check_all_modules(cls) -> dict[str, Any]:
        """检查所有模块状态（兼容workflow.py调用）

        Returns:
            dict: {"success": bool, "warnings": list, "loaded": list}
        """
        warnings = []

        # 验证路径
        path_errors = cls.validate_paths()
        warnings.extend(path_errors)

        # 验证最小必备检查
        check_errors = cls.validate_minimal_checks()
        warnings.extend(check_errors)

        return {
            "success": len(warnings) == 0,
            "warnings": warnings,
            "loaded": list(cls._loaded_modules.keys()),
        }
