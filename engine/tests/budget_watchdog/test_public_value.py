import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from engine.budget_watchdog.public_value import (
    parse_public_value_documents,
    summarize_public_value,
)
from engine.budget_watchdog.public_value_bundle import build_public_value_bundle

A1_TEXT = """Table A.1
MACROECONOMIC PARAMETERS, FYs 2025-2029
Particulars                                      2025 Actual  2026 Adjusted  2027 Projection  2028 Projection  2029 Projection
Real GDP Growth (%)                                   4.4          3.5-4.5          5.0-6.0          5.0-6.0          5.0-6.0
Population (in Millions) 2/                         113.6              114.5              115.3              116.1              116.9
Unemployment Rate (%) 3/                              4.7          5.3-5.8          4.0-5.0          4.0-5.0          4.0-5.1
"""

A2_TEXT = """Table A.2
NATIONAL GOVERNMENT FISCAL PROGRAM, 2025-2029
(In Billion Pesos)
Particulars                                         2025 Actual  2026 Program  2027 Projection  2028 Projection  2029 Projection
REVENUES                                               4,453.4          4,807.0           5,205.5          5,524.4          5,993.5
Percent of GDP                                             15.9             15.8              15.7             15.4             15.5
DISBURSEMENTS                                          6,030.3          6,465.9           6,900.5          7,246.5          7,614.1
Percent of GDP                                             21.5             21.2              20.8             20.2             19.7
Current Operating Expenditures                         4,678.3          5,197.3           5,530.9          5,803.9          6,083.8
Interest Payments                                        864.1            995.6           1,114.3          1,237.0          1,377.5
Percent Share to Total Disbursements                       14.3             15.4              16.1             17.1             18.1
Capital Outlays                                        1,348.9          1,258.6           1,340.8          1,414.0          1,501.6
Percent of GDP                                              4.8              4.1               4.0              3.9              3.9
DEFICIT                                               (1,576.8)        (1,658.9)         (1,694.9)        (1,722.1)        (1,620.6)
Percent of GDP                                            (5.6)            (5.4)             (5.1)            (4.8)            (4.2)
Gross Borrowings                                       2,653.8          2,733.9           3,304.0          3,650.4          3,550.9
Total Expenditure Program 5/                           6,392.7          6,793.2           7,200.2          7,200.2          7,642.5
Infrastructure Program (Disbursements)                 1,324.1          1,272.6           1,340.8          1,420.9          1,505.2
Percent of GDP                                              4.7              4.2               4.0              4.0              3.9
NG Infrastructure                                      1,013.6            902.6             938.8            998.6          1,082.5
Infrastructure Transfers to LGUs 6/                      240.4            294.2             330.8            351.4            351.8
"""


def _documents() -> dict[str, str]:
    return {"besf-a1": A1_TEXT, "besf-a2": A2_TEXT}


def _snapshot(tmp_path: Path) -> Path:
    snapshot = tmp_path / "public-value-snapshot"
    snapshot.mkdir()
    documents = []
    for key, text in _documents().items():
        path = snapshot / f"{key}.txt"
        path.write_text(text, encoding="utf-8")
        documents.append(
            {
                "key": key,
                "path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "pdf_sha256": key[-1] * 64,
                "source_url": f"https://www.dbm.gov.ph/{key}.pdf",
                "source_page": 1 if key == "besf-a1" else 2,
            }
        )
    (snapshot / "snapshot-manifest.json").write_text(
        json.dumps(
            {
                "fiscal_year": 2027,
                "baseline_year": 2026,
                "documents": documents,
            }
        ),
        encoding="utf-8",
    )
    return snapshot


def test_parses_exact_fiscal_and_macroeconomic_boundaries() -> None:
    records = parse_public_value_documents(_documents())
    by_id = {record.indicator_id: record for record in records}

    assert len(records) == 19
    assert by_id["real_gdp_growth"].lower_2026 == 350
    assert by_id["real_gdp_growth"].upper_2027 == 600
    assert by_id["population"].value_2027 == 115_300_000
    assert by_id["revenues"].value_2027 == 520_550_000_000_000
    assert by_id["deficit_gdp"].value_2026 == 540
    assert by_id["infrastructure_gdp"].value_2027 == 400

    summary = summarize_public_value(records)
    assert summary["reading"] == "mixed"
    assert summary["improving_count"] == 3
    assert summary["pressure_count"] == 6
    assert summary["context_count"] == 10
    assert summary["revenue_coverage_bps"] == 7_544
    assert summary["expenditure_per_capita_centavos"] == 6_244_753


