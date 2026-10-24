"""Local HTTP end-to-end test without contacting Discord or real AI providers."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
URL = "http://127.0.0.1:8765"
ORIGIN = URL
EXTENSION_ORIGIN = "chrome-extension://aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
CHANNEL = "323456789012345678"
MESSAGE = "523456789012345678"


def get(path: str):
    with urllib.request.urlopen(URL + path, timeout=5) as response:
        return response.status, response.read(), dict(response.headers)


def post(path: str, obj: dict, headers: dict | None = None):
    body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        URL + path, data=body, method="POST",
        headers={"Content-Type": "application/json", "Origin": ORIGIN, **(headers or {})},
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def make_zip():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr(
            f"messages/c{CHANNEL}/channel.json",
            json.dumps({"id": CHANNEL, "name": "demo", "guild_id": "223456789012345678"}),
        )
        archive.writestr(
            f"messages/c{CHANNEL}/messages.json",
            json.dumps([{"ID": MESSAGE, "Timestamp": "2026-10-01T12:00:00Z",
                         "Contents": "项目决定使用 Python 和 Vue 构建知识库", "Attachments": []}], ensure_ascii=False),
        )
    return output.getvalue()


def multipart_upload():
    boundary = "DPA-boundary-smoke"
    body = (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"messages.zip\"\r\n"
        "Content-Type: application/zip\r\n\r\n"
    ).encode() + make_zip() + f"\r\n--{boundary}--\r\n".encode()
    req = urllib.request.Request(
        URL + "/api/import", data=body, method="POST",
        headers={"Origin": ORIGIN, "Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        return json.loads(response.read())


class MockOllama(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path not in ("/api/chat", "/v1/chat/completions"):
            self.send_error(404)
            return
        size = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(size))
        assert any("消息ID" in m["content"] for m in payload["messages"])
        if self.path == "/api/chat":
            assert payload["model"] == "mock-model"
            result = {"message": {"content": "总结：使用 Python + Vue [消息ID:" + MESSAGE + "]"}}
        else:
            assert payload["model"] == "cloud-mock"
            assert self.headers.get("Authorization") == "Bearer example-only-key"
            result = {"choices": [{"message": {"content": "云端兼容接口模拟摘要 [消息ID:" + MESSAGE + "]"}}]}
        response = json.dumps(result).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(response)))
        self.end_headers()
        self.wfile.write(response)

    def log_message(self, *_args):
        pass


def main():
    with tempfile.TemporaryDirectory(prefix="dpa-smoke-") as temp:
        env = {**os.environ, "DPA_DATA_DIR": temp}
        process = subprocess.Popen(
            [sys.executable, str(ROOT / "run.py"), "--no-browser"],
            cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        mock = ThreadingHTTPServer(("127.0.0.1", 0), MockOllama)
        mock_thread = threading.Thread(target=mock.serve_forever, daemon=True)
        mock_thread.start()
        try:
            for _ in range(50):
                try:
                    code, body, _ = get("/api/health")
                    if code == 200:
                        break
                except (urllib.error.URLError, TimeoutError):
                    time.sleep(0.12)
            else:
                raise RuntimeError("本地服务没有启动。")
            assert json.loads(body)["ok"]
            code, html, headers = get("/")
            assert code == 200 and b"assets/" in html
            assert "content-security-policy" in {key.lower() for key in headers}
            assert json.loads(get("/api/stats")[1])["messages"] == 0

            imported = multipart_upload()
            assert imported["added"] == 1, imported
            imported_again = multipart_upload()
            assert imported_again["added"] == 0 and imported_again["updated"] == 1
            msgs = json.loads(get("/api/messages?q=Python")[1])
            assert msgs["total"] == 1 and msgs["items"][0]["guild_id"] == "223456789012345678"

            pairing = json.loads(get("/api/pairing")[1])["key"]
            status, _ = post("/api/collector", {"messages": [], "channels": []},
                             {"Origin": EXTENSION_ORIGIN, "X-Archive-Pairing": "wrong"})
            assert status == 401
            status, _ = post("/api/collector", {"messages": [], "channels": []},
                             {"Origin": "https://evil.example", "X-Archive-Pairing": pairing})
            assert status == 403
            status, _ = post("/api/summarize", {},
                             {"Origin": "", "Sec-Fetch-Site": "cross-site"})
            assert status == 403
            status, result = post(
                "/api/collector",
                {"channels": [{"id": CHANNEL, "name": "demo", "kind": "guild"}],
                 "messages": [{"id": "523456789012345699", "channel_id": CHANNEL,
                               "timestamp": "2026-10-02T12:00:00Z", "content": "待办：测试检索索引"}]},
                {"Origin": EXTENSION_ORIGIN, "Sec-Fetch-Site": "cross-site",
                 "X-Archive-Pairing": pairing},
            )
            assert status == 200 and result["added"] == 1

            status, job = post(
                "/api/summarize",
                {"scope": "all", "provider": "ollama", "model": "mock-model",
                 "endpoint": f"http://127.0.0.1:{mock.server_port}", "title": "模拟 AI 总结"},
            )
            assert status == 202
            for _ in range(50):
                current = json.loads(get("/api/jobs/" + job["job_id"])[1])
                if current["status"] in ("complete", "failed"):
                    break
                time.sleep(0.15)
            assert current["status"] == "complete", current
            summaries = json.loads(get("/api/summaries")[1])
            assert len(summaries) == 1
            assert "Python + Vue" in summaries[0]["content"]
            markdown = get("/api/summaries/" + str(summaries[0]["id"]) + "/markdown")[1]
            assert "模拟 AI 总结".encode() in markdown
            status, cloud_job = post(
                "/api/summarize",
                {"scope": "all", "provider": "openai", "model": "cloud-mock",
                 "endpoint": f"http://127.0.0.1:{mock.server_port}/v1",
                 "api_key": "example-only-key", "title": "模拟兼容 API"},
            )
            assert status == 202
            for _ in range(50):
                cloud_state = json.loads(get("/api/jobs/" + cloud_job["job_id"])[1])
                if cloud_state["status"] in ("complete", "failed"):
                    break
                time.sleep(0.15)
            assert cloud_state["status"] == "complete", cloud_state
            cloud_summaries = json.loads(get("/api/summaries")[1])
            assert len(cloud_summaries) == 2
            assert "云端兼容接口" in cloud_summaries[0]["content"]
            assert "example-only-key" not in json.dumps(cloud_summaries)
            print("PASS: GUI, import/dedup/search, pairing/origin, both AI backends, Markdown export")
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            mock.shutdown()
            mock.server_close()


if __name__ == "__main__":
    main()
