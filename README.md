# DeepSeek Harness Workspace

## 目录结构

```
deepseek harness workspace/
├── config/                           # 配置文件
│   ├── config.yaml                   # Hermes 主配置
│   └── .env.template                 # 环境变量模板
├── docs/                             # 工作文档
│   ├── qual-workflow-v8.2.md
│   ├── qual-workflow-v8.3.md
│   └── qual-workflow-v8.4.md
├── mcp-servers/                      # MCP 服务器实现
│   ├── finance-calc/                 # 金融计算引擎
│   ├── mcp-shrimp-task-manager/      # 任务管理器
│   ├── nocturne_memory/              # 实体记忆系统
│   └── wind-mcp/                     # Wind 金融数据
├── skills/                           # 技能/知识层
│   ├── finance/
│   │   ├── buy_side_report_review/   # 买方报告审阅
│   │   ├── qual-analysis/            # 核心工作流
│   │   ├── qual-analysis-quality-assurance/
│   │   └── qual-workflow-pitfalls/
│   ├── heavyskill/                   # HeavySkill 引擎
│   ├── heavyskill-optimize/          # HeavySkill 优化
│   ├── software-development/
│   │   └── gate-driven-development/  # HGF 工作流
│   └── workflow-gates/               # Gate 技能封装
├── tools/                            # 可执行代码层
│   └── finance/
│       ├── *.py                      # 核心模块
│       ├── qual_v8/                  # v8 工作流
│       ├── quality/                  # 质量保障
│       ├── valuation/                # 估值引擎
│       └── ...
└── workflow/                         # HGF 工作流引擎
    ├── *.py
    ├── config/
    └── scripts/
```

## 迁移清单

| 层 | 组件 | 文件数 | 状态 |
|---|------|--------|------|
| Skills | qual-analysis + 配套 | 98 | ✅ |
| Skills | buy_side_report_review | 1 | ✅ |
| Skills | heavyskill | 54 | ✅ |
| Skills | heavyskill-optimize | ~20 | ✅ |
| Skills | gate-driven-development | 104 | ✅ |
| Skills | workflow-gates | ~10 | ✅ |
| Tools | finance/ (代码) | ~200 | ✅ |
| Tools | qual_v8/ | ~20 | ✅ |
| Workflow | HGF 引擎 | 22 | ✅ |
| MCP | 4 个服务器 | ~100 | ✅ |
| Config | config.yaml + .env模板 | 2 | ✅ |

## 使用说明

### 1. 环境配置
```bash
cd config/
cp .env.template .env
# 编辑 .env 填入真实 API 密钥
```

### 2. 加载技能
在 DeepSeek Harness 中加载 skills/ 下的 SKILL.md

### 3. 运行 Qual 工作流
```python
from tools.finance.workflow import run_analysis
result = run_analysis(ticker="9868.HK")
```

### 4. 运行 HGF 工作流
```python
from workflow.gate_manager import GateManager
gm = GateManager()
```

## 依赖项

- Python 3.11+
- Wind API (金融数据)
- MinerU API (文档解析)
- DeepSeek API (LLM)

## DSH 技能挂载（2026-08-16 新增）

以下技能按 DeepSeek Harness 的 skill 发现机制挂载到项目根 `.agents/skills/`，
在**以本工作区为 cwd 的会话**中自动发现并进入技能目录（frontmatter 需 `name` kebab-case + `description`）。

| 技能 | 路径 | 功能 |
|------|------|------|
| `heavyskill` | `.agents/skills/heavyskill/SKILL.md` | HeavySkill 多轨迹推理（模式1 子代理模板 / 模式2 Python 流水线） |
| `qual-v8` | `.agents/skills/qual-v8/SKILL.md` | Qual v8.4 工作流 Gate0-8 状态机引擎接入 |
| `hgf` | `.agents/skills/hgf/SKILL.md` | Hermes Gate Flow 门禁驱动开发工作流接入 |

**跨会话可用**：如需在所有 cwd 的会话中可见，把这三个目录拷贝到用户级根
`~/.agents/skills/`（与 `dws` 同级）。

**运行前提**：Python 代码已在 Windows 侧通过 `py_compile` 语法校验；实际运行需要
Python 3 + 依赖（httpx 等）+ `DEEPSEEK_API_KEY` 等密钥（见 `config/.env.template`），
或直接在 WSL 原环境（`/home/lff7767162/.hermes`）中执行。
