"""Multi-tenant /app/* routes: projects, scans, reports, sharing, admin invites."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from paperguard.webui.deps import (
    CurrentAdmin,
    CurrentUser,
    CurrentUserOptional,
    DBSession,
)
from paperguard.webui.models import (
    InviteCode,
    Project,
    ScanReport,
    User,
    UserRole,
    Visibility,
)
from paperguard.webui.security import generate_invite_code
from paperguard.webui.templates import (
    dashboard,
    invites_page,
    project_page,
    report_page,
    shared_list_page,
)

router = APIRouter()


ALLOWED_SUFFIXES = {".csv", ".tsv", ".xlsx", ".xlsm", ".docx", ".pdf"}
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB

_FILE_DEFAULT = File(...)
_VISIBILITY_DEFAULT = Form("private")


@router.get("/", response_class=HTMLResponse)
async def index(user: CurrentUserOptional, session: DBSession) -> HTMLResponse:
    if user is None:
        return HTMLResponse(
            status_code=status.HTTP_303_SEE_OTHER,
            content="",
            headers={"location": "/app/login"},
        )
    projects = list(
        (
            await session.scalars(
                select(Project)
                .where(Project.owner_id == user.id)
                .order_by(Project.created_at.desc())
            )
        ).all()
    )
    return HTMLResponse(dashboard(user, projects))


@router.get("/projects", response_class=HTMLResponse)
async def projects_redirect() -> Response:
    return RedirectResponse("/app", status_code=status.HTTP_303_SEE_OTHER)


@router.post("/projects")
async def create_project(
    user: CurrentUser,
    session: DBSession,
    name: str = Form(...),
    description: str = Form(""),
) -> Response:
    trimmed = name.strip()[:160]
    if not trimmed:
        raise HTTPException(status_code=400, detail="Project name required")
    project = Project(
        owner_id=user.id,
        name=trimmed,
        description=description.strip()[:2000],
    )
    session.add(project)
    await session.commit()
    await session.refresh(project)
    return RedirectResponse(
        f"/app/projects/{project.id}", status_code=status.HTTP_303_SEE_OTHER
    )


async def _owned_project(
    session: AsyncSession, user: User, project_id: int
) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def view_project(
    project_id: int, user: CurrentUser, session: DBSession
) -> HTMLResponse:
    project = await _owned_project(session, user, project_id)
    reports = list(
        (
            await session.scalars(
                select(ScanReport)
                .where(ScanReport.project_id == project.id)
                .order_by(ScanReport.created_at.desc())
            )
        ).all()
    )
    return HTMLResponse(project_page(user, project, reports))


@router.post("/projects/{project_id}/scan")
async def scan_into_project(
    project_id: int,
    user: CurrentUser,
    session: DBSession,
    file: UploadFile = _FILE_DEFAULT,
    visibility: str = _VISIBILITY_DEFAULT,
) -> Response:
    project = await _owned_project(session, user, project_id)
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename")
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
    try:
        vis = Visibility(visibility)
    except ValueError:
        vis = Visibility.PRIVATE

    from paperguard.cli import _scan_single_file

    sha = hashlib.sha256(data).hexdigest()
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(data)
        tmp_path = Path(tmp.name)
    try:
        audit = _scan_single_file(tmp_path)
    finally:
        try:
            tmp_path.unlink()
        except OSError:
            pass

    payload = audit.model_dump(mode="json")
    findings = payload.get("findings") or []
    severity_max = _max_severity([f.get("severity", "PASS") for f in findings])

    report = ScanReport(
        project_id=project.id,
        filename=file.filename,
        sha256=sha,
        visibility=vis,
        n_findings=len(findings),
        severity_max=severity_max,
        payload_json=json.dumps(payload, ensure_ascii=False),
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return RedirectResponse(
        f"/app/reports/{report.id}", status_code=status.HTTP_303_SEE_OTHER
    )


_SEVERITY_ORDER = ["PASS", "CONCERN", "SUSPICIOUS", "CRITICAL"]


def _max_severity(severities: list[str]) -> str:
    max_idx = 0
    for s in severities:
        if s in _SEVERITY_ORDER:
            idx = _SEVERITY_ORDER.index(s)
            if idx > max_idx:
                max_idx = idx
    return _SEVERITY_ORDER[max_idx]


async def _readable_report(
    session: AsyncSession, report_id: int, user: User | None
) -> ScanReport:
    report = await session.get(ScanReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    if report.visibility == Visibility.PUBLIC:
        return report
    if user is None:
        raise HTTPException(status_code=401, detail="Sign-in required")
    if report.visibility == Visibility.ORG:
        return report
    # PRIVATE: must belong to a project the user owns
    project = await session.get(Project, report.project_id)
    if project is None or project.owner_id != user.id:
        raise HTTPException(status_code=403, detail="Forbidden")
    return report


@router.get("/reports/{report_id}", response_class=HTMLResponse)
async def view_report(
    report_id: int, user: CurrentUserOptional, session: DBSession
) -> HTMLResponse:
    report = await _readable_report(session, report_id, user)
    payload = json.loads(report.payload_json)
    return HTMLResponse(report_page(user, report, payload))


@router.get("/reports/{report_id}/raw.json")
async def report_raw_json(
    report_id: int, user: CurrentUserOptional, session: DBSession
) -> JSONResponse:
    report = await _readable_report(session, report_id, user)
    return JSONResponse(json.loads(report.payload_json))


@router.get("/shared", response_class=HTMLResponse)
async def shared(user: CurrentUserOptional, session: DBSession) -> HTMLResponse:
    reports = list(
        (
            await session.scalars(
                select(ScanReport)
                .where(ScanReport.visibility == Visibility.PUBLIC)
                .order_by(ScanReport.created_at.desc())
                .limit(100)
            )
        ).all()
    )
    return HTMLResponse(shared_list_page(user, reports))


# ---------- admin -----------------------------------------------------------


@router.get("/admin/invites", response_class=HTMLResponse)
async def list_invites(
    request: Request, admin: CurrentAdmin, session: DBSession
) -> HTMLResponse:
    invites = list(
        (
            await session.scalars(
                select(InviteCode).order_by(InviteCode.created_at.desc())
            )
        ).all()
    )
    base = str(request.base_url).rstrip("/")
    return HTMLResponse(invites_page(admin, invites, base))


@router.post("/admin/invites")
async def create_invite(
    request: Request,
    admin: CurrentAdmin,
    session: DBSession,
    email: str = Form(...),
    role: str = Form("member"),
) -> Response:
    normalised = email.strip().lower()
    if not normalised or "@" not in normalised:
        raise HTTPException(status_code=400, detail="Valid email required")
    try:
        role_value = UserRole(role)
    except ValueError:
        role_value = UserRole.MEMBER
    invite = InviteCode(
        code=generate_invite_code(),
        email=normalised,
        role=role_value,
        created_by_id=admin.id,
    )
    session.add(invite)
    await session.commit()
    return RedirectResponse(
        "/app/admin/invites", status_code=status.HTTP_303_SEE_OTHER
    )
