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
import time
import urllib.error
import urllib.request
import uuid

import pytest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


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


def _start_server(extra_env=None):
    port = _free_port()
    env = os.environ.copy()
    env["API_KEY"] = ""  # default: write-protection off
    if extra_env:
        env.update(extra_env)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(port)],
        cwd=BACKEND_DIR,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = "http://127.0.0.1:%d" % port
    if not _wait_until_ready(base_url):
        proc.terminate()
        raise RuntimeError("Backend server failed to start on %s" % base_url)
    return proc, base_url


def _stop_server(proc):
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()


@pytest.fixture(scope="session")
def api():
    """Client for a server running with the default local configuration."""
    proc, base_url = _start_server()
    try:
        yield ApiClient(base_url)
    finally:
        _stop_server(proc)


@pytest.fixture(scope="session")
def api_secure():
    """Client for a server running with API_KEY protection enabled."""
    proc, base_url = _start_server({"API_KEY": "test-secret-key"})
    try:
        yield ApiClient(base_url)
    finally:
        _stop_server(proc)


@pytest.fixture(scope="session")
def sample_image_bytes():
    """A small, valid, in-memory JPEG used by the image-analysis tests."""
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (64, 64), (128, 128, 128)).save(buf, format="JPEG")
    return buf.getvalue()