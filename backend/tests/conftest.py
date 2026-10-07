"""Pytest fixtures for the AI Road Damage Mapper backend.

Tests run against a REAL uvicorn server started in a subprocess and are driven
over HTTP using only the Python standard library, so no extra test dependencies
(e.g. httpx) are required.
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_DIR = os.path.dirname(BACKEND_DIR)


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_until_ready(base_url: str, timeout: float = 30.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/health", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            time.sleep(0.4)
    return False


class ApiClient:
    """Minimal standard-library HTTP client for the running backend."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def _send(self, method, path, data=None, headers=None):
        req = urllib.request.Request(
            self.base_url + path, data=data, headers=headers or {}, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.status, resp.read()
        except urllib.error.HTTPError as err:
            return err.code, err.read()

    @staticmethod
    def _maybe_json(raw):
        try:
            return json.loads(raw)
        except Exception:
            return raw.decode("utf-8", "ignore")

    def get(self, path, headers=None):
        status, raw = self._send("GET", path, headers=headers)
        return status, self._maybe_json(raw)

    def post_json(self, path, payload, headers=None):
        hdrs = {"Content-Type": "application/json"}
        hdrs.update(headers or {})
        status, raw = self._send("POST", path, data=json.dumps(payload).encode(), headers=hdrs)
        return status, self._maybe_json(raw)

    def patch_json(self, path, payload, headers=None):
        hdrs = {"Content-Type": "application/json"}
        hdrs.update(headers or {})
        status, raw = self._send("PATCH", path, data=json.dumps(payload).encode(), headers=hdrs)
        return status, self._maybe_json(raw)

    def delete(self, path, headers=None):
        status, raw = self._send("DELETE", path, headers=headers)
        return status, self._maybe_json(raw)

    def post_file(self, path, field, filename, content_type, content, headers=None):
        boundary = uuid.uuid4().hex
        body = b"".join([
            ("--" + boundary + "\r\n").encode(),
            ('Content-Disposition: form-data; name="' + field + '"; filename="' + filename + '"\r\n').encode(),
            ("Content-Type: " + content_type + "\r\n\r\n").encode(),
            content,
            ("\r\n--" + boundary + "--\r\n").encode(),
        ])
        hdrs = {"Content-Type": "multipart/form-data; boundary=" + boundary}
        hdrs.update(headers or {})
        status, raw = self._send("POST", path, data=body, headers=hdrs)
        return status, self._maybe_json(raw)


def _remove_test_database(database_path: str) -> None:
    for attempt in range(10):
        try:
            os.remove(database_path)
            return
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(0.1)


def _start_server(extra_env=None, ready_timeout: float = 30.0):
    port = _free_port()
    database_fd, database_path = tempfile.mkstemp(prefix="road-mapper-test-", suffix=".db")
    os.close(database_fd)
    env = os.environ.copy()
    env["API_KEY"] = ""  # default: write-protection off
    env["DATABASE_URL"] = "sqlite:///" + database_path.replace("\\", "/")

    # Force hermetic "no-model" mode so the suite behaves identically regardless
    # of any MODEL_PATH the developer has in their local .env. python-dotenv does
    # NOT override variables that are already present in the environment, so an
    # explicit empty value here stops a locally configured model from being
    # loaded -- keeping startup fast and the no-model assertions deterministic.
    env["MODEL_PATH"] = ""

    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=PROJECT_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = "http://127.0.0.1:%d" % port
    if not _wait_until_ready(base_url, timeout=ready_timeout):
        _stop_server(proc)
        if os.path.exists(database_path):
            _remove_test_database(database_path)
        raise RuntimeError("Backend server failed to start on %s" % base_url)
    return proc, base_url, database_path


def _stop_server(proc):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=10)


@pytest.fixture(scope="session")
def api():
    """Client for a server running with the default local configuration."""
    proc, base_url, database_path = _start_server()
    try:
        yield ApiClient(base_url)
    finally:
        _stop_server(proc)
        if os.path.exists(database_path):
            _remove_test_database(database_path)


@pytest.fixture(scope="session")
def api_secure():
    """Client for a server running with API_KEY protection enabled."""
    proc, base_url, database_path = _start_server({"API_KEY": "test-secret-key"})
    try:
        yield ApiClient(base_url)
    finally:
        _stop_server(proc)
        if os.path.exists(database_path):
            _remove_test_database(database_path)


@pytest.fixture(scope="session")
def sample_image_bytes():
    """A small, valid, in-memory JPEG used by the image-analysis tests."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()


# ─── Optional real-model ("model mode") fixture ───────────────────────────────
# The default fixtures above deliberately run in no-model mode. The fixture below
# exercises the real computer-vision path when weights + the Ultralytics extra are
# available, and is skipped otherwise so the suite stays green everywhere.

MODEL_CANDIDATE = os.path.join(PROJECT_DIR, "models", "best.pt")


def _real_model_available() -> bool:
    if not os.path.exists(MODEL_CANDIDATE):
        return False
    try:
        import importlib.util

        return importlib.util.find_spec("ultralytics") is not None
    except Exception:  # noqa: BLE001
        return False


@pytest.fixture(scope="session")
def api_with_model():
    """Client for a server configured with the repository's real model weights.

    Model loading can take noticeably longer than the no-model path, so the
    readiness timeout is raised. Skipped when no weights / Ultralytics are found.
    """
    if not _real_model_available():
        pytest.skip("No real model weights or Ultralytics installed; skipping model-mode tests.")
    proc, base_url, database_path = _start_server({"MODEL_PATH": MODEL_CANDIDATE}, ready_timeout=120.0)
    try:
        yield ApiClient(base_url)
    finally:
        _stop_server(proc)
        if os.path.exists(database_path):
            _remove_test_database(database_path)