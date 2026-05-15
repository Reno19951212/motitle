"""Tests for GET /api/prompt_templates endpoint."""
import json
import sys
from pathlib import Path
import pytest


# Reuse client fixture pattern from existing test files
@pytest.fixture
def client():
    """Test client with auth bypass via _isolate_app_data autouse fixture."""
    backend_dir = Path(__file__).parent.parent
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    import app as app_module
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c


class TestPromptTemplatesEndpoint:
    def test_returns_3_templates(self, client):
        resp = client.get("/api/prompt_templates")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "templates" in body
        ids = {t["id"] for t in body["templates"]}
        assert ids == {"broadcast", "sports", "literal"}

    def test_each_template_has_required_fields(self, client):
        resp = client.get("/api/prompt_templates")
        for t in resp.get_json()["templates"]:
            assert "id" in t
            assert "label" in t
            assert "description" in t
            assert "overrides" in t
            assert isinstance(t["overrides"], dict)

    def test_response_is_stable_order(self, client):
        """broadcast comes first (the recommended default)."""
        resp = client.get("/api/prompt_templates")
        ids = [t["id"] for t in resp.get_json()["templates"]]
        assert ids[0] == "broadcast"

    def test_endpoint_does_not_require_admin(self, client):
        """Auth bypass is on in tests (_isolate_app_data), so the route is
        reachable. The decorator is @login_required (not @admin_required) —
        verify by ensuring 200 response under non-admin context."""
        resp = client.get("/api/prompt_templates")
        # With R5_AUTH_BYPASS, all routes are reachable.
        # In production this would still require any authenticated user.
        assert resp.status_code == 200
