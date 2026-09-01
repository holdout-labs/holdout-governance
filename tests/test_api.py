"""HTTP JSON API tests (stdlib server, in-process)."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

import pytest

from holdout_governance import __version__
from holdout_governance.api import GovHTTPHandler

from m1_scenarios import build


@pytest.fixture()
def server(tmp_path):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), GovHTTPHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_port}"
    httpd.shutdown()
    httpd.server_close()


def _get(url: str):
    with urllib.request.urlopen(url) as resp:
        return resp.status, json.loads(resp.read())


def _post(url: str, body: dict):
    request = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request) as resp:
        return resp.status, json.loads(resp.read())


def _defect_dir(tmp_path):
    d = tmp_path / "defect"
    d.mkdir()
    build(d, "no_evidence_record")
    return d


def test_health(server) -> None:
    status, body = _get(f"{server}/health")
    assert status == 200
    assert body["ok"] is True
    assert body["version"] == __version__


def test_check_blocks_defect(server, tmp_path) -> None:
    d = _defect_dir(tmp_path)
    status, body = _post(f"{server}/check", {"manifest": str(d / "artifact.json")})
    assert status == 200
    assert body["decision"] == "block"
    assert body["exit_code"] == 2
    assert "gate:evidence_integrity" in body["missing"]


def test_report_endpoint(server, tmp_path) -> None:
    d = _defect_dir(tmp_path)
    status, body = _post(f"{server}/report", {"manifest": str(d / "artifact.json")})
    assert status == 200
    assert body["decision"] == "block"
    assert body["v1"] is False


def test_init_endpoint(server, tmp_path) -> None:
    target = tmp_path / "proj"
    status, body = _post(f"{server}/init", {"dir": str(target), "name": "api-demo"})
    assert status == 200
    assert body["created"] is True
    assert (target / "policy.yml").exists()
    assert (target / "artifact.json").exists()
    assert body["policy_ref"].startswith("sha256:")


def test_missing_manifest_returns_400(server) -> None:
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _post(f"{server}/check", {"manifest": "C:/definitely/not/here.json"})
    assert exc_info.value.code == 400
    body = json.loads(exc_info.value.read())
    assert "error" in body


def test_unknown_path_returns_404(server) -> None:
    with pytest.raises(urllib.error.HTTPError) as exc_info:
        _get(f"{server}/nope")
    assert exc_info.value.code == 404
