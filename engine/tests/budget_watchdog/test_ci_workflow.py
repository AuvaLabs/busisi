from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
WORKFLOW = ROOT / ".github" / "workflows" / "busisi-production-monitor.yml"
TEST_WORKFLOW = ROOT / ".github" / "workflows" / "test.yml"
TEST_REQUIREMENTS = ROOT / "requirements-dev.txt"


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
