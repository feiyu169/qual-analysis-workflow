"""HGF 准出检查器（V3.3-R3 拆分自 lifecycle.py）。
26 种准出检查器 + _CHECKERS 注册表 + check_exit_criteria。
外部 API 由 lifecycle.py re-export 保持兼容。
"""

import json
import os
import subprocess

# ── 准出条件检查器（V3.2：防"文件存在即通过"）───────────────────────────────


def _read_text(path: str) -> str:
    """编码容忍读取：UTF-8(BOM)/UTF-16/GBK 依次尝试（中文 Windows 文档常见编码）"""
    last_error: Exception | None = None
    for enc in ("utf-8-sig", "utf-16", "gbk"):
        try:
            with open(path, encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, OSError) as e:
            last_error = e
            continue
    raise last_error or UnicodeDecodeError("decode", b"", 0, 1, "未知编码")


def _check_document(gate: dict, working_dir: str, file_hint: str | None) -> tuple:
    """文档类准出：文件存在且内容非空（≥300 有效字符），拒绝空壳文档。

    V3.2.11（Phase 1 诚实化）：阈值从 100 提到 300——长度仍**不是**通过依据，
    只是拒空壳的最低门槛；语义合格性由 _check_document_semantic 按类型校验。
    """
    candidates = []
    if file_hint:
        candidates.append(os.path.join(working_dir, file_hint))
    candidates.append(os.path.join(working_dir, "docs", f"{gate['id']}.md"))
    candidates.append(os.path.join(working_dir, f"{gate['id']}.md"))
    for path in candidates:
        if os.path.exists(path):
            try:
                content = _read_text(path)
            except Exception:
                return False, [f"{path} 无法按常见编码（UTF-8/UTF-16/GBK）读取"]
            if len(content.strip()) < 300:
                return False, [
                    f"{path} 内容过短（{len(content.strip())} 字符），疑似空壳文档"
                ]
            return True, []
    return False, [
        f"未找到 {gate['id']} 的准出文档（--file 指定，或 docs/{gate['id']}.md）"
    ]


# ── V3.2.11 Phase 1 诚实化：文档 gate 语义校验器 ────────────────────────────
# 评审共识 A/H："文件 ≥100 字符即过设计类 gate"是存在性检查冒充语义验证。
# 现按准出类型强制**结构化条目**（组件/数据流/信任边界/STRIDE/端点），
# 长度永远不作为通过依据——只做最低拒空壳门槛（_check_document）。


# 每类准出必须包含的结构条目（组内中英文任一命中即可；组间全部命中）
# 如 "组件"|"component" 是一组：文档含"组件"或"component"均算命中。
_DOC_SEMANTIC_REQUIREMENTS: dict[str, list[list[str]]] = {
    "architecture_document": [
        ["组件", "component"],
        ["数据流", "data flow"],
        ["信任边界", "trust boundary"],
        ["接口", "interface"],
    ],
    "threat_model": [
        ["STRIDE"],
        ["威胁", "threat"],
        ["缓解", "mitigat"],
        ["攻击面", "attack surface"],
    ],
    "api_definition": [
        ["端点", "endpoint"],
        ["请求", "request"],
        ["响应", "response"],
        ["schema", "OpenAPI"],
    ],
    "detailed_design": [
        ["模块", "module"],
        ["状态", "state"],
        ["错误处理", "error handling"],
        ["边界", "boundary"],
    ],
    "security_requirements": [
        ["认证", "authentication"],
        ["授权", "authorization"],
        ["机密性", "confidentiality"],
        ["完整性", "integrity"],
    ],
    "data_desensitization": [
        ["脱敏", "desensitiz", "masking"],
        ["字段", "field"],
        ["敏感", "sensitive"],
    ],
    "deployment_checklist": [
        ["部署", "deploy"],
        ["环境", "environment"],
        ["回滚", "rollback"],
        ["配置", "config"],
    ],
    "key_rotation": [
        ["轮换", "rotation"],
        ["密钥", "key"],
        ["过期", "expir"],
        ["吊销", "revoke"],
    ],
    "monitoring_configured": [
        ["监控", "monitor"],
        ["指标", "metric"],
        ["告警", "alert"],
        ["SLO"],
    ],
}


