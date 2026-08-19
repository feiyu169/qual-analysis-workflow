# Mutmut 变异测试设置与陷阱

## Python 版本兼容性

mutmut 3.x 需要 Python 3.9+。如果系统默认 Python 是 3.8：

```bash
# 创建 Python 3.11 venv
cd <project_dir>
uv venv .venv --python 3.11
.venv/bin/python3.11 -m ensurepip
.venv/bin/python3.11 -m pip install mutmut pytest hypothesis
```

## pyproject.toml 配置

```toml
[tool.mutmut]
source_paths = ["target_module.py"]  # 注意：不是 paths_to_mutate（已弃用）
timeout = 30
also_copy = ["conftest.py"]  # 必须复制到 mutants/ 目录

[tool.pytest.ini_options]
testpaths = ["tests"]
```

## 关键陷阱：相对导入不兼容

**问题**：mutmut 在 `mutants/` 子目录运行测试，相对导入 `from ..module import` 会失败。

**根因**：mutmut 创建 `mutants/` 目录复制源文件，pytest 从该目录运行时无法解析包结构。

**解决方案**：
1. 测试文件使用直接导入 `from module import ...`（非相对导入）
2. 源文件使用 try/except 兼容导入：
```python
try:
    from .state_machine import GateStateMachine
except ImportError:
    from state_machine import GateStateMachine
```
3. 根级 `conftest.py` 添加 sys.path：
```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
```

## 关键陷阱：模块身份冲突

**问题**：pytest 以包方式加载 `workflow.state_machine`，但测试文件直接导入 `state_machine`，产生两个不同的模块实例。导致枚举比较失败（`GateStatus.PENDING is not GateStatus.PENDING`）。

**症状**：`Invalid transition: pending -> in_progress` 错误，尽管 VALID_TRANSITIONS 表明这是合法转移。

**解决方案**：conftest.py 和所有测试文件必须使用相同的导入风格。推荐全部使用直接导入（非相对），配合根级 conftest.py 的 sys.path 设置。

## 运行命令

```bash
# 运行变异测试
.venv/bin/python3.11 -m mutmut run

# 查看结果
.venv/bin/python3.11 -m mutmut results

# 统计杀死率
.venv/bin/python3.11 -m mutmut results 2>&1 | grep -c "killed"
.venv/bin/python3.11 -m mutmut results 2>&1 | grep -c "survived"
```

## 实战数据（state_machine.py）

- 总变异体：187
- 基线杀死率：48.1%（90/187）
- 执行速度：~28 mutations/second
- 目标：≥80%
