"""AI-10 routing decision formatting + dataclass behaviour."""
from __future__ import annotations

from app.modules.ai.auto_router import _format_reason


class TestFormatReason:
    def test_no_history(self) -> None:
        msg = _format_reason(2, None)
        assert "2 open tasks" in msg
        assert "no historical response data" in msg

    def test_with_history(self) -> None:
        msg = _format_reason(0, 1.7)
        assert "0 open tasks" in msg
        assert "1.7h" in msg
