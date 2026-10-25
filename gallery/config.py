import logging
import os
from dataclasses import dataclass

log = logging.getLogger(__name__)


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env reader so secrets stay out of the shell history; real env vars win."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


@dataclass
class Settings:
    provider: str
    github_token: str | None
    github_model: str
    foundry_endpoint: str | None
    foundry_key: str | None
    foundry_deployment: str | None
    replay_dir: str
    db_path: str


def load_settings() -> Settings:
    _load_dotenv()
    env = os.environ.get
    s = Settings(
        provider=env("GALLERY_PROVIDER", "replay"),
        github_token=env("GITHUB_TOKEN"),
        github_model=env("GITHUB_MODEL", "openai/gpt-4.1-mini"),
        foundry_endpoint=env("FOUNDRY_ENDPOINT"),
        foundry_key=env("FOUNDRY_KEY"),
        foundry_deployment=env("FOUNDRY_DEPLOYMENT"),
        replay_dir=env("GALLERY_REPLAY_DIR", "replay_cache"),
        db_path=env("GALLERY_DB", "gallery.db"),
    )
    missing = (s.provider == "github" and not s.github_token) or (
        s.provider == "foundry" and not (s.foundry_endpoint and s.foundry_key and s.foundry_deployment))
    if s.provider not in ("github", "foundry", "replay") or missing:
        log.warning("Provider %r unavailable or missing credentials; using replay", s.provider)
        s.provider = "replay"
    return s
