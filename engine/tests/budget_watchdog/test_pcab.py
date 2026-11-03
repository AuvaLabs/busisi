import json
from datetime import date

import pytest

from engine.budget_watchdog.pcab import parse_pcab_regular_licenses


def _payload(rows: list[list[str]], *, records: int | None = None) -> bytes:
    return json.dumps(
        {
            "page": "1",
            "total": 1,
            "records": len(rows) if records is None else records,
            "rows": [{"id": cells[0], "cell": cells} for cells in rows],
        }
    ).encode()


def test_pcab_snapshot_normalizes_license_numbers_and_verifies_current_status() -> None:
    payload = _payload(
        [
            ["1", "ACME BUILDERS, INC.", "012345", "A Person", "AAA", "2027-03-01", "1"],
            ["2", "SECOND BUILDERS", "67890", "B Person", "B", "2026-10-01", "0"],
        ]
    )

    snapshot = parse_pcab_regular_licenses(
        payload,
        retrieved_on=date(2026, 11, 3),
        source_sha256="a" * 64,
    )

    acme = snapshot.verify("12345")
    second = snapshot.verify("67890")
    missing = snapshot.verify("99999")
    assert snapshot.record_count == 2
    assert acme.status == "current_regular"
    assert acme.firm_name == "ACME BUILDERS, INC."
    assert acme.category == "AAA"
    assert acme.gov_infra is True
    assert second.status == "expired_regular"
    assert second.gov_infra is False
    assert missing.status == "not_found_current_regular"


def test_pcab_snapshot_rejects_partial_or_malformed_tables() -> None:
    valid_row = ["1", "ACME", "12345", "A Person", "A", "2027-01-01", "1"]

    with pytest.raises(ValueError, match="record count"):
        parse_pcab_regular_licenses(
            _payload([valid_row], records=2),
            retrieved_on=date(2026, 11, 3),
            source_sha256="a" * 64,
        )
    with pytest.raises(ValueError, match="seven cells"):
        parse_pcab_regular_licenses(
            _payload([["1", "ACME"]]),
            retrieved_on=date(2026, 11, 3),
            source_sha256="a" * 64,
        )
    document = json.loads(_payload([valid_row]))
    document["total"] = 2
    with pytest.raises(ValueError, match="single complete page"):
        parse_pcab_regular_licenses(
            json.dumps(document).encode(),
            retrieved_on=date(2026, 11, 3),
            source_sha256="a" * 64,
        )
