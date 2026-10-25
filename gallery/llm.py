"""Provider-switchable LLM access: Microsoft Agent Framework agents on GitHub Models or Foundry,
wrapped in a replay cache so demos are free and deterministic."""
import asyncio
import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Callable, Protocol

from gallery.config import Settings

log = logging.getLogger(__name__)

TIMEOUT_S = 8.0
DEGRADED_FOR_S = 60.0
GITHUB_MODELS_URL = "https://models.github.ai/inference"


class LLM(Protocol):
    status: str

    async def run(self, agent: str, instructions: str, prompt: str,
                  tools: list[Callable] = ()) -> str: ...


class ReplayMiss(Exception):
    pass


class ProviderDegraded(Exception):
    pass


class AFLLM:
    """One Agent Framework agent per call; the chat client is shared."""

    def __init__(self, settings: Settings):
        from agent_framework.openai import OpenAIChatCompletionClient

        if settings.provider == "foundry":
            self.client = OpenAIChatCompletionClient(
                model=settings.foundry_deployment, azure_endpoint=settings.foundry_endpoint,
                api_key=settings.foundry_key, api_version="2024-10-21")
            self.model = f"foundry:{settings.foundry_deployment}"
        else:
            self.client = OpenAIChatCompletionClient(
                model=settings.github_model, base_url=GITHUB_MODELS_URL, api_key=settings.github_token)
            self.model = f"github:{settings.github_model}"
        self._degraded_until = 0.0

    @property
    def status(self) -> str:
        return "degraded" if time.monotonic() < self._degraded_until else "ok"

    async def run(self, agent: str, instructions: str, prompt: str, tools: list[Callable] = ()) -> str:
        from agent_framework import Agent

        if self.status == "degraded":
            raise ProviderDegraded(f"{self.model} rate limited")
        a = Agent(self.client, instructions, name=agent, tools=list(tools) or None)
        try:
            response = await asyncio.wait_for(a.run(prompt), TIMEOUT_S)
        except Exception as exc:
            if "429" in str(exc) or "RateLimit" in type(exc).__name__:
                self._degraded_until = time.monotonic() + DEGRADED_FOR_S
                log.warning("Rate limited by %s; using templates for %ss", self.model, DEGRADED_FOR_S)
            raise
        return response.text


class ReplayLLM:
    def __init__(self, inner: LLM | None, cache_dir: str | Path, record: bool):
        self.inner = inner
        self.dir = Path(cache_dir)
        self.record = record

    @property
    def status(self) -> str:
        return self.inner.status if self.inner else "replay"

    def _path(self, agent: str, instructions: str, prompt: str) -> Path:
        key = hashlib.sha256(f"{agent}|{instructions}|{prompt}".encode()).hexdigest()[:32]
        return self.dir / agent / f"{key}.json"

    async def run(self, agent: str, instructions: str, prompt: str, tools: list[Callable] = ()) -> str:
        path = self._path(agent, instructions, prompt)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))["text"]
        if self.inner is None:
            raise ReplayMiss(f"no cached reply for {agent}")
        text = await self.inner.run(agent, instructions, prompt, tools)
        if self.record:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"agent": agent, "prompt": prompt, "text": text},
                                       ensure_ascii=False, indent=1), encoding="utf-8")
        return text


def make_llm(settings: Settings) -> ReplayLLM:
    if settings.provider == "replay":
        return ReplayLLM(None, settings.replay_dir, record=False)
    return ReplayLLM(AFLLM(settings), settings.replay_dir, record=True)


_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.S)


def parse_json(text: str) -> dict:
    m = _FENCE.search(text)
    body = m.group(1) if m else text
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("no JSON object in reply")
    try:
        value = json.loads(body[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("reply is not a JSON object")
    return value
