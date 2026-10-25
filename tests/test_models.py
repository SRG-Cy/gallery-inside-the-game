from gallery.config import load_settings
from gallery.models import Event


def test_event_roundtrip():
    e = Event(id=1, t=12.5, type="pass", team="NOR", player_id="NOR-8", x=40, y=30,
              end_x=55, end_y=25, outcome="complete", under_pressure=True)
    assert Event.model_validate_json(e.model_dump_json()) == e


def test_load_settings_falls_back_to_replay(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)  # ignore any real .env
    monkeypatch.setenv("GALLERY_PROVIDER", "github")
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    assert load_settings().provider == "replay"


def test_load_settings_keeps_github_with_token(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GALLERY_PROVIDER", "github")
    monkeypatch.setenv("GITHUB_TOKEN", "x")
    assert load_settings().provider == "github"
