"""Local FastAPI service. Bind to 127.0.0.1; never expose this on the LAN."""

from __future__ import annotations

import os
import re
import secrets
import threading
import uuid
from io import BytesIO
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from .ai import summarize_messages, validate_endpoint
from .importer import MAX_SINGLE_FILE, parse_discord_zip, parse_json_document
from .storage import ArchiveDB


ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DPA_DATA_DIR", str(ROOT / "data")))
db = ArchiveDB(DATA_DIR / "archive.sqlite")
app = FastAPI(title="Discord Personal Archive", version="0.1.0", docs_url=None, redoc_url=None)
PAIRING_KEY = secrets.token_urlsafe(18)
MAX_UPLOAD = 250_000_000
jobs: dict[str, dict[str, Any]] = {}
job_lock = threading.Lock()
extension_origin = re.compile(r"^chrome-extension://[a-p]{32}$")


@app.middleware("http")
async def localhost_boundary(request: Request, call_next):
    host = request.headers.get("host", "").split(":")[0].strip("[]").lower()
    if host not in ("127.0.0.1", "localhost", "::1"):
        return JSONResponse({"detail": "仅允许本机访问。"}, status_code=403)
    origin = request.headers.get("origin", "")
    allowed = {"http://127.0.0.1:8765", "http://localhost:8765"}
    if os.environ.get("DPA_DEV") == "1":
        allowed.update({"http://127.0.0.1:5173", "http://localhost:5173"})
    is_extension = bool(extension_origin.fullmatch(origin))
    is_collector = request.url.path == "/api/collector"
    # Modern browsers label cross-site requests even when the Origin header is
    # absent. The paired extension is the sole deliberately cross-site writer.
    if (request.method in ("POST", "PUT", "PATCH", "DELETE")
            and request.headers.get("sec-fetch-site") == "cross-site"
            and not (is_collector and is_extension)):
        return JSONResponse({"detail": "拒绝跨站修改请求。"}, status_code=403)
    if request.method == "OPTIONS" and is_collector and is_extension:
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": origin,
                "Access-Control-Allow-Methods": "POST, OPTIONS",
                "Access-Control-Allow-Headers": "content-type, x-archive-pairing",
                "Access-Control-Max-Age": "300",
                "Vary": "Origin",
            },
        )
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        if is_collector:
            if origin and not is_extension:
                return JSONResponse({"detail": "此入口只允许本地扫描扩展。"}, status_code=403)
        elif origin and origin not in allowed:
            return JSONResponse({"detail": "来源校验失败。"}, status_code=403)
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'"
    )
    if is_collector and is_extension:
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Vary"] = "Origin"
    return response


@app.get("/api/health")
def health():
    return {"ok": True, "version": "0.1.0", "mode": "local-only"}


@app.get("/api/stats")
def stats():
    return db.stats()


@app.get("/api/channels")
def channels(q: str = Query(default="", max_length=120)):
    return db.channels(q)


@app.get("/api/messages")
def messages(
    channel_id: str | None = Query(default=None, max_length=40),
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=40, ge=1, le=100),
    offset: int = Query(default=0, ge=0, le=1_000_000),
):
    return db.messages(channel_id, q, limit, offset)


@app.post("/api/import")
async def import_file(file: UploadFile = File(...)):
    filename = Path(file.filename or "archive.zip").name
    await file.seek(0)
    stream = file.file
    stream.seek(0, 2)
    size = stream.tell()
    stream.seek(0)
    if not 0 < size <= MAX_UPLOAD:
        raise HTTPException(413, "文件超过 250MB 大小上限，或文件为空。")

    def ingest():
        if filename.lower().endswith(".zip"):
            parsed = parse_discord_zip(stream)
        elif filename.lower().endswith(".json"):
            data = stream.read(MAX_SINGLE_FILE + 1)
            if len(data) > MAX_SINGLE_FILE:
                raise ValueError("JSON 文件太大。")
            parsed = parse_json_document(data)
        else:
            raise ValueError("只支持 Discord 数据包 ZIP 或原插件预览 JSON。")
        channels_found, messages_found, source = parsed
        result = db.import_batch(channels_found, messages_found, source, filename)
        return {**result, "source": source, "channels_found": len(channels_found),
                "messages_found": len(messages_found)}

    try:
        return await run_in_threadpool(ingest)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    finally:
        await file.close()


@app.get("/api/pairing")
def pairing():
    # Only the local UI can read this (no CORS); the key never touches Discord.
    return {"key": PAIRING_KEY, "endpoint": "http://127.0.0.1:8765", "expires": "服务重启后失效"}