def _check_document_semantic(
    gate: dict, working_dir: str, file_hint: str | None
) -> tuple:
    """语义化文档准出：在 _check_document 之上，按准出类型强制结构条目。

    规则（V3.2.11 Phase 1）：
    - 先过 _check_document 基础门槛（非空壳）；
    - 该 gate 的 exit_criteria 中有已知语义模板的 type → 文档必须命中
      全部条目组（每组内中英文任一命中即可，如"组件"或"component"）；
    - 缺条目组 → FAIL（带缺失清单），**长度满足但条目缺失不通过**。
    """
    ok, issues = _check_document(gate, working_dir, file_hint)
    if not ok:
        return ok, issues

    path = None
    if file_hint and os.path.exists(os.path.join(working_dir, file_hint)):
        path = os.path.join(working_dir, file_hint)
    else:
        for cand in (
            os.path.join(working_dir, "docs", f"{gate['id']}.md"),
            os.path.join(working_dir, f"{gate['id']}.md"),
        ):
            if os.path.exists(cand):
                path = cand
                break
    content = _read_text(path) if path else ""

    # 收集本 gate 所有准出 type 的必需条目组
    groups = []
    for criterion in gate.get("exit_criteria") or []:
        ctype = criterion.get("type", "")
        groups.extend(_DOC_SEMANTIC_REQUIREMENTS.get(ctype, []))

    if not groups:
        # 该 gate 无语义模板（如 document_generated 本身）→ 仅过基础门槛
        return True, []

    content_lower = content.lower()
    missing = [
        "/".join(g) for g in groups if not any(k.lower() in content_lower for k in g)
    ]
    if missing:
        return False, [
            f"{path} 缺少语义条目 {len(missing)}/{len(groups)} 组: "
            + ", ".join(missing)
            + "（长度满足但结构不合格，拒绝通过）"
        ]
    return True, []


