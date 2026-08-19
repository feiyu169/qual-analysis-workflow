"""LLM 调用降级封装（with_fallback）：桥接优先，滑动窗口降级直连。

v3.1 P0-2：独立模块（原为 run_qual_full.py / run_xpev_full.py 内联 _llm_with_fallback）。
v3.1 P0-4：白名单 `(LLMCallBudgetExceeded, WallClockDeadlineExceeded)` 先于
           `except DeterministicLLMFailure`——预算/墙钟耗尽不换模型重试（子类遮蔽修复）。
v3.1 P0-5：逃生直连调用前过 deadline 预检（monotonic()>deadline → raise
           WallClockDeadlineExceeded，不再发起在途超支，可证明上界收敛）。

错误分类（docs/qual-loop-fix-design-v3-arch.md §2.1）：
- 瞬态（网络/连接/超时）→ 窗口内累计失败 ≥ fail_threshold 或已切换 → 换直连
- 确定性（DeterministicLLMFailure）→ 换路由单次逃生（成功输出附加 degrade_marker）
- 预算/墙钟（白名单子类）→ 不重试，原样上抛（fail-closed）
"""
from collections import deque
from collections.abc import Callable

from .llm_errors import (
    DeterministicLLMFailure,
    LLMCallBudgetExceeded,
    WallClockDeadlineExceeded,
)


def with_fallback(
    primary: Callable[[str, str], str],
    direct_factory: Callable[[], Callable[[str, str], str]] | None = None,
    *,
    fail_threshold: int = 4,         # 滑动窗口内失败数阈值（v3.1 P0-2：4/8）
    window: int = 8,                 # 滑动窗口大小（最近 N 次调用）
    deadline: float | None = None,   # 墙钟 deadline（time.monotonic() 值），逃生预检用
    degrade_marker: str = "",        # 直连输出附加标记（报告打标，默认空）
) -> Callable[[str, str], str]:
    """桥接优先，滑动窗口降级直连。

    primary 窗口内失败达阈值（或已切换）后，调用 direct_factory() 构造直连 caller 逃生；
    已切换后后续失败直接走直连。确定性失败换路由单次逃生；预算/墙钟耗尽原样上抛。
    """
    import time as _time

    hist: deque[bool] = deque(maxlen=window)
    direct: Callable[[str, str], str] | None = None

    def _deadline_guard_escape() -> None:
        """逃生调用发起前墙钟预检（v3.1 P0-5）"""
        if deadline is not None and _time.monotonic() > deadline:
            raise WallClockDeadlineExceeded(
                f"逃生直连前墙钟预算耗尽（deadline={deadline:.0f}，当前={_time.monotonic():.0f}）"
            )

    def _switch() -> None:
        nonlocal direct
        if direct is None and direct_factory is not None:
            direct = direct_factory()

    def caller(chapter_name: str, prompt: str) -> str:
        nonlocal direct
        try:
            text = primary(chapter_name, prompt)
            hist.append(False)  # 成功不清零（K4 滑动语义）
            return text
        except (LLMCallBudgetExceeded, WallClockDeadlineExceeded):
            # v3.1 P0-4：白名单前置——预算/墙钟耗尽不换模型重试（重试重复消耗预算/时间），原样上抛
            hist.append(True)
            raise
        except DeterministicLLMFailure:
            # 确定性失败：换路由单次逃生；仍败 → 抛原异常（上层降级+打标）
            hist.append(True)
            try:
                _switch()
                if direct is not None:
                    _deadline_guard_escape()
                    out = direct(chapter_name, prompt)
                    return out + (degrade_marker or "")
            except (LLMCallBudgetExceeded, WallClockDeadlineExceeded):
                raise  # 白名单：逃生路径同样不吞终止性异常
            except Exception:  # noqa: BLE001, S110
                pass
            raise
        except Exception:
            # 瞬态失败：窗口降级 + 已切换时走直连
            hist.append(True)
            if sum(hist) >= fail_threshold or direct is not None:
                try:
                    _switch()
                    if direct is not None:
                        _deadline_guard_escape()
                        return direct(chapter_name, prompt)
                except (LLMCallBudgetExceeded, WallClockDeadlineExceeded):
                    raise  # 白名单：逃生路径同样不吞终止性异常
                except Exception:  # noqa: BLE001, S110
                    pass
            raise

    return caller
