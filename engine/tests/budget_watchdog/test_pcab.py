import json
from datetime import UTC, date, datetime

import pytest

from engine.budget_watchdog.archive import Acquisition, ArtifactArchive
from engine.budget_watchdog.pcab import (
    PCAB_DETAIL_LIMIT,
    acquire_pcab_license_details,
    parse_pcab_license_detail,
    parse_pcab_regular_licenses,
)


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


def test_parses_valid_pcab_license_detail() -> None:
    payload = b"""
    <div><h2>License Valid!</h2></div>
    <table>
      <tr><th>Contractor:</th><td>ACME BUILDERS, INC.</td></tr>
      <tr><th>License Number:</th><td>012345</td></tr>
      <tr><th>Validity Period of this License/Renewal:</th>
          <td>February 26, 2026 to February 24, 2028</td></tr>
    </table>
    """

    detail = parse_pcab_license_detail(
        payload,
        record_id="115834",
        source_sha256="b" * 64,
    )

    assert detail.record_id == "115834"
    assert detail.status == "valid"
    assert detail.firm_name == "ACME BUILDERS, INC."
    assert detail.license_number == "12345"
    assert detail.valid_from == date(2026, 2, 26)
    assert detail.valid_to == date(2028, 2, 24)
    assert detail.source_sha256 == "b" * 64


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b"<h2>Unknown</h2>", "status"),
        (
            b"<h2>License Valid!</h2><table>"
            b"<tr><th>Contractor:</th><td>ACME</td></tr></table>",
            "License Number",
        ),
        (
            b"<h2>License Valid!</h2><table>"
            b"<tr><th>Contractor:</th><td>ACME</td></tr>"
            b"<tr><th>License Number:</th><td>123</td></tr>"
            b"<tr><th>Validity Period of this License/Renewal:</th>"
            b"<td>today to tomorrow</td></tr></table>",
            "validity period",
        ),
    ],
)
def test_rejects_malformed_pcab_license_detail(payload: bytes, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        parse_pcab_license_detail(
            payload,
            record_id="115834",
            source_sha256="b" * 64,
        )


def test_acquires_archives_and_orders_pcab_license_details(tmp_path) -> None:
    class Fetcher:
        def __init__(self) -> None:
            self.record_ids: list[str] = []

        def fetch(self, source_id, path, *, params, retrieved_at):
            record_id = str(params["licid"])
            self.record_ids.append(record_id)
            payload = f"""
            <h2>License Valid!</h2><table>
              <tr><th>Contractor:</th><td>BUILDER {record_id}</td></tr>
              <tr><th>License Number:</th><td>{record_id}</td></tr>
              <tr><th>Validity Period of this License/Renewal:</th>
                  <td>January 1, 2026 to January 1, 2028</td></tr>
            </table>
            """.encode()
            return Acquisition(
                source_id=source_id,
                source_url=(
                    "https://pcab.construction.gov.ph/verify/checklicense.php"
                    f"?licid={record_id}"
                ),
                retrieved_at=retrieved_at,
                media_type="text/html",
                payload=payload,
            )

    fetcher = Fetcher()
    artifacts, details = acquire_pcab_license_details(
        fetcher,
        ArtifactArchive(tmp_path / "archive"),
        ("20", "10"),
        retrieved_at=datetime(2026, 11, 9, tzinfo=UTC),
    )

    assert fetcher.record_ids == ["10", "20"]
    assert [item.record_id for item in details] == ["10", "20"]
    assert [item.license_number for item in details] == ["10", "20"]
    assert len(artifacts) == 2
    assert all((tmp_path / "archive" / "blobs" / item.sha256).is_file() for item in artifacts)


def test_rejects_unbounded_duplicate_or_invalid_pcab_detail_ids(tmp_path) -> None:
    class UnusedFetcher:
        def fetch(self, *args, **kwargs):
            raise AssertionError("invalid identifiers must fail before acquisition")

    archive = ArtifactArchive(tmp_path / "archive")
    fetcher = UnusedFetcher()
    for record_ids, message in (
        (("1", "1"), "unique and bounded"),
        (("not-a-number",), "digits"),
        (
            tuple(str(item) for item in range(PCAB_DETAIL_LIMIT + 1)),
            "unique and bounded",
        ),
    ):
        with pytest.raises(ValueError, match=message):
            acquire_pcab_license_details(fetcher, archive, record_ids)
