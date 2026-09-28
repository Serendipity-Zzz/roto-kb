from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

FORBIDDEN_PATHS = ("/data/knowledge-base", "/var/lib/legacy-kb-server", "/opt/legacy-kb-server")


class ConfigurationError(ValueError):
    pass


def read_dotenv(path: str | Path) -> dict[str, str]:
    """Read simple KEY=VALUE pairs without mutating the process environment."""
    env_path = Path(path)
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key:
            values[key] = value
    return values


def load_dotenv(path: str | Path = ".env") -> None:
    """Load a dotenv file without overriding explicit process variables."""
    for key, value in read_dotenv(path).items():
        if key not in os.environ:
            os.environ[key] = value


def load_runtime_environment(path: str | Path = ".env") -> None:
    """Load local defaults plus an optional external secret env file.

    Precedence is process environment, external env file, local dotenv, then
    Settings defaults. The external file keeps local integration secrets out of
    this repository while allowing the service and its caller to share tokens.
    """
    local_values = read_dotenv(path)
    external_path = os.getenv("ROTO_KB_ENV_FILE") or local_values.get("ROTO_KB_ENV_FILE")
    external_values: dict[str, str] = {}
    if external_path:
        external = Path(external_path).expanduser()
        if not external.is_file():
            raise ConfigurationError(f"ROTO_KB_ENV_FILE does not exist: {external}")
        external_values = read_dotenv(external)

    merged = {**local_values, **external_values}
    for key, value in merged.items():
        if key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class Settings:
    mode: str = "empty"
    source_path: Path = Path("knowledge")
    data_path: Path = Path(".roto-kb")
    host: str = "127.0.0.1"
    port: int = 8710
    qdrant_url: str = "http://127.0.0.1:6334"
    qdrant_mode: str = "embedded"
    qdrant_path: Path = Path(".roto-kb/qdrant")
    embedding_model: str = "text-embedding-v4"
    embedding_dimension: int | None = None
    read_token: str | None = None
    admin_token: str | None = None
    qdrant_api_key: str | None = None
    dashscope_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    dashscope_llm_model: str = "qwen3.7-flash"
    llm_enabled: bool = False
    embedding_batch_size: int = 16
    embedding_timeout_seconds: float = 30.0
    max_top_k: int = 20

    @classmethod
    def from_env(cls) -> Settings:
        load_runtime_environment()
        return cls(
            mode=os.getenv("ROTO_KB_MODE", "empty"),
            source_path=Path(os.getenv("ROTO_KB_SOURCE_PATH", "knowledge")),
            data_path=Path(os.getenv("ROTO_KB_DATA_PATH", ".roto-kb")),
            host=os.getenv("ROTO_KB_HOST", "127.0.0.1"),
            port=int(os.getenv("ROTO_KB_PORT", "8710")),
            qdrant_url=os.getenv("QDRANT_URL", "http://127.0.0.1:6334"),
            qdrant_mode=os.getenv("QDRANT_MODE", "embedded"),
            qdrant_path=Path(os.getenv("QDRANT_PATH", ".roto-kb/qdrant")),
            embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-v4"),
            embedding_dimension=int(os.environ["EMBEDDING_DIMENSION"]) if os.getenv("EMBEDDING_DIMENSION") else None,
            read_token=os.getenv("ROTO_KB_READ_TOKEN"),
            admin_token=os.getenv("ROTO_KB_ADMIN_TOKEN"),
            qdrant_api_key=os.getenv("QDRANT_API_KEY"),
            dashscope_base_url=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
            dashscope_llm_model=os.getenv("DASHSCOPE_LLM_MODEL", "qwen3.7-flash"),
            llm_enabled=os.getenv("LLM_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
            embedding_batch_size=int(os.getenv("EMBEDDING_BATCH_SIZE", "16")),
            embedding_timeout_seconds=float(os.getenv("EMBEDDING_TIMEOUT_SECONDS", "30")),
        )

    def validate(self, *, production: bool | None = None) -> None:
        production = self.mode == "production" if production is None else production
        if not 1 <= self.port <= 65535:
            raise ConfigurationError("port out of range")
        if self.max_top_k < 1:
            raise ConfigurationError("max_top_k must be positive")
        if self.embedding_batch_size < 1 or self.embedding_timeout_seconds <= 0:
            raise ConfigurationError("embedding batch/timeout must be positive")
        if self.qdrant_mode not in {"embedded", "server"}:
            raise ConfigurationError("QDRANT_MODE must be embedded or server")
        if self.read_token and self.admin_token and self.read_token == self.admin_token:
            raise ConfigurationError("read and admin tokens must differ")
        if self.read_token and len(self.read_token) < 32:
            raise ConfigurationError("ROTO_KB_READ_TOKEN must be at least 32 characters")
        if self.admin_token and len(self.admin_token) < 32:
            raise ConfigurationError("ROTO_KB_ADMIN_TOKEN must be at least 32 characters")
        if production and (not self.read_token or not self.admin_token):
            raise ConfigurationError("production requires read and admin secrets")
        if production and self.host not in {"127.0.0.1", "::1", "localhost"}:
            raise ConfigurationError("production app must bind to loopback; expose it through nginx")
        if production and self.qdrant_mode == "server" and not self.qdrant_api_key:
            raise ConfigurationError("server Qdrant mode requires QDRANT_API_KEY")


class PathPolicy:
    def __init__(self, allowed_root: Path):
        self.allowed_root = allowed_root.resolve()

    def resolve(self, path: str | Path) -> Path:
        candidate = Path(path)
        if candidate.is_symlink():
            raise PermissionError("symlink sources are not allowed")
        resolved = candidate.resolve()
        text = str(resolved).replace("\\", "/").lower()
        if any(text == p or text.startswith(p + "/") for p in FORBIDDEN_PATHS):
            raise PermissionError("path is reserved for the existing knowledge service")
        try:
            resolved.relative_to(self.allowed_root)
        except ValueError as exc:
            raise PermissionError("path is outside the configured source root") from exc
        return resolved
