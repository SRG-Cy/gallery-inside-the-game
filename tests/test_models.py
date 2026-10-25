from gallery.config import Settings, load_settings
from gallery.models import Event


def test_event_roundtrip():
    e = Event(id=1, t=12.5, type="pass", team="NOR", player_id="NOR-8", x=40, y=30,
              end_x=55, end_y=25, outcome="complete", under_pressure=True)
    assert Event.model_validate_json(e.model_dump_json()) == e


def test_retired_github_provider_falls_back_to_replay(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # ignore any real .env
    monkeypatch.setenv("GALLERY_PROVIDER", "github")
    assert load_settings().provider == "replay"


def test_foundry_needs_all_three_settings(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GALLERY_PROVIDER", "foundry")
    monkeypatch.setenv("FOUNDRY_ENDPOINT", "https://x.openai.azure.com/")
    monkeypatch.setenv("FOUNDRY_DEPLOYMENT", "gpt-4.1-mini")
    monkeypatch.delenv("FOUNDRY_KEY", raising=False)
    assert load_settings().provider == "replay"
    monkeypatch.setenv("FOUNDRY_KEY", "k")
    assert load_settings().provider == "foundry"


def test_settings_have_no_github_fields():
    assert not any(f.startswith("github") for f in Settings.__dataclass_fields__)
