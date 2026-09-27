from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from roto_kb.api.app import create_app
from roto_kb.config import ConfigurationError, Settings
from roto_kb.domain.models import EvidencePackage, SourceRecord, stable_id
from roto_kb.ingestion.chunker import chunk_document
from roto_kb.ingestion.parsers import parse_text
from roto_kb.ingestion.scanner import SUPPORTED, infer_domain
from roto_kb.retrieval import is_identifier_query, resolve_allowed_chunk_ids
from roto_kb.service import KnowledgeService


def test_empty_contract_and_auth():
    settings = Settings(read_token="r" * 32, admin_token="a" * 32)
    client = TestClient(create_app(settings))
    assert client.get("/health").json()["active_release_id"] == "rel_empty"
    assert client.get("/browse").status_code == 401
    response = client.post("/search", json={"query": "traction_bcs"}, headers={"Authorization": "Bearer " + "r" * 32})
    package = EvidencePackage.model_validate(response.json())
    assert package.no_match and package.results == []


def test_settings_load_external_secret_env_with_process_precedence(tmp_path: Path, monkeypatch):
    local_env = tmp_path / ".env"
    secret_env = tmp_path / "shared.env"
    local_env.write_text(
        f"ROTO_KB_ENV_FILE={secret_env}\n"
        "ROTO_KB_READ_TOKEN=\n"
        "ROTO_KB_ADMIN_TOKEN=\n",
        encoding="utf-8",
    )
    secret_env.write_text(
        f"ROTO_KB_READ_TOKEN={'r' * 32}\n"
        f"ROTO_KB_ADMIN_TOKEN={'a' * 32}\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    for key in ("ROTO_KB_ENV_FILE", "ROTO_KB_READ_TOKEN", "ROTO_KB_ADMIN_TOKEN"):
        monkeypatch.delenv(key, raising=False)

    settings = Settings.from_env()
    assert settings.read_token == "r" * 32
    assert settings.admin_token == "a" * 32

    monkeypatch.setenv("ROTO_KB_READ_TOKEN", "process-token")
    assert Settings.from_env().read_token == "process-token"


def test_production_settings_require_loopback_and_long_distinct_tokens():
    with pytest.raises(ConfigurationError, match="at least 32"):
        Settings(mode="production", host="127.0.0.1", read_token="r", admin_token="a" * 32).validate()

    with pytest.raises(ConfigurationError, match="loopback"):
        Settings(mode="production", host="0.0.0.0", read_token="r" * 32, admin_token="a" * 32).validate()

    with pytest.raises(ConfigurationError, match="must differ"):
        Settings(mode="production", host="127.0.0.1", read_token="r" * 32, admin_token="r" * 32).validate()


def test_stable_chunks_and_hybrid_search(tmp_path: Path):
    source = SourceRecord(source_id="src_1", source_uri="https://example.invalid/a", sha256="0" * 64, license="MIT")
    doc = parse_text(source, "# Boundary\ntraction_bcs and vol_frac are engineering parameters.")
    assert chunk_document(doc) == chunk_document(doc)
    service = KnowledgeService(tmp_path)
    (tmp_path / "a.md").write_text("# Boundary\ntraction_bcs and vol_frac are engineering parameters.", encoding="utf-8")
    release = service.reload()
    assert release.status == "active" and release.chunk_count >= 1
    assert service.search("traction_bcs").results


def test_stable_id():
    assert stable_id("doc", "a", 1) == stable_id("doc", "a", 1)


def test_domain_filters_and_identifier_prefer_bm25(tmp_path: Path):
    assert ".py" in SUPPORTED
    assert infer_domain("official-docs/fenitop/beam_3d.py") == "fenitop-examples"
    assert is_identifier_query("vol_frac")

    (tmp_path / "official-docs" / "fenitop").mkdir(parents=True)
    (tmp_path / "official-docs" / "fenitop" / "beam_3d.py").write_text(
        'opt = {"vol_frac": 0.08, "filter_radius": 0.6}\n',
        encoding="utf-8",
    )
    (tmp_path / "other.md").write_text("# Unrelated petroleum volume density notes\n", encoding="utf-8")
    service = KnowledgeService(tmp_path)
    service.reload()

    package = service.search("vol_frac", filters={"domains": ["fenitop-examples"]})
    assert package.results and package.results[0].domain == "fenitop-examples"
    assert "vol_frac" in package.results[0].snippets[0].content

    allowed = resolve_allowed_chunk_ids(service.chunks, {"domains": ["fenitop-examples"]})
    assert allowed and all(service.chunks[cid].domain == "fenitop-examples" for cid in allowed)