@app.post("/api/collector")
async def collector(request: Request):
    token = request.headers.get("x-archive-pairing", "")
    if not secrets.compare_digest(token, PAIRING_KEY):
        raise HTTPException(401, "配对码无效。")
    if int(request.headers.get("content-length") or 0) > 2_000_000:
        raise HTTPException(413, "单批数据超过大小限制。")
    raw = await request.body()
    if len(raw) > 2_000_000:
        raise HTTPException(413, "单批数据超过大小限制。")
    try:
        import json
        payload = json.loads(raw)
    except ValueError as exc:
        raise HTTPException(400, "JSON 格式错误。") from exc
    if not isinstance(payload, dict):
        raise HTTPException(400, "同步数据应为对象。")
    channels_found = payload.get("channels") or []
    messages_found = payload.get("messages") or []
    if not isinstance(channels_found, list) or not isinstance(messages_found, list):
        raise HTTPException(400, "数据类型错误。")
    if len(channels_found) > 200 or len(messages_found) > 200:
        raise HTTPException(400, "单批最多 200 条消息。")
    clean_channels = [c for c in channels_found if isinstance(c, dict)]
    clean_messages = [m for m in messages_found if isinstance(m, dict)]
    result = await run_in_threadpool(
        db.import_batch, clean_channels, clean_messages, "live-readonly", "只读在线同步"
    )
    return result


class SummaryRequest(BaseModel):
    scope: Literal["all", "channel"] = "channel"
    channel_id: str | None = None
    provider: Literal["ollama", "openai"] = "ollama"
    model: str = Field(min_length=1, max_length=120)
    endpoint: str = Field(min_length=8, max_length=500)
    api_key: str = Field(default="", max_length=4000)
    title: str = Field(default="", max_length=200)


@app.get("/api/summaries")
def list_summaries():
    return db.summaries()


@app.get("/api/summaries/{summary_id}/markdown")
def summary_markdown(summary_id: int):
    summary = next((s for s in db.summaries() if s["id"] == summary_id), None)
    if not summary:
        raise HTTPException(404, "摘要不存在。")
    title = summary["title"].replace("\n", " ")[:120]
    body = f"# {title}\n\n{summary['content']}\n"
    return PlainTextResponse(
        body,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename=summary-{summary_id}.md"},
    )


def _change_job(job_id: str, **changes):
    with job_lock:
        jobs[job_id].update(changes)


def _run_job(job_id: str, settings: SummaryRequest):
    # API keys stay in this task's memory only. Neither disk nor job results.
    try:
        chosen = settings.channel_id if settings.scope == "channel" else None
        selected = db.messages_for_summary(chosen)
        if not selected:
            raise ValueError("当前范围没有可总结的消息。")
        _change_job(job_id, total_messages=len(selected), status="running", detail="准备分批分析")

        def progress(done: int, total: int, detail: str):
            _change_job(job_id, done=done, total=total, detail=detail)

        text = summarize_messages(
            selected, settings.provider, settings.model, settings.endpoint,
            settings.api_key, progress,
        )
        title = settings.title.strip() or (
            "所有历史消息知识总结" if not chosen else "频道历史消息知识总结"
        )
        summary_id = db.save_summary(
            title, settings.scope, chosen, settings.provider, settings.model,
            len(selected), text, [m["id"] for m in selected[:200]],
        )
        _change_job(job_id, status="complete", detail="总结完成", summary_id=summary_id)
    except Exception as exc:
        # External errors may include sensitive provider content. Keep UI errors generic
        # unless they were deliberately authored by this app.
        if isinstance(exc, (ValueError, RuntimeError)):
            message = str(exc)[:400]
        else:
            message = "AI 分析发生异常。请检查模型服务或缩小范围。"
        _change_job(job_id, status="failed", detail=message)


@app.post("/api/summarize", status_code=202)
def summarize(request: SummaryRequest):
    try:
        validate_endpoint(request.provider, request.endpoint)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if request.scope == "channel" and not request.channel_id:
        raise HTTPException(400, "请先指定一个频道。")
    with job_lock:
        if len([x for x in jobs.values() if x["status"] in ("queued", "running")]) >= 1:
            raise HTTPException(409, "已有 AI 任务在运行，请等待完成。")
        job_id = uuid.uuid4().hex
        jobs[job_id] = {
            "id": job_id, "status": "queued", "done": 0, "total": 0,
            "total_messages": 0, "detail": "已排队", "summary_id": None,
        }
    threading.Thread(target=_run_job, args=(job_id, request), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with job_lock:
        if job_id not in jobs:
            raise HTTPException(404, "任务不存在或服务已重启。")
        return dict(jobs[job_id])


DIST = ROOT / "frontend" / "dist"
if DIST.exists():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")


@app.get("/{path:path}")
def ui(path: str):
    if path.startswith("api/"):
        raise HTTPException(404, "接口不存在。")
    # Serve the built Vue SPA. Source is available even before npm build.
    index = DIST / "index.html"
    if index.exists():
        return FileResponse(index)
    return PlainTextResponse(
        "Vue 尚未构建。请先在 frontend 目录执行 npm install 和 npm run build。",
        status_code=503,
    )
