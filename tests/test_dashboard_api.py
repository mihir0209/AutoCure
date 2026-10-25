"""
Automated Dashboard & Web UI API Integration Tests
===================================================
Tests FastAPI endpoints:
  - GET /api/v1/reports/{report_id}
  - GET /api/v1/reports/{report_id}/proposals
  - GET /api/v1/reports/{report_id}/view (AST nodes + fix diff verification)
  - GET /visualizer (with authentication session)
  - POST /api/v1/fix/apply/{user_id} and /api/v1/repo/{user_id}/apply-fix
"""

import sys
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from main import app
from database.report_store import get_report_store
from database.token_store import get_token_store


@pytest.fixture(scope="module")
def client():
    """Spin up the FastAPI TestClient with lifespan events enabled."""
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(scope="module")
def registered_report_id():
    """Retrieve or ensure an existing report exists in the report store."""
    store = get_report_store()
    rep = store.get_latest_for_user("test-service")
    if rep:
        return rep.report_id

    # Fallback to any latest report in store
    reports = store.list_reports(limit=1)
    if reports:
        return reports[0].report_id

    pytest.skip("No reports available in data/reports.db to test")


# ============================================================================
# 1. Report Metadata & Proposals Endpoints
# ============================================================================

def test_get_report_metadata(client, registered_report_id):
    """Verify GET /api/v1/reports/{report_id} returns accurate metadata and proposals."""
    resp = client.get(f"/api/v1/reports/{registered_report_id}")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()

    assert data["report_id"] == registered_report_id
    assert "user_id" in data
    assert "error_type" in data
    assert "root_cause" in data
    assert "confidence" in data
    assert "proposals" in data
    assert "view_url" in data
    assert isinstance(data["proposals"], list)
    assert data["proposals_count"] >= 0


def test_get_report_proposals(client, registered_report_id):
    """Verify GET /api/v1/reports/{report_id}/proposals returns proposals array."""
    resp = client.get(f"/api/v1/reports/{registered_report_id}/proposals")
    assert resp.status_code == 200
    data = resp.json()

    assert data["report_id"] == registered_report_id
    assert "proposals" in data
    assert isinstance(data["proposals"], list)
    if data["proposals"]:
        p = data["proposals"][0]
        assert "target_file" in p
        assert "original_code" in p
        assert "suggested_code" in p


def test_get_report_metadata_not_found(client):
    """Verify 404 response for invalid report ID."""
    resp = client.get("/api/v1/reports/nonexistent-report-xyz-999")
    assert resp.status_code == 404
    assert "not found" in resp.json()["detail"].lower()


# ============================================================================
# 2. HTML Visualizer Report View (AST Nodes & Fix Diff Verification)
# ============================================================================

def test_report_view_html_ast_nodes_and_fix_diff(client, registered_report_id):
    """
    Verify GET /api/v1/reports/{report_id}/view serves the standalone HTML report
    containing interactive AST visualization components and code fix diff.
    """
    resp = client.get(f"/api/v1/reports/{registered_report_id}/view")
    assert resp.status_code == 200
    assert "text/html" in resp.headers.get("content-type", "")

    html_content = resp.text
    assert len(html_content) > 1000, "HTML report should be populated"

    # Assert interactive AST nodes & visualizer components are present
    assert any(
        term in html_content
        for term in ["ast-viz-wrap", "ast-viz-toolbar", "AST Parser Trace", "class=\"ast-tree\""]
    ), "Report HTML must contain AST visualizer container or tree markup"

    assert any(
        btn in html_content
        for btn in ["Zoom In", "Zoom Out", "Reset", "Fit", "toolbar"]
    ), "Report HTML must contain interactive AST toolbar actions"

    # Assert fix proposal and code diff elements are present
    assert any(
        diff_marker in html_content
        for diff_marker in ["Fix Proposal", "Suggested Fix", "Original Code", "code-ctx", "proposal"]
    ), "Report HTML must contain code fix proposal and diff sections"


# ============================================================================
# 3. Web Visualizer SPA Route (/visualizer)
# ============================================================================

def test_visualizer_redirects_unauthenticated(client):
    """Verify accessing /visualizer without auth redirects to /login."""
    resp = client.get("/visualizer", follow_redirects=False)
    assert resp.status_code in (302, 307)
    assert "/login" in resp.headers.get("location", "")


def test_visualizer_authenticated(client):
    """Verify authenticated user can view /visualizer page."""
    # Login as admin
    login_resp = client.post(
        "/login",
        data={"username": "admin", "password": "admin"},
        follow_redirects=False,
    )
    assert login_resp.status_code == 302
    cookies = login_resp.cookies

    # Access visualizer with authenticated session
    viz_resp = client.get("/visualizer", cookies=cookies)
    assert viz_resp.status_code == 200
    assert "text/html" in viz_resp.headers.get("content-type", "")
    assert len(viz_resp.text) > 0


# ============================================================================
# 4. Apply Fix Proposal Endpoints (/api/v1/fix/apply/{user_id})
# ============================================================================

def test_post_apply_fix_proposal_success(client):
    """Verify POST /api/v1/fix/apply/{user_id} queues fix application."""
    fix_payload = {
        "fixes": [
            {
                "target_file": "processor.py",
                "original_code": "return items[index]",
                "suggested_code": "return items[index] if 0 <= index < len(items) else None",
                "explanation": "Add bounds check to prevent IndexError",
            }
        ],
        "branch_name": "autocure/test-fix-apply",
        "commit_message": "test: automated apply fix verification",
    }

    # Test /api/v1/fix/apply/{user_id}
    resp = client.post("/api/v1/fix/apply/test-service", json=fix_payload)
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data["status"] == "queued"
    assert data["fixes_count"] == 1
    assert data["branch_name"] == "autocure/test-fix-apply"

    # Also test /api/v1/repo/{user_id}/apply-fix alias
    resp_alias = client.post("/api/v1/repo/test-service/apply-fix", json=fix_payload)
    assert resp_alias.status_code == 200
    assert resp_alias.json()["status"] == "queued"


def test_post_apply_fix_user_not_found(client):
    """Verify 404 response when applying fix for unknown user."""
    resp = client.post(
        "/api/v1/fix/apply/unknown-user-999",
        json={"fixes": [{"target_file": "app.py", "original_code": "x", "suggested_code": "y"}]},
    )
    assert resp.status_code == 404
    assert "user not found" in resp.json()["detail"].lower()


def test_post_apply_fix_missing_fixes(client):
    """Verify 400 response when fixes list is empty."""
    resp = client.post("/api/v1/fix/apply/test-service", json={"fixes": []})
    assert resp.status_code == 400
    assert "no fixes provided" in resp.json()["detail"].lower()
