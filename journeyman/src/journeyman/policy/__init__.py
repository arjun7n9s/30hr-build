"""Policy stream and tool gateway stubs."""

from typing import Any

from journeyman.contracts import DualPass, DualPassResult


class PolicyStream:
    def current(self) -> DualPass:
        raise NotImplementedError


class ToolGateway:
    def allow(self, tool: str, args: dict[str, Any], stream: PolicyStream) -> DualPassResult:
        raise NotImplementedError
