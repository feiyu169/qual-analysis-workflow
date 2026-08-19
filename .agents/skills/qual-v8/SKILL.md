---
name: qual-v8
description: >-
  Qual 买方定性分析工作流 v8.4（Gate0-8 状态机引擎）的 DSH 接入技能。当用户要求
  "分析 {公司} / {股票代码} 定性分析 / 买方研究 / 深度研究" 时使用。覆盖数据源验证→
  类型推断→数据收集→章节写作→审计修复→质量增强→结论→问题转化→最终验证九个 Gate，
  含第三方监督、审计日志锚定、熔断降级。依赖 Wind MCP、财报解析、LLM 调用器。
---

# Qual 买方定性分析工作流 v8.4（DSH 接入）

本技能把 hermes 导出的 qual 工作流（`tools/finance/` v2-v7 单体 + `tools/finance/qual_v8/`
Gate0-8 状态机引擎）接入 DSH：说明代码在哪、需要什么环境、如何从 DSH 驱动、以及
必须遵守的纪律。

## 工作流架构

```
用户请求 → Gate0 数据源验证 → Gate1 类型推断 → Gate2 数据收集 → Gate3 章节写作
        → Gate4 审计修复 → Gate5 质量增强 → Gate6 结论 → Gate7 问题转化
        → Gate8 最终验证 → 记忆存储
```

- **v8 引擎**（推荐，生产化）：`tools/finance/qual_v8/` — `QualWorkflow` 类，
  状态机 `core/state_machine.py`、Gate 引擎 `core/gate_engine.py`、第三方监督
  `core/supervisor.py`、审计日志 `core/audit_logger.py`、熔断 `core/circuit_breaker.py`、
  告警/指标 `monitoring/`、Gate0-8 实现 `gates/`。
- **v2-v7 单体**（成熟回退）：`tools/finance/workflow.py` 的 `run_analysis()`
  （107KB 单体：类型推断→数据收集→11 章写作→审计修复→Step4.5 质量增强→组装→记忆）。

## 前置条件（从 DSH 运行前必须满足）

1. **Python 环境**：`tools/finance/.venv`（python3.11，已含 docling/pdfplumber/pandas/
   openai/httpx 等）。Windows 下解释器：`tools\finance\.venv\Scripts\python.exe`。
2. **API 密钥**：参照 `config/.env.template` 设置环境变量——`DEEPSEEK_API_KEY`
   （LLM 调用器 `finance/llm_caller.py` 按 环境变量 → ~/.hermes/.env → config.yaml 的
   gbrain env 顺序读取）、`WIND_API_KEY`（Wind MCP）、`MINERU_TOKEN`（PDF 解析）。
3. **MCP 数据服务**：wind-mcp（行情/估值/财务）、dayu、anysearch（分析师评级）、
   gbrain/flomo/nocturne-memory（记忆）。服务器代码在 `mcp-servers/`，启动方式见
   `config/config.yaml` 的 `mcp_servers` 段。
4. **WSL 提示**：这套环境原本运行在 WSL（`/home/lff7767162/.hermes`）。在 Windows DSH
   侧运行优先用工作区 venv；涉及 Wind/财报下载时建议 `wsl -e python3 ...` 走原环境。

## 从 DSH 驱动（推荐入口）

```powershell
$py = "D:\OneDrive\文档\deepseek harness workspace\tools\finance\.venv\Scripts\python.exe"
cd "D:\OneDrive\文档\deepseek harness workspace\tools\finance"

# 方式1：v8 引擎（Gate0-8 状态机）
& $py -c @"
from qual_v8.workflow import QualWorkflow, WorkflowConfig
wf = QualWorkflow(WorkflowConfig())
result = wf.execute({
    'ticker': '00772.HK', 'company_name': '阅文集团', 'market': 'hk',
    'wind_data': {...}, 'llm_caller': None,  # 见下方纪律：llm_caller 必须配置
})
print(result.get('status'), result.get('report_path'))
"@

# 方式2：v2-v7 单体（成熟回退）
& $py -c @"
from finance.llm_caller import create_deepseek_caller
from finance.filing_downloader import fetch_filing
from finance.workflow import run_analysis
result = run_analysis(
    ticker='1024.HK', company_name='快手', market='hk',
    wind_data=wind_data, filing_data=fetch_filing(ticker='1024.HK', market='hk', limit=1),
    llm_caller=create_deepseek_caller(), shares=43.4,
    output_dir=r'D:\OneDrive\文档\deepseek harness workspace\output',
)
"@
```

## 纪律（hermes 实测沉淀，必须遵守）

- **禁止绕过工作流手动拼凑报告**（P7，最常违反）：工作流失败必须报告失败与根因、
  修复代码、重新执行，不得用 MCP 手动收集数据后自写 6 章顶替 11 章。
- **`llm_caller` 必须配置**：禁止 `llm_caller=None` 产生 placeholder；用
  `finance.llm_caller.create_deepseek_caller()`。
- **每个 ✅ 都要有独立证据**：下载成功→文件 >1024B；解析成功→markdown >0；
  写入成功→读回验证。禁止"自认为通过"（P4/P18）。
- **报告禁用占位符**：`[LLM_GENERATE:...]`、`XX亿元`、`[Placeholder]` 均为失败信号。
- **验证调参不撒谎**：参数调整（WACC/FCF 增速）必须记录"失败→修复→复跑"过程（HGF P4）。
- **重试上限**：审计修复最多 3 轮；辩论机制 `enable_debate=False`（已知卡死问题，
  见 qual-workflow-pitfalls 8.12/8.15）。

## 数据与质量层（可选深度）

- 质量保障体系：`tools/finance/quality/`（96 文件：DCFService、YearAnchor、
  AuthorityResolver 决策矩阵、结论综合、终值仲裁、ROIC-WACC 四象限等 v3 组件）。
- 批判性审阅（最后防线）：`skills/finance/buy_side_report_review/SKILL.md` —
  报告生成后以资深买方视角做红队审阅，输出 P0/P1/P2 清单。
- 深度审查：用 `heavyskill` 技能（K=8）对方案/报告做多轨迹审查。

## 参考文档（工作区）

- 技术方案：`docs/qual-workflow-v8.4.md`（最新）、`docs/qual-workflow-v8.3.md`、`v8.2.md`
- 缺陷清单与修复模式：`skills/finance/qual-workflow-pitfalls/SKILL.md`（Q0-Q3 十七缺陷 + 模式 A-J）
- 质量保障：`skills/finance/qual-analysis-quality-assurance/SKILL.md`（四层防护）
- 主技能定义：`skills/finance/qual-analysis/SKILL.md`（10+1 章、facets、prompts）
