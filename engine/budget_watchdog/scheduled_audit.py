"""Pure checks for scheduled Busisi verification command results."""

from __future__ import annotations


def audit_command_results(results: dict[str, int | None]) -> tuple[str, ...]:
    issues = []
    for name, code in results.items():
        if code is None:
            issues.append(f"{name} check did not complete")
        elif code != 0:
            issues.append(f"{name} check failed with exit code {code}")
    return tuple(issues)
