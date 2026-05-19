"""PaperGuard Web UI — FastAPI app.

Two layered surfaces:

1. **Anonymous / legacy** (unchanged from 1.x):
   - ``GET  /``           upload form
   - ``POST /scan``       upload single file + lang → HTML report
   - ``POST /scan.json``  same but JSON
   - ``GET  /detectors``  list registered detectors
   - ``GET  /health``     health probe

   Optional ``X-API-Token`` auth via ``PAPERGUARD_API_TOKEN`` still applies.

2. **Multi-tenant** (new in 2.0, opt-in):
   - ``GET  /app/login``, ``POST /app/login``, ``POST /app/logout``
   - ``GET  /app/redeem/{code}``, ``POST /app/redeem/{code}``
   - ``GET  /app``                    dashboard
   - ``POST /app/projects``
   - ``GET  /app/projects/{id}``
   - ``POST /app/projects/{id}/scan`` upload + persist
   - ``GET  /app/reports/{id}``       view (visibility-checked)
   - ``GET  /app/reports/{id}/raw.json``
   - ``GET  /app/shared``             public report list
   - ``GET  /app/admin/invites``, ``POST /app/admin/invites``

   Activated by ``PAPERGUARD_DB_URL`` and admin bootstrap envs (see
   ``docs/webui_multitenant.md``). Sessions live in HttpOnly signed cookies.

Single-user / anonymous installs need zero new config — the multi-tenant
surface is opt-in.
"""
from __future__ import annotations

import os
import secrets
import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse

from paperguard import __version__
from paperguard.core.registry import DetectorRegistry

_FILE_DEFAULT = File(...)
_LANG_DEFAULT = Form("en")


def _expected_token() -> str | None:
    """Server 模式下要求 X-API-Token header 匹配此值;为空时禁用 auth。"""
    return os.environ.get("PAPERGUARD_API_TOKEN")


def _check_token(provided: str | None) -> None:
    expected = _expected_token()
    if not expected:
        return  # auth disabled
    if not provided or not secrets.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Invalid or missing token")

MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

ALLOWED_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xlsm", ".docx", ".pdf"}


def _multitenant_enabled() -> bool:
    """Whether to mount the /app/* routes on startup."""
    return os.environ.get("PAPERGUARD_DB_URL", "").strip() != "" or os.environ.get(
        "PAPERGUARD_MULTITENANT", ""
    ).strip().lower() in {"1", "true", "yes"}


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Startup: init DB schema + bootstrap admin if multi-tenant is enabled."""
    if _multitenant_enabled():
        from paperguard.webui.admin_bootstrap import bootstrap_admin_from_env
        from paperguard.webui.db import dispose_engine, get_sessionmaker, init_models

        await init_models()
        sm = get_sessionmaker()
        async with sm() as session:
            await bootstrap_admin_from_env(session)
        try:
            yield
        finally:
            await dispose_engine()
    else:
        yield


def create_app() -> FastAPI:
    app = FastAPI(
        title="PaperGuard",
        version=__version__,
        description="Statistical anomaly screener for tabular research data.",
        lifespan=_lifespan,
    )

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return _INDEX_HTML

    @app.get("/detectors")
    def list_detectors() -> dict[str, Any]:
        reg = DetectorRegistry().register_default()
        return {
            "version": __version__,
            "detectors": [
                {
                    "id": d.id,
                    "name": d.name,
                    "description": d.description,
                    "cluster": d.assumption_cluster,
                    "academic_basis": d.academic_basis,
                }
                for d in reg.all()
            ],
        }

    @app.post("/scan", response_class=HTMLResponse)
    async def scan_html(
        file: UploadFile = _FILE_DEFAULT,
        lang: str = _LANG_DEFAULT,
        x_api_token: str | None = Header(default=None),
    ) -> HTMLResponse:
        _check_token(x_api_token)
        report = await _scan_upload(file)
        from paperguard.reporter.html_export import render_html

        return HTMLResponse(render_html(report, lang=lang))

    @app.post("/scan.json")
    async def scan_json(
        file: UploadFile = _FILE_DEFAULT,
        x_api_token: str | None = Header(default=None),
    ) -> JSONResponse:
        _check_token(x_api_token)
        report = await _scan_upload(file)
        return JSONResponse(report.model_dump(mode="json"))

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    if _multitenant_enabled():
        from paperguard.webui.routes_app import router as app_router
        from paperguard.webui.routes_auth import router as auth_router

        app.include_router(auth_router, prefix="/app", tags=["auth"])
        app.include_router(app_router, prefix="/app", tags=["multi-tenant"])

    return app


async def _scan_upload(file: UploadFile) -> Any:
    """处理上传:写到 tempdir → run _scan_single_file → 返回 AuditReport。"""
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")
    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type {suffix}; allowed: {sorted(ALLOWED_SUFFIXES)}",
        )

    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({len(data)} bytes; max {MAX_UPLOAD_BYTES})",
        )

    from paperguard.cli import _scan_single_file

    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        return _scan_single_file(tmp_path)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass


_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>PaperGuard Web UI</title>
<style>
  body { font-family: -apple-system, system-ui, sans-serif; max-width: 700px;
         margin: 3em auto; padding: 0 1em; color: #222; }
  h1 { color: #2c3e50; }
  .disclaimer { background: #fffbea; border: 1px solid #f0c36d;
                padding: 0.8em 1em; border-radius: 4px; font-size: 0.9em;
                color: #555; margin-bottom: 2em; }
  form { background: #f6f8fa; padding: 1.5em; border-radius: 6px; }
  label { display: block; margin: 0.6em 0 0.2em; font-weight: bold; }
  input[type=file], select { width: 100%; padding: 0.4em; box-sizing: border-box; }
  button { margin-top: 1em; padding: 0.6em 1.4em; background: #0366d6;
           color: white; border: none; border-radius: 4px; cursor: pointer;
           font-size: 1em; }
  button:hover { background: #024a9e; }
  .footer { margin-top: 3em; font-size: 0.85em; color: #777; }
  code { background: #eee; padding: 0.1em 0.3em; border-radius: 2px; }
</style>
</head>
<body>
<h1>PaperGuard</h1>
<p>Upload a research data file (.csv / .xlsx / .docx / .pdf) — receive a
statistical-anomaly screening report.</p>

<div class="disclaimer">
This tool flags <strong>statistical anomalies, not fraud</strong>. Every
finding lists possible innocent explanations. Use the output as a starting
point for further inquiry, never as a conclusion.
</div>

<form action="/scan" method="post" enctype="multipart/form-data">
  <label for="file">Data file</label>
  <input type="file" name="file" id="file" required
         accept=".csv,.tsv,.xlsx,.xlsm,.docx,.pdf">
  <label for="lang">Report language</label>
  <select name="lang" id="lang">
    <option value="en" selected>English</option>
    <option value="zh-CN">中文</option>
  </select>
  <button type="submit">Scan</button>
</form>

<p class="footer">
  Also try <code>POST /scan.json</code> for a machine-readable response, or
  <code>GET /detectors</code> to see the active detector list.
  Multi-tenant mode? Sign in at <code>/app/login</code>.
</p>
</body>
</html>
"""
