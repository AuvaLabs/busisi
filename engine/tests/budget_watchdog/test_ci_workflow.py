from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "busisi-production-monitor.yml"
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
TEST_REQUIREMENTS = ROOT / "requirements-dev.txt"
PUBLIC_RELEASE_FILES = (
    ROOT / "LICENSE",
    ROOT / "NOTICE",
    ROOT / "DATA_AND_MEDIA.md",
    ROOT / "SECURITY.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "CODE_OF_CONDUCT.md",
    ROOT / ".gitleaks.toml",
    ROOT / ".github" / "CODEOWNERS",
    ROOT / ".github" / "dependabot.yml",
    ROOT / ".github" / "ISSUE_TEMPLATE" / "data-correction.yml",
    ROOT / ".github" / "ISSUE_TEMPLATE" / "source-update.yml",
    ROOT / ".github" / "ISSUE_TEMPLATE" / "software-bug.yml",
)


def test_busisi_production_monitor_is_scheduled_and_credential_free() -> None:
    document = WORKFLOW.read_text(encoding="utf-8")

    assert "schedule:" in document
    assert 'cron: "17 */6 * * *"' in document
    assert "workflow_dispatch:" in document
    assert "contents: read" in document
    assert "actions/checkout@v7" in document
    assert "actions/setup-node@v7" in document
    assert "npm ci" in document
    assert "npm run verify:live" in document
    assert "secrets." not in document


def test_test_dependencies_support_current_starlette_client() -> None:
    requirements = TEST_REQUIREMENTS.read_text(encoding="utf-8")

    assert "httpx2>=2.16,<3" in requirements


def test_workflows_use_current_action_runtimes() -> None:
    monitor = WORKFLOW.read_text(encoding="utf-8")
    tests = TEST_WORKFLOW.read_text(encoding="utf-8")

    for document in (monitor, tests):
        assert "actions/checkout@v7" in document
        assert "actions/setup-node@v7" in document
        assert "runs-on: ubuntu-24.04" in document
    assert "actions/setup-python@v7" in tests


def test_test_workflow_validates_contributor_attribution() -> None:
    document = TEST_WORKFLOW.read_text(encoding="utf-8")

    assert "fetch-depth: 0" in document
    assert "Validate contributor attribution" in document
    assert "co-authored-by:" in document.lower()
    for identity in ("claude", "codex", "chatgpt", "openai", "anthropic", "copilot"):
        assert identity in document.lower()


def test_public_release_governance_is_explicit() -> None:
    for path in PUBLIC_RELEASE_FILES:
        assert path.is_file(), path
        assert path.stat().st_size > 0, path

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    data_terms = (ROOT / "DATA_AND_MEDIA.md").read_text(encoding="utf-8")
    security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    scanner = (ROOT / ".gitleaks.toml").read_text(encoding="utf-8")

    assert "Apache License 2.0" in readme
    assert "Proprietary" not in readme
    assert "does not relicense third-party material" in data_terms
    assert "dev@auvalabs.com" in security
    assert "useDefault = true" in scanner
    assert "Public IndexNow ownership key" in scanner
