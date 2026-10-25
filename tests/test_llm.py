import pytest

from gallery.llm import ReplayLLM, ReplayMiss, parse_json
from tests.fakes import FakeLLM


async def test_replay_hit_skips_inner(tmp_path):
    inner = FakeLLM(default="first")
    rec = ReplayLLM(inner, tmp_path, record=True)
    assert await rec.run("analyst", "inst", "p1") == "first"
    inner.default = "second"
    assert await rec.run("analyst", "inst", "p1") == "first"
    assert inner.count("analyst") == 1


async def test_replay_records_miss(tmp_path):
    await ReplayLLM(FakeLLM(default="hello"), tmp_path, record=True).run("a", "i", "p")
    assert await ReplayLLM(None, tmp_path, record=False).run("a", "i", "p") == "hello"


async def test_replay_miss_without_inner_raises(tmp_path):
    with pytest.raises(ReplayMiss):
        await ReplayLLM(None, tmp_path, record=False).run("a", "i", "p")


async def test_replay_does_not_cache_failures(tmp_path):
    inner = FakeLLM({"a": [RuntimeError("boom"), "ok"]})
    rec = ReplayLLM(inner, tmp_path, record=True)
    with pytest.raises(RuntimeError):
        await rec.run("a", "i", "p")
    assert await rec.run("a", "i", "p") == "ok"


def test_parse_json_fenced():
    assert parse_json('```json\n{"a": 1}\n```') == {"a": 1}


def test_parse_json_with_prose():
    assert parse_json('Sure! Here it is: {"a": {"b": 2}} Hope that helps.') == {"a": {"b": 2}}


def test_parse_json_invalid_raises():
    with pytest.raises(ValueError):
        parse_json("no json here")
    with pytest.raises(ValueError):
        parse_json('{"a": }')
