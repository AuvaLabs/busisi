import hashlib
import json
from pathlib import Path

import pytest

from engine.budget_watchdog.award_mirror import AwardMirrorError, load_award_mirror

FIXTURE = Path("ops/harness/fixtures/philgeps_award_mirror.json")


def test_loads_versioned_exact_award_rows() -> None:
    catalog = load_award_mirror(FIXTURE.read_bytes())

    assert catalog.source.revision == "b98de579579e8c7e79bac2a22ac7491549db6d0d"
    assert catalog.source.acquisition_status == "source_file_archived_secondary"
    assert catalog.source.source_file_sha256 == (
        "9bfa9e7cbf5041dc3b51a4c2742e60a43d1615f119955581d4b155bf3a6d4a8b"
    )
    assert catalog.source.source_file_byte_size == 492869009
    assert [item.contract_id for item in catalog.records] == ["25HI0028", "24HI0148", "24HI0131"]
    assert [item.contract_amount_centavos for item in catalog.records] == [
        197899499, 494467510, 493416373,
    ]


def _rehash(record: dict[str, object]) -> None:
    payload = {key: value for key, value in record.items() if key != "row_sha256"}
    record["row_sha256"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_rejects_tampered_award_row() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["records"][0]["contract_amount_centavos"] = 1

    with pytest.raises(AwardMirrorError, match="row_sha256"):
        load_award_mirror(json.dumps(raw).encode())


def test_rejects_duplicate_contract_identity() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["records"][1]["contract_id"] = "25HI0028"
    _rehash(raw["records"][1])

    with pytest.raises(AwardMirrorError, match="duplicate contract_id"):
        load_award_mirror(json.dumps(raw).encode())


@pytest.mark.parametrize(("field", "value", "message"), [
    ("revision", "not-a-revision", "revision"),
])
def test_rejects_invalid_source(field: str, value: str, message: str) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["source"][field] = value

    with pytest.raises(AwardMirrorError, match=message):
        load_award_mirror(json.dumps(raw).encode())


def test_rejects_invalid_source_row_uuid() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["records"][0]["source_row_id"] = "not-a-uuid"
    _rehash(raw["records"][0])

    with pytest.raises(AwardMirrorError, match="source_row_id"):
        load_award_mirror(json.dumps(raw).encode())


@pytest.mark.parametrize(("mutate", "message"), [
    (lambda raw: raw.update(schema_version=2), "schema version"),
    (lambda raw: raw.update(records={}), "records must be an array"),
    (lambda raw: raw.update(source=[]), "source must be an object"),
    (lambda raw: raw["source"].update(dataset_url="http://example.test"), "HTTPS"),
    (lambda raw: raw["source"].update(retrieved_at="2026-01-01"), "timezone-aware"),
    (lambda raw: raw["source"].update(last_modified="not-a-date"), "ISO formatted"),
    (lambda raw: raw["source"].update(acquisition_status="unarchived"), "acquisition status"),
    (lambda raw: raw["source"].update(source_file_sha256="bad"), "source file SHA-256"),
    (lambda raw: raw["source"].update(source_file_byte_size=0), "source file byte size"),
])
def test_rejects_invalid_catalog_boundaries(mutate, message: str) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    mutate(raw)

    with pytest.raises(AwardMirrorError, match=message):
        load_award_mirror(json.dumps(raw).encode())


@pytest.mark.parametrize(("field", "value", "message"), [
    ("contract_amount_centavos", True, "integer centavos"),
    ("contract_amount_centavos", -1, "integer centavos"),
    ("fiscal_year", 1900, "supported range"),
    ("award_date", "not-a-date", "ISO formatted"),
    ("awardee_name", "", "non-empty text"),
])
def test_rejects_invalid_record_boundaries(field: str, value: object, message: str) -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["records"][0][field] = value
    _rehash(raw["records"][0])

    with pytest.raises(AwardMirrorError, match=message):
        load_award_mirror(json.dumps(raw).encode())


def test_rejects_invalid_json_and_non_object_record() -> None:
    with pytest.raises(AwardMirrorError, match="JSON is invalid"):
        load_award_mirror(b"{broken")

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["records"][0] = []
    with pytest.raises(AwardMirrorError, match="record entries must be objects"):
        load_award_mirror(json.dumps(raw).encode())


def test_rejects_duplicate_source_row_identity() -> None:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    raw["records"][1]["source_row_id"] = raw["records"][0]["source_row_id"]
    _rehash(raw["records"][1])

    with pytest.raises(AwardMirrorError, match="duplicate source_row_id"):
        load_award_mirror(json.dumps(raw).encode())


def test_fixture_fingerprint_is_stable() -> None:
    payload = FIXTURE.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == "f00bbdc81519ae3193238a175a78201f314689b9d6d6d22346684837fce207ae"