def _check_review(gate: dict, working_dir: str, file_hint: str | None) -> tuple:
    """评审类准出：.hgf/reviews.jsonl 中存在该 gate 的评审通过记录。

    V3.2.5 信任要求：记录必须带双签名 reviewer（执行者）与 verifier
    （独立评审者），两者均非空且不相同——防止 agent 自签评审冒充独立审查。
    V3.2.11（Phase 2 权威化）：评审诚实化——user_acceptance 类 gate
    拒绝 self-check（被审对象不得自证通过）。
    """
    p = os.path.join(working_dir, ".hgf", "reviews.jsonl")
    if not os.path.exists(p):
        return False, ["评审记录 .hgf/reviews.jsonl 不存在"]
    with open(p, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            rec = json.loads(line)
            if rec.get("gate") != gate["id"] or rec.get("verdict") != "pass":
                continue
            reviewer = (rec.get("reviewer") or "").strip()
            verifier = (rec.get("verifier") or "").strip()
            if not reviewer or not verifier:
                return False, [
                    f"{gate['id']} 的评审记录缺少双签名（需 reviewer 与 verifier）"
                ]
            if reviewer == verifier:
                return False, [
                    f"{gate['id']} 的评审记录 reviewer 与 verifier 相同，"
                    "非独立评审（自签无效）"
                ]
            # V3.2.11：user_acceptance/review_checklist 拒绝 self-check
            kind = rec.get("kind", "independent")
            if kind == "self-check" and gate["id"] in (
                "user_acceptance",
                "review_checklist",
            ):
                return False, [
                    f"{gate['id']} 拒绝 self-check（被审对象不得自证通过）——"
                    "需 independent 独立评审记录"
                ]
            # V3.2.11（待办 4）：user_acceptance 需**真实人工证据**——
            # 独立评审记录之外，还必须有用户确认文件（人工通道落地：
            # agent 不得仅凭自签/双签名记录通过验收）。
            if gate["id"] == "user_acceptance":
                human_evidence = False
                candidates = [
                    os.path.join(working_dir, "docs", "user_acceptance.md"),
                    os.path.join(working_dir, "user_acceptance.md"),
                ]
                if file_hint:
                    candidates.insert(0, os.path.join(working_dir, file_hint))
                for cand in candidates:
                    if os.path.exists(cand):
                        try:
                            content = _read_text(cand)
                        except Exception:
                            continue
                        # 人工确认文件需含"验收"且长度合理（≥100 字符），
                        # 避免空文件充当证据
                        if len(content.strip()) >= 100 and "验收" in content:
                            human_evidence = True
                            break
                if not human_evidence:
                    return False, [
                        "user_acceptance 需要人工验收证据：docs/user_acceptance.md"
                        "（含'验收'结论，≥100 字符）或 --file 指定——agent "
                        "不得仅凭评审记录通过验收（V3.2.11 人工通道）"
                    ]
            return True, []
    return False, [f"评审记录中无 {gate['id']} 的通过结论"]


def _check_unit_tests(gate: dict, working_dir: str, file_hint: str | None) -> tuple:
    """L1 真实执行：pytest 必须通过（禁止'存在即通过'）

    V3.2.11 分层：只跑 unit 标记（tests/ 下无标记的测试视为 unit）。
    V3.2.11 修复：参数数组 + shell=False——此前 shell=True 字符串命令的
    引号被 shell 拆掉（`-m 'not integration and not e2e'` → 语法错误
    "no tests ran"），狗粮化 gate_2_1 拦截时发现。
    """
    try:
        r = subprocess.run(
            [
                "pytest",
                "tests/",
                "-q",
                "-m",
                "not integration and not e2e",
            ],
            capture_output=True,
            text=True,
            cwd=working_dir,
            timeout=300,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except Exception as e:
        return False, [f"pytest 执行失败: {e}"]
    if r.returncode != 0:
        tail = r.stdout.strip().splitlines()[-5:] if r.stdout.strip() else []
        return False, ["pytest 未通过: " + " | ".join(tail)]
    return True, []


def _check_integration_tests(
    gate: dict, working_dir: str, file_hint: str | None
) -> tuple:
    """L2 集成测试真检查器（V3.2.11 Phase 1 诚实化，修评审共识 B）。

    此前 integration_test_passed 与 unit_test_passed 共用 _check_unit_tests——
    声明 L2"真实数据端到端"实际跑 L1 单测，属类别欺诈。现改为：
    - 要求存在 tests/integration/ 或 tests/ 下带 @pytest.mark.integration 的用例；
    - 真跑 `pytest -m integration`（无集成测试 → FAIL，不允许空跑通过）；
    - 若配置了 e2e 目录/标记也一并跑。
    """
    import glob

    integration_dir = os.path.join(working_dir, "tests", "integration")
    has_dir = os.path.isdir(integration_dir) and glob.glob(
        os.path.join(integration_dir, "test_*.py")
    )
    has_marker = False
    marker_file = os.path.join(working_dir, "tests", "conftest.py")
    if os.path.exists(marker_file):
        with open(marker_file, encoding="utf-8", errors="replace") as f:
            has_marker = "integration" in f.read()

    if not has_dir and not has_marker:
        return False, [
            "无集成测试证据：需 tests/integration/ 目录或 @pytest.mark.integration "
            "标记（集成测试不再用单测冒充——V3.2.11）"
        ]

    cmds = []
    if has_dir:
        cmds.append(["pytest", "tests/integration/", "-q"])
    if has_marker:
        cmds.append(["pytest", "tests/", "-q", "-m", "integration"])
    for cmd in cmds:
        try:
            r = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=working_dir,
                timeout=600,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
        except Exception as e:
            return False, [f"集成测试执行失败: {e}"]
        if r.returncode != 0:
            tail = r.stdout.strip().splitlines()[-5:] if r.stdout.strip() else []
            return False, ["集成测试未通过: " + " | ".join(tail)]
    return True, []


def _check_static(gate: dict, working_dir: str, file_hint: str | None) -> tuple:
    """L1 真实执行：ruff 必须 0 错误（V3.3-R2：argv 数组 + shell=False）"""
    try:
        from . import tool_runner as _runner
    except ImportError:
        import tool_runner as _runner
    try:
        r = _runner.safe_run(["ruff", "check", "."], working_dir, timeout=120)
    except Exception as e:
        return False, [f"ruff 执行失败: {e}"]
    if r.returncode != 0:
        return False, [
            "ruff 发现静态分析问题: " + (r.stdout.strip().splitlines()[-1] or "")
        ]
    return True, []


def _check_health(gate: dict, working_dir: str, file_hint: str | None) -> tuple:
    """健康/监控类准出（V3.2.11 Phase 3：真实探针替代裸确认，修评审共识 G）。

    优先级：
    1. gate 配置的 probe_command（真实执行，返回 0 → 通过）——最优先；
    2. scripts/probes/<type>.py 探针脚本（存在则真实执行）；
    3. --file 提供健康检查输出文件；
    4. 以上皆无 → FAIL（不再接受裸 --confirm 跳过——confirm 必须附证据文件，
       由 check_exit_criteria 的 confirm 参数配套 enforce_confirm_evidence）。
    """
    try:
        from . import tool_runner as _runner
    except ImportError:
        import tool_runner as _runner

    # 1) gate 配置的探针命令（V3.3-R2：split_command 拆 argv + safe_run shell=False；
    #    配置者可写简单命令如 "healthcheck.sh --port 8080"；复杂 shell 语法
    #    （管道/重定向）需改为脚本探针 scripts/probes/<type>.py）
    probe_cmd = (gate.get("probe_command") or "").strip()
    if probe_cmd:
        argv = _runner.split_command(probe_cmd)
        if not argv:
            return False, ["probe_command 为空，拒绝判定"]
        try:
            r = _runner.safe_run(argv, working_dir, timeout=120)
        except Exception as e:
            return False, [f"健康探针执行失败: {e}"]
        if r.returncode != 0:
            tail = (r.stdout or r.stderr).strip().splitlines()[-3:]
            return False, ["健康探针未通过: " + " | ".join(tail)]
        return True, []

    # 2) scripts/probes/<type>.py 探针脚本
    ctype = ""
    for criterion in gate.get("exit_criteria") or []:
        ctype = criterion.get("type", "")
        break
    probe_path = os.path.join(working_dir, "scripts", "probes", f"{ctype}.py")
    if ctype and os.path.exists(probe_path):
        import shutil

        try:
            r = _runner.safe_run(
                [shutil.which("python") or "python", probe_path],
                working_dir,
                timeout=120,
            )
        except Exception as e:
            return False, [f"健康探针脚本执行失败: {e}"]
        if r.returncode != 0:
            tail = (r.stdout or r.stderr).strip().splitlines()[-3:]
            return False, ["健康探针未通过: " + " | ".join(tail)]
        return True, []

    # 3) --file 证据
    if file_hint and os.path.exists(os.path.join(working_dir, file_hint)):
        return True, []

    return False, [
        "健康/监控准出需要真实证据：配置 probe_command，或 "
        "scripts/probes/<type>.py 探针，或 --file 输出文件（V3.2.11："
        "不再接受裸 --confirm 跳过）"
    ]


def _check_tool_scan(
    gate: dict,
    working_dir: str,
    file_hint: str | None,
    tool: str,
    command: str,
    timeout: int = 300,
    label: str = "",
) -> tuple:
    """通用安全/扫描类准出真检查器（V3.2.9 修复 A/J）。

    此前 sast_scan/dependency_scan 等准出被映射到 ruff/pytest 兜底，
    名义是安全扫描、实质是 lint——"名不副实"（评审 A/J）。现改为：
    - 工具必须存在（shutil.which），缺失 → FAIL（fail-loud，不静默通过）；
    - 真实执行工具命令（V3.3-R2：经 tool_runner 的 argv 数组 + shell=False，
      与 gate_plugin 统一，消除 shell=True 遗留），返回码 0 → 通过，
      非 0 → FAIL（附输出尾部）；
    - 执行异常/超时 → FAIL（附原因），绝不把环境故障当代码质量信号。
    """
    try:
        from . import tool_runner as _runner
    except ImportError:
        import tool_runner as _runner
    if not _runner.check_tool_available(tool):
        return False, [
            f"{label or tool} 工具未安装（PATH 中无 {tool}），"
            f"无法执行 {gate.get('id', '?')} 的准出验证——拒绝判定（fail-loud）"
        ]
    argv = _runner.split_command(command)
    if not argv:
        return False, [f"{label or tool} 命令为空，拒绝判定"]
    try:
        r = _runner.safe_run(argv, working_dir, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, [f"{label or tool} 执行超时（>{timeout}s），拒绝判定"]
    except Exception as e:
        return False, [f"{label or tool} 执行失败: {e}"]
    if r.returncode != 0:
        tail = (r.stdout or r.stderr).strip().splitlines()[-3:]
        return False, [f"{label or tool} 未通过: " + " | ".join(tail)]
    return True, []


def _check_semgrep(gate, working_dir, file_hint) -> tuple:
    """SAST 准出真检查器：semgrep 真跑（此前为 ruff 兜底，名不副实）"""
    return _check_tool_scan(
        gate,
        working_dir,
        file_hint,
        tool="semgrep",
        command="semgrep --config=p/r2c-ci --json .",
        timeout=300,
        label="SAST(semgrep)",
    )


def _check_dependency(gate, working_dir, file_hint) -> tuple:
    """依赖漏洞准出真检查器：safety 真跑（此前为 pytest 兜底，名不副实）。

    注意：safety 在线扫描需要 SAFETY_API_KEY 且可能被限流；失败时如实
    报告原因（FAIL），不会把"跑了个测试"当作"依赖已扫描"。

    V3.2.11（狗粮化验收发现）：**零第三方依赖项目直接通过**——requirements.txt
    无实质依赖（无 `==`/`>=`/`~=` 等版本行）时无扫描目标，0 依赖 = 0 漏洞，
    这是客观事实而非静默降级；有依赖才跑 safety。
    """
    req_path = os.path.join(working_dir, "requirements.txt")
    has_deps = False
    if os.path.exists(req_path):
        with open(req_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                if any(mark in line for mark in ("==", ">=", "<=", "~=", ">", "<")):
                    has_deps = True
                    break
    if not has_deps:
        return True, ["零第三方依赖（无版本约束行），依赖扫描通过"]
    return _check_tool_scan(
        gate,
        working_dir,
        file_hint,
        tool="safety",
        command="safety check --json",
        timeout=120,
        label="依赖扫描(safety)",
    )


def _check_checkov(gate, working_dir, file_hint) -> tuple:
    """IaC 安全审计准出真检查器：checkov 真跑（此前为 ruff 兜底）。

    V3.3.1（狗粮化发现）：无 IaC 资产（无 .tf/.tfvars/cloudformation/k8s 文件）
    → 直通（无审计目标，客观事实非静默降级）；有资产才跑 checkov。
    """
    import glob as _glob

    ia_c_patterns = (
        "*.tf",
        "*.tfvars",
        "*.template",
        "cloudformation/**",
        "k8s/**",
        "terraform/**",
    )
    has_iac = any(_glob.glob(os.path.join(working_dir, p)) for p in ia_c_patterns)
    if not has_iac:
        return True, ["无 IaC 资产（Terraform/CloudFormation/K8s），IaC 审计通过"]
    return _check_tool_scan(
        gate,
        working_dir,
        file_hint,
        tool="checkov",
        command="checkov -d . --output json",
        timeout=300,
        label="IaC审计(checkov)",
    )


def _check_dast(gate, working_dir, file_hint) -> tuple:
    """DAST 准出：本环境未内置 DAST 工具，需 --file 提供外部 DAST 扫描报告
    或 --confirm 人工确认——显式标注，绝不静默通过。"""
    if file_hint and os.path.exists(os.path.join(working_dir, file_hint)):
        return True, []
    return False, [
        "DAST 准出需要外部扫描报告（--file，如 OWASP ZAP 输出）或 --confirm 人工确认"
    ]


def _check_tdd_evidence(gate: dict, working_dir: str, file_hint: str | None) -> tuple:
    """TDD 证据真检查器（V3.2.8）：git 历史中测试文件首次提交必须早于（或等于）
    实现文件首次提交。此前是 review 兜底，现改为真实 git 历史验证。"""
    import subprocess

    tests_dir = os.path.join(working_dir, "tests")
    if not os.path.isdir(tests_dir):
        return False, ["无 tests/ 目录，无法验证 TDD 证据"]

    def first_add(path: str) -> str | None:
        r = subprocess.run(
            ["git", "log", "--diff-filter=A", "--format=%aI", "--", path],
            cwd=working_dir,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
            check=False,
        )
        lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
        return lines[-1] if lines else None  # 时间升序，最后一行最早

    try:
        test_time = first_add(tests_dir)
        if not test_time:
            return False, ["tests/ 无 git 提交记录（git 仓库未初始化或未提交）"]
        impl_time = first_add(".")
        if not impl_time:
            return True, []  # 只有测试，视为 TDD
        if test_time <= impl_time:
            return True, []
        return False, [
            f"测试首次提交 {test_time} 晚于实现首次提交 {impl_time}（非 TDD，测试应先于实现）"
        ]
    except Exception as e:
        return False, [f"TDD 证据验证失败（需 git 仓库）: {e}"]


_CHECKERS = {
    "document_generated": _check_document,
    # V3.2.11 Phase 1 诚实化：设计/安全/部署类文档 gate 升级为语义校验
    # （结构条目强制，长度不再是通过依据——修评审共识 A/H）
    "security_requirements": _check_document_semantic,
    "architecture_document": _check_document_semantic,
    "threat_model": _check_document_semantic,
    "api_definition": _check_document_semantic,
    "detailed_design": _check_document_semantic,
    "automated_review": _check_document_semantic,
    "review_checklist": _check_document_semantic,
    "data_desensitization": _check_document_semantic,
    "deployment_checklist": _check_document_semantic,
    "key_rotation": _check_document_semantic,
    "monitoring_configured": _check_document_semantic,
    "review_passed": _check_review,
    "manual_review": _check_review,
    "user_acceptance": _check_review,
    "feedback_collected": _check_review,
    "unit_test_passed": _check_unit_tests,
    "integration_test_passed": _check_integration_tests,  # V3.2.11：真验 L2（分层测试）
    "static_analysis": _check_static,
    "sast_scan": _check_semgrep,  # V3.2.9：真跑 semgrep（此前 ruff 兜底，名不副实）
    "dast_scan": _check_dast,  # V3.2.9：需外部 DAST 报告或 --confirm
    "iac_security_audit": _check_checkov,  # V3.2.9：真跑 checkov（此前 ruff 兜底）
    "dependency_scan": _check_dependency,  # V3.2.9：真跑 safety（此前 pytest 兜底）
    "tdd_evidence": _check_tdd_evidence,  # V3.2.8：git 历史真实验证测试先于实现
    "health_check": _check_health,
    "monitoring_normal": _check_health,
}


def check_exit_criteria(
    gate: dict, working_dir: str, file_hint: str | None, confirm: bool = False
) -> tuple:
    """执行 gate 的全部准出条件检查；confirm 允许人工确认兜底。

    V3.2.11（Phase 3，修评审共识 G）：--confirm 不再接受裸布尔——必须有
    --file 证据文件才允许覆盖无检查器的准出（"确认"必须有据可查）。
    """
    issues = []
    for criterion in gate.get("exit_criteria") or []:
        ctype = criterion.get("type", "")
        checker = _CHECKERS.get(ctype)
        if checker is None:
            if (
                confirm
                and file_hint
                and os.path.exists(os.path.join(working_dir, file_hint))
            ):
                continue
            if confirm and not file_hint:
                issues.append(
                    f"准出条件 [{ctype}] 无自动检查器：--confirm 需附 --file "
                    "证据文件（V3.2.11：禁止裸布尔确认）"
                )
            elif confirm and file_hint:
                issues.append(
                    f"准出条件 [{ctype}] 无自动检查器：--confirm 的 --file 证据"
                    f"不存在（{file_hint}）"
                )
            else:
                issues.append(
                    f"准出条件 [{ctype}] 无自动检查器，需 --confirm --file <证据>"
                )
            continue
        ok, errs = checker(gate, working_dir, file_hint)
        if not ok:
            issues.extend(errs)
    return (len(issues) == 0), issues
