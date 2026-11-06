"""Run the private, model-assisted project-link review council."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sqlite3
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from engine.budget_watchdog.evidence_retrieval import (
    lexical_search,
    retrieval_manifest_sha256,
)
from engine.budget_watchdog.review_council import (
    COUNCIL_SEATS,
    CouncilVerdict,
    adjudicate_case,
    attach_document_evidence,
    build_evidence_packet,
    council_status,
    packet_sha256,
    record_verdict,
    validate_verdict_against_packet,
    verdict_from_payload,
)
from engine.budget_watchdog.review_council_agents import extract_json, token_usage

ROOT = Path(__file__).resolve().parents[2]
PROMPT_DIR = ROOT / "ops" / "harness" / "prompts"
SCHEMA_PATH = ROOT / "ops" / "harness" / "schema" / "busisi-council-verdict.schema.json"
DEFAULT_WORKSPACE = ROOT / "data" / "budget_watchdog" / "project-link-review"
DISSENT_ROUND = 2
MODEL_BY_SEAT = {
    "source_auditor": "kimi-code/k3",
    "identity_skeptic": "fable",
    "quality_reviewer": "gpt-6-astra",
}
PROMPT_BY_SEAT = {
    seat: PROMPT_DIR / f"busisi-{seat.replace('_', '-')}.md" for seat in COUNCIL_SEATS
}
EMPTY_USAGE = {
    "input_tokens": None,
    "cached_input_tokens": None,
    "cache_write_input_tokens": None,
    "output_tokens": None,
    "reasoning_tokens": None,
}


@dataclass(frozen=True, slots=True)
class CouncilAttempt:
    attempt_number: int
    started_at: str
    duration_seconds: float
    exit_code: int | None
    raw_output: str
    error: str
    usage: dict[str, int | None]


@dataclass(frozen=True, slots=True)
class CouncilRun:
    case_id: str
    seat: str
    model: str
    round_number: int
    packet_sha256: str
    prompt_sha256: str
    attempts: tuple[CouncilAttempt, ...]
    verdict: CouncilVerdict | None


@dataclass(frozen=True, slots=True)
class Runtime:
    kimi_bin: Path
    claude_bin: Path
    codex_bin: Path
    timeout: int


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _read_json_lines(value: str) -> tuple[dict[str, Any], ...]:
    records = []
    for line in value.splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(record, dict):
            records.append(record)
    return tuple(records)


def _usage_from_output(value: str) -> dict[str, int | None]:
    records = _read_json_lines(value)
    if not records:
        try:
            record = json.loads(value)
        except json.JSONDecodeError:
            return dict(EMPTY_USAGE)
        records = (record,) if isinstance(record, dict) else ()
    for record in reversed(records):
        normalized = token_usage(record)
        if any(item is not None for item in normalized.values()):
            return normalized
    return dict(EMPTY_USAGE)


def _command(
    seat: str,
    runtime: Runtime,
    prompt: str,
    output_path: Path,
    schema_text: str,
) -> tuple[list[str], str | None]:
    if seat == "source_auditor":
        return (
            [
                str(runtime.kimi_bin),
                "-m",
                MODEL_BY_SEAT[seat],
                "-p",
                prompt,
                "--output-format",
                "text",
            ],
            None,
        )
    if seat == "identity_skeptic":
        return (
            [
                str(runtime.claude_bin),
                "-p",
                "--model",
                MODEL_BY_SEAT[seat],
                "--output-format",
                "json",
                "--json-schema",
                schema_text,
                "--restricted",
                "--tools",
                "",
                "--permission-prompts",
                "none",
                "--no-session-persistence",
                "--disable-slash-commands",
            ],
            prompt,
        )
    return (
        [
            str(runtime.codex_bin),
            "exec",
            "--skip-git-repo-check",
            "--sandbox",
            "read-only",
            "--ephemeral",
            "--ignore-user-config",
            "--ignore-rules",
            "-m",
            MODEL_BY_SEAT[seat],
            "--output-schema",
            str(SCHEMA_PATH),
            "--json",
            "--output-last-message",
            str(output_path),
            "-",
        ],
        prompt,
    )


def _final_output(seat: str, stdout: str, codex_output: str) -> str:
    if codex_output:
        return codex_output
    if seat == "identity_skeptic":
        try:
            wrapper = json.loads(stdout)
        except json.JSONDecodeError:
            return stdout
        result = wrapper.get("result") if isinstance(wrapper, dict) else None
        return result if isinstance(result, str) else stdout
    return stdout


def _invoke(seat: str, prompt: str, runtime: Runtime, attempt_number: int) -> CouncilAttempt:
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    started_at = datetime.now(UTC).isoformat()
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="busisi-council-") as directory:
        output_path = Path(directory) / "last-message.json"
        command, stdin = _command(seat, runtime, prompt, output_path, schema_text)
        try:
            completed = subprocess.run(  # noqa: S603
                command,
                input=stdin,
                text=True,
                capture_output=True,
                timeout=runtime.timeout,
                cwd=directory,
                check=False,
            )
            codex_output = output_path.read_text(encoding="utf-8") if output_path.is_file() else ""
            raw_output = _final_output(seat, completed.stdout, codex_output)
            error = completed.stderr.strip() if completed.returncode else ""
            if completed.returncode and not error:
                error = f"process exited with code {completed.returncode}"
            usage = _usage_from_output(completed.stdout)
            return CouncilAttempt(
                attempt_number,
                started_at,
                time.monotonic() - started,
                completed.returncode,
                raw_output,
                error,
                usage,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            return CouncilAttempt(
                attempt_number,
                started_at,
                time.monotonic() - started,
                None,
                "",
                str(error),
                dict(EMPTY_USAGE),
            )


def _prior_verdicts(database: Path, case_id: str) -> tuple[dict[str, Any], ...]:
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        rows = connection.execute(
            "SELECT seat, decision, confidence, summary, findings_json, gaps_json, recommendation "
            "FROM council_verdicts WHERE case_id = ? AND round_number = 1 ORDER BY seat",
            (case_id,),
        ).fetchall()
    finally:
        connection.close()
    return tuple(
        {
            "seat": row["seat"],
            "decision": row["decision"],
            "confidence": row["confidence"],
            "summary": row["summary"],
            "findings": json.loads(row["findings_json"]),
            "gaps": json.loads(row["gaps_json"]),
            "recommendation": row["recommendation"],
        }
        for row in rows
    )


def _build_prompt(
    seat: str,
    packet: dict[str, Any],
    round_number: int,
    prior: tuple[dict[str, Any], ...],
) -> str:
    role = PROMPT_BY_SEAT[seat].read_text(encoding="utf-8").strip()
    schema = SCHEMA_PATH.read_text(encoding="utf-8").strip()
    sections = [role, "Required JSON schema:\n" + schema]
    if round_number == DISSENT_ROUND:
        sections.append(
            "This is a dissent review. Reconsider the same evidence after reading the first-round "
            "views below. Resolve their concrete objections when the packet allows it. Do not "
            "change a conclusion merely to agree, and do not add facts.\n"
            + json.dumps(prior, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        )
    sections.append(
        "Evidence packet:\n"
        + json.dumps(packet, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    return "\n\n".join(sections) + "\n"


def _run_seat(
    database: Path,
    packet: dict[str, Any],
    seat: str,
    round_number: int,
    runtime: Runtime,
) -> CouncilRun:
    case_id = packet["case_id"]
    packet_hash = packet_sha256(packet)
    prior = _prior_verdicts(database, case_id) if round_number == DISSENT_ROUND else ()
    prompt = _build_prompt(seat, packet, round_number, prior)
    attempts: list[CouncilAttempt] = []
    verdict = None
    for attempt_number in (1, 2):
        attempt = _invoke(seat, prompt, runtime, attempt_number)
        try:
            if attempt.exit_code != 0:
                raise ValueError(attempt.error or "review process failed")
            candidate = verdict_from_payload(extract_json(attempt.raw_output))
            if candidate.case_id != case_id or candidate.seat != seat:
                raise ValueError("verdict case or seat does not match the request")
            validate_verdict_against_packet(candidate, packet)
            verdict = candidate
            attempts.append(attempt)
            break
        except (KeyError, TypeError, ValueError) as error:
            attempts.append(
                CouncilAttempt(
                    attempt.attempt_number,
                    attempt.started_at,
                    attempt.duration_seconds,
                    attempt.exit_code,
                    attempt.raw_output,
                    str(error),
                    attempt.usage,
                )
            )
    return CouncilRun(
        case_id,
        seat,
        MODEL_BY_SEAT[seat],
        round_number,
        packet_hash,
        _digest(prompt),
        tuple(attempts),
        verdict,
    )


def _materialize_packets(
    database: Path,
    case_ids: tuple[str, ...],
    retrieval_database: Path | None,
    retrieval_limit: int,
) -> dict[str, dict[str, Any]]:
    manifest = (
        retrieval_manifest_sha256(retrieval_database)
        if retrieval_database is not None
        else None
    )
    packets: dict[str, dict[str, Any]] = {}
    for case_id in case_ids:
        packet = build_evidence_packet(database, case_id)
        if retrieval_database is not None and manifest is not None:
            query = " ".join(
                (
                    packet["budget_record"]["description"],
                    packet["project_record"]["description"],
                    packet["budget_record"]["location"],
                    packet["project_record"]["contract_id"],
                )
            )
            results = lexical_search(retrieval_database, query, limit=retrieval_limit)
            packet = attach_document_evidence(
                packet,
                query=query,
                results=results,
                index_manifest_sha256=manifest,
            )
        packets[case_id] = packet
    if retrieval_database is not None and retrieval_manifest_sha256(retrieval_database) != manifest:
        raise ValueError("retrieval index changed while council packets were materialized")
    return packets


def _selected_cases(
    database: Path,
    round_number: int,
    limit: int,
    requested: tuple[str, ...],
) -> tuple[str, ...]:
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        if requested:
            placeholders = ",".join("?" for _ in requested)
            rows = connection.execute(
                f"SELECT case_id FROM review_cases WHERE case_id IN ({placeholders}) "  # noqa: S608
                "ORDER BY case_id",
                requested,
            ).fetchall()
        elif round_number == DISSENT_ROUND:
            rows = connection.execute(
                "SELECT case_id FROM council_outcomes WHERE round_number = 1 "
                "AND outcome = 'unclear' ORDER BY case_id LIMIT ?",
                (limit,),
            ).fetchall()
        else:
            rows = connection.execute(
                "SELECT c.case_id FROM review_cases c JOIN review_prechecks p USING (case_id) "
                "WHERE p.passed = 1 ORDER BY c.case_id LIMIT ?",
                (limit,),
            ).fetchall()
    finally:
        connection.close()
    found = tuple(row[0] for row in rows)
    if requested and len(found) != len(set(requested)):
        raise ValueError("one or more requested case IDs do not exist")
    return found


def _missing_tasks(
    database: Path, case_ids: tuple[str, ...], round_number: int
) -> tuple[tuple[str, str], ...]:
    connection = sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)
    try:
        existing = set(
            connection.execute(
                "SELECT case_id, seat FROM council_verdicts WHERE round_number = ?",
                (round_number,),
            ).fetchall()
        )
    finally:
        connection.close()
    return tuple(
        (case_id, seat)
        for case_id in case_ids
        for seat in COUNCIL_SEATS
        if (case_id, seat) not in existing
    )


def _next_attempt_number(connection: sqlite3.Connection, run: CouncilRun) -> int:
    row = connection.execute(
        "SELECT COALESCE(MAX(attempt_number), 0) FROM council_attempts "
        "WHERE case_id = ? AND round_number = ? AND seat = ?",
        (run.case_id, run.round_number, run.seat),
    ).fetchone()
    return int(row[0]) + 1


def _save_run(workspace: Path, database: Path, run: CouncilRun) -> None:
    raw_dir = workspace / "council" / "raw" / run.case_id
    raw_dir.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(database)
    try:
        next_attempt = _next_attempt_number(connection, run)
        for offset, attempt in enumerate(run.attempts):
            number = next_attempt + offset
            relative = (
                Path("council")
                / "raw"
                / run.case_id
                / (f"round-{run.round_number}-{run.seat}-attempt-{number}.txt")
            )
            output_path = workspace / relative
            output_path.write_text(attempt.raw_output, encoding="utf-8")
            output_hash = hashlib.sha256(output_path.read_bytes()).hexdigest()
            with connection:
                connection.execute(
                    "INSERT INTO council_attempts VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        run.case_id,
                        run.round_number,
                        run.seat,
                        number,
                        run.model,
                        run.packet_sha256,
                        run.prompt_sha256,
                        attempt.started_at,
                        attempt.duration_seconds,
                        attempt.exit_code,
                        int(not attempt.error),
                        str(relative),
                        output_hash,
                        attempt.error,
                        attempt.usage["input_tokens"],
                        attempt.usage["cached_input_tokens"],
                        attempt.usage["cache_write_input_tokens"],
                        attempt.usage["output_tokens"],
                        attempt.usage["reasoning_tokens"],
                    ),
                )
    finally:
        connection.close()
    if run.verdict is None:
        return
    successful = next(item for item in reversed(run.attempts) if not item.error)
    record_verdict(
        database,
        run.verdict,
        round_number=run.round_number,
        model=run.model,
        packet_sha256=run.packet_sha256,
        prompt_sha256=run.prompt_sha256,
        output_sha256=_digest(successful.raw_output),
        started_at=successful.started_at,
        duration_seconds=successful.duration_seconds,
        token_usage=successful.usage,
    )


def _write_status(workspace: Path, database: Path, errors: list[dict[str, str]]) -> None:
    status = council_status(database)
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "models": MODEL_BY_SEAT,
        "outcomes": asdict(status),
        "current_run_errors": errors,
        "public_release_eligible": False,
        "release_note": "Council votes remain private until calibration and release checks pass.",
    }
    output = workspace / "council" / "council-status.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(output)


def _run_round(
    workspace: Path,
    database: Path,
    case_ids: tuple[str, ...],
    round_number: int,
    runtime: Runtime,
    workers: int,
    retrieval_database: Path | None,
    retrieval_limit: int,
) -> list[dict[str, str]]:
    tasks = _missing_tasks(database, case_ids, round_number)
    packets = _materialize_packets(
        database, case_ids, retrieval_database, retrieval_limit
    )
    errors: list[dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _run_seat,
                database,
                packets[case_id],
                seat,
                round_number,
                runtime,
            ): (
                case_id,
                seat,
            )
            for case_id, seat in tasks
        }
        for future in as_completed(futures):
            case_id, seat = futures[future]
            try:
                run = future.result()
                _save_run(workspace, database, run)
                if run.verdict is None:
                    errors.append({"case_id": case_id, "seat": seat, "error": "no valid verdict"})
            except Exception as error:  # noqa: BLE001 - preserve other independent reviews
                errors.append({"case_id": case_id, "seat": seat, "error": str(error)})
    decided_at = datetime.now(UTC).isoformat()
    for case_id in case_ids:
        adjudicate_case(database, case_id, decided_at, round_number=round_number)
    return errors


def _runtime(args: argparse.Namespace) -> Runtime:
    runtime = Runtime(args.kimi_bin, args.claude_bin, args.codex_bin, args.timeout)
    for binary in (runtime.kimi_bin, runtime.claude_bin, runtime.codex_bin):
        if not binary.is_file() or not os.access(binary, os.X_OK):
            raise ValueError(f"review command is not executable: {binary}")
    return runtime


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--round", type=int, choices=(1, 2), default=1)
    parser.add_argument("--case-id", action="append", default=[])
    parser.add_argument("--with-dissent", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--retrieval-database", type=Path)
    parser.add_argument("--retrieval-limit", type=int, default=5)
    parser.add_argument("--kimi-bin", type=Path, default=Path("/home/deploy/.kimi-code/bin/kimi"))
    parser.add_argument("--claude-bin", type=Path, default=Path("/home/deploy/.local/bin/claude"))
    parser.add_argument("--codex-bin", type=Path, default=Path("/home/deploy/.local/bin/codex"))
    return parser


def main() -> int:
    args = _parser().parse_args()
    if args.limit < 1 or args.workers < 1 or args.timeout < 1 or args.retrieval_limit < 1:
        raise ValueError("limit, workers, timeout, and retrieval limit must be positive")
    database = args.workspace / "project-link-review.sqlite3"
    if not database.is_file():
        raise ValueError("review workspace database does not exist")
    if args.retrieval_database is not None and not args.retrieval_database.is_file():
        raise ValueError("retrieval database does not exist")
    runtime = _runtime(args)
    case_ids = _selected_cases(database, args.round, args.limit, tuple(args.case_id))
    tasks = _missing_tasks(database, case_ids, args.round)
    if args.dry_run:
        print(
            json.dumps(
                {
                    "round": args.round,
                    "cases": len(case_ids),
                    "requests": len(tasks),
                    "models": MODEL_BY_SEAT,
                    "document_retrieval": args.retrieval_database is not None,
                },
                indent=2,
            )
        )
        return 0
    errors = _run_round(
        args.workspace,
        database,
        case_ids,
        args.round,
        runtime,
        min(args.workers, len(tasks) or 1),
        args.retrieval_database,
        args.retrieval_limit,
    )
    if args.with_dissent and args.round == 1:
        dissent_cases = _selected_cases(database, 2, args.limit, ())
        errors.extend(
            _run_round(
                args.workspace,
                database,
                dissent_cases,
                2,
                runtime,
                min(args.workers, len(dissent_cases) * len(COUNCIL_SEATS) or 1),
                args.retrieval_database,
                args.retrieval_limit,
            )
        )
    _write_status(args.workspace, database, errors)
    status = council_status(database)
    print(
        json.dumps({"cases": len(case_ids), "errors": errors, "status": asdict(status)}, indent=2)
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
