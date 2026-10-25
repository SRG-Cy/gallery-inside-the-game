from collections import deque


class FakeLLM:
    """Scripted LLM: per-agent queues of replies (str) or exceptions; records every call."""

    def __init__(self, replies: dict[str, list] | None = None, default=None):
        self.queues = {k: deque(v) for k, v in (replies or {}).items()}
        self.default = default
        self.calls: list[dict] = []
        self.status = "ok"

    async def run(self, agent, instructions, prompt, tools=()):
        self.calls.append({"agent": agent, "prompt": prompt, "tools": list(tools)})
        q = self.queues.get(agent)
        reply = q.popleft() if q else self.default
        if isinstance(reply, BaseException):
            raise reply
        if callable(reply):
            return reply(prompt)
        if reply is None:
            raise RuntimeError(f"FakeLLM has no reply for {agent}")
        return reply

    def count(self, agent: str) -> int:
        return sum(c["agent"] == agent for c in self.calls)