def test_parser_rejects_missing_ambiguous_or_invalid_source_rows() -> None:
    with pytest.raises(ValueError, match="required source row is missing"):
        parse_public_value_documents({"besf-a1": A1_TEXT, "besf-a2": "Table A.2"})
    with pytest.raises(ValueError, match="required source row is ambiguous"):
        parse_public_value_documents(
            {"besf-a1": A1_TEXT, "besf-a2": A2_TEXT + "\nREVENUES 1 2 3 4 5\n"}
        )
    with pytest.raises(ValueError, match="document set is incomplete"):
        parse_public_value_documents({"besf-a1": A1_TEXT})
    with pytest.raises(ValueError, match="source range is reversed"):
        parse_public_value_documents(
            {
                "besf-a1": A1_TEXT.replace("3.5-4.5", "4.5-3.5"),
                "besf-a2": A2_TEXT,
            }
        )
    with pytest.raises(ValueError, match="indicator set is incomplete"):
        summarize_public_value(parse_public_value_documents(_documents())[:-1])


def test_builds_and_verifies_public_value_d1_bundle(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    output = tmp_path / "public-value-bundle"

    result = build_public_value_bundle(snapshot, output, chunk_rows=7)

    assert result.indicator_count == 19
    assert result.improving_count == 3
    assert result.pressure_count == 6
    assert len(result.manifest_sha256) == 64
    connection = sqlite3.connect(":memory:")
    try:
        migration = (
            Path(__file__).resolve().parents[3]
            / "cloudflare/busisi/migrations/0009_public_value.sql"
        )
        connection.executescript(migration.read_text(encoding="utf-8"))
        for chunk in sorted((output / "chunks").glob("*.sql")):
            connection.executescript(chunk.read_text(encoding="utf-8"))
        counts = connection.execute(
            "SELECT direction, COUNT(*) FROM public_value_indicators GROUP BY direction"
        ).fetchall()
        metadata = dict(connection.execute("SELECT key, value FROM public_value_metadata"))
    finally:
        connection.close()
    assert dict(counts) == {"context": 10, "improving": 3, "pressure": 6}
    assert metadata["reading"] == "mixed"
    assert metadata["source_scope"] == "FY2027 BESF Tables A.1 and A.2"


def test_bundle_rejects_tampering_and_invalid_boundaries(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    manifest_path = snapshot / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["documents"][0]["sha256"] = "0" * 64
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="digest mismatch"):
        build_public_value_bundle(snapshot, tmp_path / "tampered")

    manifest["documents"][0]["sha256"] = hashlib.sha256(
        (snapshot / manifest["documents"][0]["path"]).read_bytes()
    ).hexdigest()
    manifest["fiscal_year"] = 2026
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="fiscal boundary"):
        build_public_value_bundle(snapshot, tmp_path / "invalid-year")
    with pytest.raises(ValueError, match="chunk_rows"):
        build_public_value_bundle(snapshot, tmp_path / "invalid-chunk", chunk_rows=0)


def test_bundle_rejects_missing_and_duplicate_snapshot_documents(tmp_path: Path) -> None:
    snapshot = _snapshot(tmp_path)
    manifest_path = snapshot / "snapshot-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    missing_path = snapshot / manifest["documents"][0]["path"]
    missing_path.unlink()
    with pytest.raises(ValueError, match="document is missing"):
        build_public_value_bundle(snapshot, tmp_path / "missing")

    missing_path.write_text(A1_TEXT, encoding="utf-8")
    manifest["documents"][0]["sha256"] = hashlib.sha256(missing_path.read_bytes()).hexdigest()
    manifest["documents"].append(dict(manifest["documents"][0]))
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate public-value document key"):
        build_public_value_bundle(snapshot, tmp_path / "duplicate")
