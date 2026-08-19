"""
任务分级器 - V5 方案实现
根据任务规模、变更类型、关键模块、风险评估进行分级
"""

import re
from dataclasses import dataclass

import structlog

logger = structlog.get_logger()


@dataclass
class Task:
    """任务数据"""

    description: str
    files: list[str]
    file_count: int
    line_count: int
    affected_areas: list[str] | None = None
    labels: list[str] | None = None
    commit_messages: list[str] | None = None
    diff_stats: dict | None = None


@dataclass
class ClassificationResult:
    """分级结果"""

    level: str
    type: str
    types: list[str] | None = None
    risk: str | None = None
    change_lines: int | None = None


class TaskClassifierError(Exception):
    """任务分级错误"""


class TaskClassifier:
    """任务分级器"""

    # 等级排序：L0 > L3 > L3_lite > L2 > L1
    LEVEL_ORDER = {
        "L0": 5,
        "L3": 4,
        "L3_LITE": 3,
        "L2": 2,
        "L1": 1,
        "DOCS": -1,
        "CONFIG": -1,
        "IAC": -1,
    }

    # 文件过滤规则
    IGNORE_PATTERNS = [
        "vendor/",
        "node_modules/",
        "*.pb.go",
        "*.min.js",
        "tests/",
        "test/",
        "__tests__/",
        "spec/",
        ".git/",
        "__pycache__/",
        "*.pyc",
    ]

    # 代码文件扩展名
    CODE_EXTENSIONS = {".py", ".js", ".ts", ".go", ".java", ".rs", ".c", ".cpp", ".h"}

    # IaC 文件扩展名
    IAC_EXTENSIONS = {".tf", ".tfvars", ".template"}
    IAC_DIRS = ["terraform/", "cloudformation/", "k8s/"]

    # 配置文件扩展名
    CONFIG_EXTENSIONS = {".yaml", ".yml", ".json", ".toml", ".ini", ".env"}
    CONFIG_DIRS = ["config/", "settings/"]

    # 文档文件扩展名
    DOC_EXTENSIONS = {".md", ".rst", ".txt"}
    DOC_DIRS = ["docs/", "documentation/"]

    # 热修复关键词
    HOTFIX_KEYWORDS = [
        "hotfix",
        "emergency",
        "urgent",
        "critical",
        "线上故障",
        "安全漏洞",
        "数据损坏",
        "紧急修复",
        "sev0",
        "sev1",
        "incident",
        "outage",
    ]

    # 关键模块（可配置）
    CRITICAL_MODULES = [
        "auth",
        "authentication",
        "authorization",
        "payment",
        "billing",
        "database",
        "db",
        "migration",
        "core",
        "kernel",
        "engine",
        "security",
        "crypto",
    ]

    def __init__(self, config: dict = None):
        """初始化分级器"""
        if config:
            self.IGNORE_PATTERNS = config.get(
                "ignore_patterns", self.__class__.IGNORE_PATTERNS
            )
            self.CRITICAL_MODULES = config.get(
                "critical_modules", self.__class__.CRITICAL_MODULES
            )

    def classify_task(self, task: Task) -> ClassificationResult:
        """
        任务分级

        Args:
            task: 任务数据

        Returns:
            ClassificationResult: 分级结果

        Raises:
            TaskClassifierError: 分级失败
        """
        # 输入验证
        self._validate_task(task)

        try:
            # 0. 紧急热修复检查
            if self.is_hotfix(task):
                logger.info("task_classified", level="L0", type="CODE", reason="hotfix")
                return ClassificationResult(level="L0", type="CODE", risk="high")

            # 1. 变更类型检测（支持混合类型）
            change_types = self.detect_change_types(task)
            logger.info("change_types_detected", types=change_types)

            # 2. 纯非代码变更直接返回
            if change_types == ["DOCS"]:
                logger.info("task_classified", level="DOCS", type="DOCS")
                return ClassificationResult(level="DOCS", type="DOCS")
            if change_types == ["CONFIG"]:
                logger.info("task_classified", level="CONFIG", type="CONFIG")
                return ClassificationResult(level="CONFIG", type="CONFIG")
            if change_types == ["IAC"]:
                logger.info("task_classified", level="IAC", type="IAC")
                return ClassificationResult(level="IAC", type="IAC")

            # 3. 规模分级（仅统计代码文件）
            change_lines = self.get_change_lines(task, change_types)
            level = "L1"

            if task.file_count > 10 or change_lines > 500:
                level = "L3"
            elif task.file_count > 3 or change_lines > 100:
                level = "L2"

            logger.info(
                "scale_classified",
                file_count=task.file_count,
                change_lines=change_lines,
                level=level,
            )

            # 4. 关键模块检查
            if self.is_critical_module(task.affected_areas or []):
                level = self.max_level(level, "L2")
                logger.info("critical_module_upgrade", level=level)

            # 5. 风险评估
            risk = self._assess_risk_level(task)
            logger.info("risk_assessed", risk=risk)

            # 6. 风险升级
            if risk == "high":
                if task.file_count <= 3 and change_lines <= 100:
                    level = "L3_LITE"
                else:
                    level = "L3"
                logger.info("risk_upgrade", level=level, reason="high_risk")
            elif risk == "medium" and level == "L1":
                level = "L2"
                logger.info("risk_upgrade", level=level, reason="medium_risk")

            # 7. 混合类型处理
            if len(change_types) > 1:
                logger.info(
                    "task_classified",
                    level=level,
                    type="MIXED",
                    types=change_types,
                    risk=risk,
                )
                return ClassificationResult(
                    level=level,
                    type="MIXED",
                    types=change_types,
                    risk=risk,
                    change_lines=change_lines,
                )

            logger.info("task_classified", level=level, type=change_types[0], risk=risk)
            return ClassificationResult(
                level=level,
                type=change_types[0] if change_types else "CODE",
                risk=risk,
                change_lines=change_lines,
            )

        except Exception as e:
            logger.error("classification_failed", error=str(e))
            raise TaskClassifierError(f"任务分级失败: {e!s}")

    def _validate_task(self, task: Task):
        """验证任务输入"""
        if not task:
            raise TaskClassifierError("任务不能为空")

        if not task.description:
            raise TaskClassifierError("任务描述不能为空")

        if not task.files:
            raise TaskClassifierError("任务文件列表不能为空")

        if task.file_count < 0:
            raise TaskClassifierError("文件数量不能为负数")

        if task.line_count < 0:
            raise TaskClassifierError("行数不能为负数")

    def is_hotfix(self, task: Task) -> bool:
        """检查是否为紧急热修复"""
        description_lower = task.description.lower()

        # 检查描述关键词
        for keyword in self.HOTFIX_KEYWORDS:
            if keyword in description_lower:
                return True

        # 检查标签
        if task.labels:
            for label in task.labels:
                if label.lower() in self.HOTFIX_KEYWORDS:
                    return True

        # 检查 PR 标题格式（如 sev0, sev1）
        return bool(re.search(r"^sev[0-1]", description_lower))

    def detect_change_types(self, task: Task) -> list[str]:
        """检测变更类型（支持多类型）"""
        types = set()

        for file in task.files:
            # 只过滤非代码相关的文件（vendor, node_modules, .git 等）
            # 测试文件不应被忽略，它们是代码变更的一部分
            ignore_for_type_detection = [
                "vendor/",
                "node_modules/",
                "*.pb.go",
                "*.min.js",
                ".git/",
                "__pycache__/",
                "*.pyc",
            ]
            if any(pattern in file for pattern in ignore_for_type_detection):
                continue

            # 代码文件
            if any(file.endswith(ext) for ext in self.CODE_EXTENSIONS):
                types.add("CODE")

            # IaC 文件
            if any(file.endswith(ext) for ext in self.IAC_EXTENSIONS):
                types.add("IAC")
            if any(d in file for d in self.IAC_DIRS):
                types.add("IAC")

            # 配置文件
            if any(file.endswith(ext) for ext in self.CONFIG_EXTENSIONS):
                types.add("CONFIG")
            if any(d in file for d in self.CONFIG_DIRS):
                types.add("CONFIG")

            # 文档文件
            if any(file.endswith(ext) for ext in self.DOC_EXTENSIONS):
                types.add("DOCS")
            if any(d in file for d in self.DOC_DIRS):
                types.add("DOCS")

        return list(types) if types else ["CODE"]

    def get_change_lines(self, task: Task, change_types: list[str]) -> int:
        """
        计算变更行数（仅统计代码文件）

        注意：当 diff_stats 不存在时，返回的是"每文件平均行数"而非总行数。
        这是一个估算值，用于分级决策，不是精确统计。

        Args:
            task: 任务数据
            change_types: 变更类型列表

        Returns:
            int: 变更行数估算值
        """
        # 如果有 diff_stats，直接使用
        if task.diff_stats:
            return task.diff_stats.get("additions", 0) + task.diff_stats.get(
                "deletions", 0
            )

        # 如果是纯非代码变更，不计算行数
        if change_types and all(t in ["DOCS", "CONFIG", "IAC"] for t in change_types):
            return 0

        # 过滤代码文件，计算行数
        code_file_count = 0
        for file in task.files:
            if self._should_ignore(file):
                continue
            if any(file.endswith(ext) for ext in self.CODE_EXTENSIONS):
                code_file_count += 1

        if code_file_count == 0:
            return 0

        # 按代码文件数平均分配行数（更准确的估算）
        return task.line_count // code_file_count

    def is_critical_module(self, affected_areas: list[str]) -> bool:
        """检查是否涉及关键模块"""
        if not affected_areas:
            return False

        for area in affected_areas:
            area_lower = area.lower()
            for module in self.CRITICAL_MODULES:
                if module in area_lower:
                    return True

        return False

    def max_level(self, level1: str, level2: str) -> str:
        """
        返回较高等级

        Args:
            level1: 等级1
            level2: 等级2

        Returns:
            str: 较高等级
        """
        order1 = self.LEVEL_ORDER.get(level1, 0)
        order2 = self.LEVEL_ORDER.get(level2, 0)

        return level1 if order1 >= order2 else level2

    def _assess_risk_level(self, task: Task) -> str:
        """评估风险等级（委托给 RiskAssessor）"""
        try:
            try:
                from .risk_assessor import RiskAssessor
            except ImportError:
                from risk_assessor import RiskAssessor
        except ImportError:
            from risk_assessor import RiskAssessor
        assessor = RiskAssessor()
        result = assessor.assess_risk(
            affected_areas=task.affected_areas or [], description=task.description
        )
        return result.risk

    def _should_ignore(self, file: str) -> bool:
        """检查文件是否应该忽略"""
        for pattern in self.IGNORE_PATTERNS:
            if pattern in file:
                return True
        return False
