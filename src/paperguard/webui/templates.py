"""Inline HTML templates for the multi-tenant Web UI.

Inline HTML strings keep the project zero-template-engine. Style matches
the existing anonymous index page (system fonts, GitHub-blue accents,
minimal CSS). All user-supplied strings are passed through ``html.escape``.
"""
from __future__ import annotations

from datetime import datetime
from html import escape
from typing import Any

from paperguard.webui.models import (
    InviteCode,
    Project,
    ScanReport,
    User,
    UserRole,
    Visibility,
)

_BASE_CSS = """
body { font-family: -apple-system, system-ui, sans-serif; max-width: 920px;
       margin: 2em auto; padding: 0 1em; color: #222; }
a { color: #0366d6; text-decoration: none; }
a:hover { text-decoration: underline; }
h1, h2 { color: #2c3e50; }
.bar { display:flex; justify-content: space-between; align-items: center;
       border-bottom: 1px solid #eee; padding-bottom: 0.6em; margin-bottom: 1.4em; }
.bar nav a { margin-left: 0.8em; font-size: 0.95em; }
.flash { background:#fffbea; border:1px solid #f0c36d; padding: 0.6em 1em;
         border-radius:4px; margin: 0.4em 0 1em; }
.error { background:#fdecea; border:1px solid #e88; color:#9b1f1f; }
form { background:#f6f8fa; padding:1.2em; border-radius:6px; margin-bottom:1em; }
label { display:block; margin: 0.5em 0 0.2em; font-weight:bold; }
input[type=text], input[type=email], input[type=password], textarea, select
  { width:100%; padding: 0.45em; box-sizing:border-box; font-size: 0.95em;
    border: 1px solid #ccc; border-radius: 3px; }
button { margin-top: 1em; padding: 0.55em 1.3em; background:#0366d6;
         color:white; border:none; border-radius:4px; cursor:pointer;
         font-size:0.95em; }
button:hover { background:#024a9e; }
table { border-collapse: collapse; width: 100%; margin: 0.5em 0 1.2em; }
th, td { text-align: left; padding: 0.45em 0.6em; border-bottom: 1px solid #eee;
         font-size: 0.93em; }
th { background: #f6f8fa; }
.badge { display:inline-block; padding: 0.1em 0.5em; border-radius: 3px;
         font-size:0.78em; font-weight:bold; background:#eee; color:#555; }
.badge.CRITICAL { background:#9b1f1f; color:white; }
.badge.SUSPICIOUS { background:#d97706; color:white; }
.badge.CONCERN { background:#eab308; color:#333; }
.badge.PASS { background:#16a34a; color:white; }
.badge.admin { background:#6f42c1; color:white; }
.muted { color: #777; font-size: 0.88em; }
.disclaimer { background:#fffbea; border:1px solid #f0c36d; padding: 0.6em 1em;
              border-radius:4px; font-size:0.86em; color:#555; margin-top: 2em; }
code { background:#eee; padding: 0.05em 0.35em; border-radius:2px; font-size:0.9em; }
"""

_DISCLAIMER_HTML = (
    '<div class="disclaimer">PaperGuard flags <strong>statistical anomalies, '
    "not fraud</strong>. Every finding lists possible innocent explanations. "
    "Use the output as a starting point for further inquiry, never as a "
    "conclusion.</div>"
)


def _bar(user: User | None) -> str:
    if user is None:
        return (
            '<div class="bar"><strong><a href="/app">PaperGuard</a></strong>'
            '<nav><a href="/app/shared">Public reports</a>'
            '<a href="/app/login">Sign in</a></nav></div>'
        )
    admin_link = (
        '<a href="/app/admin/invites">Invites</a>'
        if user.role == UserRole.ADMIN
        else ""
    )
    role_badge = (
        '<span class="badge admin">admin</span> '
        if user.role == UserRole.ADMIN
        else ""
    )
    return (
        '<div class="bar"><strong><a href="/app">PaperGuard</a></strong>'
        f'<nav>{role_badge}<span class="muted">{escape(user.email)}</span>'
        '<a href="/app/projects">Projects</a>'
        '<a href="/app/shared">Public</a>'
        f"{admin_link}"
        '<form action="/app/logout" method="post" style="display:inline; '
        'background:none; padding:0; margin:0;">'
        '<button type="submit" style="background:none; color:#0366d6; padding:0; '
        'margin-left:0.8em;">Sign out</button></form>'
        "</nav></div>"
    )


def _page(title: str, body: str, user: User | None = None) -> str:
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<title>{escape(title)} — PaperGuard</title>
<style>{_BASE_CSS}</style></head>
<body>{_bar(user)}{body}{_DISCLAIMER_HTML}</body></html>"""


def login_page(error: str | None = None, email_prefill: str = "") -> str:
    err = (
        f'<div class="flash error">{escape(error)}</div>'
        if error
        else ""
    )
    body = f"""<h1>Sign in</h1>{err}
<form action="/app/login" method="post">
<label for="email">Email</label>
<input type="email" name="email" id="email" required value="{escape(email_prefill)}">
<label for="password">Password</label>
<input type="password" name="password" id="password" required>
<button type="submit">Sign in</button>
</form>
<p class="muted">No account? PaperGuard uses <strong>invite-only</strong>
registration. Ask an admin for an invite link.</p>"""
    return _page("Sign in", body)


def redeem_page(
    code: str,
    invite: InviteCode | None,
    error: str | None = None,
) -> str:
    if invite is None:
        return _page(
            "Invalid invite",
            '<h1>Invalid invite</h1><p>This invite code is not valid '
            'or has already been used.</p>',
        )
    if invite.is_redeemed:
        return _page(
            "Used invite",
            '<h1>Invite already used</h1><p>This invite link has '
            "already been redeemed. Ask your admin for a fresh one.</p>",
        )
    err = (
        f'<div class="flash error">{escape(error)}</div>'
        if error
        else ""
    )
    body = f"""<h1>Create your account</h1>
<p>You were invited as <strong>{escape(invite.email)}</strong>.</p>{err}
<form action="/app/redeem/{escape(code)}" method="post">
<label for="display_name">Display name</label>
<input type="text" name="display_name" id="display_name" required>
<label for="password">Choose a password (min 10 chars)</label>
<input type="password" name="password" id="password" minlength="10" required>
<button type="submit">Create account</button>
</form>"""
    return _page("Redeem invite", body)


def dashboard(user: User, projects: list[Project]) -> str:
    if not projects:
        rows = (
            '<tr><td colspan="3" class="muted">No projects yet — '
            'create one below.</td></tr>'
        )
    else:
        rows = "".join(
            f'<tr><td><a href="/app/projects/{p.id}">{escape(p.name)}</a></td>'
            f'<td>{len(p.reports)}</td>'
            f'<td class="muted">{p.created_at.date().isoformat()}</td></tr>'
            for p in projects
        )
    body = f"""<h1>Your projects</h1>
<table>
<thead><tr><th>Name</th><th>Reports</th><th>Created</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<h2>New project</h2>
<form action="/app/projects" method="post">
<label for="name">Project name</label>
<input type="text" name="name" id="name" maxlength="160" required>
<label for="description">Description (optional)</label>
<textarea name="description" id="description" rows="3"></textarea>
<button type="submit">Create project</button>
</form>"""
    return _page("Dashboard", body, user)


def project_page(
    user: User,
    project: Project,
    reports: list[ScanReport],
    error: str | None = None,
) -> str:
    err = (
        f'<div class="flash error">{escape(error)}</div>'
        if error
        else ""
    )
    if not reports:
        rows = (
            '<tr><td colspan="5" class="muted">No scans yet — upload '
            "a file below.</td></tr>"
        )
    else:
        rows = "".join(
            f'<tr><td><a href="/app/reports/{r.id}">{escape(r.filename)}</a></td>'
            f'<td><span class="badge {escape(r.severity_max)}">'
            f'{escape(r.severity_max)}</span></td>'
            f"<td>{r.n_findings}</td>"
            f"<td>{escape(r.visibility.value)}</td>"
            f'<td class="muted">{r.created_at.strftime("%Y-%m-%d %H:%M UTC")}</td>'
            "</tr>"
            for r in reports
        )
    body = f"""<h1>{escape(project.name)}</h1>
<p class="muted">{escape(project.description) or "<em>No description</em>"}</p>
{err}
<table>
<thead><tr><th>File</th><th>Severity</th><th>Findings</th>
<th>Visibility</th><th>Scanned</th></tr></thead>
<tbody>{rows}</tbody>
</table>
<h2>Upload a new scan</h2>
<form action="/app/projects/{project.id}/scan" method="post"
      enctype="multipart/form-data">
<label for="file">Data file (.csv / .xlsx / .docx / .pdf)</label>
<input type="file" name="file" id="file" required
       accept=".csv,.tsv,.xlsx,.xlsm,.docx,.pdf">
<label for="visibility">Visibility</label>
<select name="visibility" id="visibility">
<option value="private" selected>Private (only you)</option>
<option value="org">Org (any signed-in user)</option>
<option value="public">Public (anyone)</option>
</select>
<button type="submit">Scan and save</button>
</form>"""
    return _page(project.name, body, user)


def _render_findings(report_payload: dict[str, Any]) -> str:
    findings = report_payload.get("findings") or []
    if not findings:
        return '<p class="muted">No findings — all detectors passed.</p>'
    rows = []
    for f in findings:
        sev = escape(str(f.get("severity", "PASS")))
        rows.append(
            f'<tr><td><strong>{escape(str(f.get("detector_id", "?")))}</strong></td>'
            f'<td><span class="badge {sev}">{sev}</span></td>'
            f'<td>{escape(str(f.get("message", "")))}</td></tr>'
        )
    return (
        "<table><thead><tr><th>Detector</th><th>Severity</th>"
        "<th>Message</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
    )


def report_page(
    user: User | None,
    report: ScanReport,
    payload: dict[str, Any],
) -> str:
    body = f"""<h1>{escape(report.filename)}</h1>
<p class="muted">SHA-256 <code>{escape(report.sha256)}</code></p>
<p>Severity: <span class="badge {escape(report.severity_max)}">
{escape(report.severity_max)}</span> — {report.n_findings} findings —
Visibility: <strong>{escape(report.visibility.value)}</strong></p>
<h2>Findings</h2>
{_render_findings(payload)}
<p><a href="/app/reports/{report.id}/raw.json">Raw JSON</a></p>"""
    return _page(report.filename, body, user)


def shared_list_page(user: User | None, reports: list[ScanReport]) -> str:
    if not reports:
        rows = (
            '<tr><td colspan="4" class="muted">No public reports yet.</td></tr>'
        )
    else:
        rows = "".join(
            f'<tr><td><a href="/app/reports/{r.id}">{escape(r.filename)}</a></td>'
            f'<td><span class="badge {escape(r.severity_max)}">'
            f"{escape(r.severity_max)}</span></td>"
            f"<td>{r.n_findings}</td>"
            f'<td class="muted">{r.created_at.strftime("%Y-%m-%d")}</td></tr>'
            for r in reports
        )
    body = f"""<h1>Public reports</h1>
<p class="muted">Reports their authors have marked <code>public</code>.</p>
<table>
<thead><tr><th>File</th><th>Severity</th><th>Findings</th>
<th>Scanned</th></tr></thead>
<tbody>{rows}</tbody>
</table>"""
    return _page("Public", body, user)


def invites_page(
    user: User,
    invites: list[InviteCode],
    base_url: str,
    error: str | None = None,
) -> str:
    err = (
        f'<div class="flash error">{escape(error)}</div>'
        if error
        else ""
    )
    rows: list[str] = []
    for inv in invites:
        if inv.is_redeemed:
            status_cell = (
                f'<span class="muted">redeemed '
                f"{inv.redeemed_at.strftime('%Y-%m-%d') if inv.redeemed_at else ''}"
                "</span>"
            )
        else:
            link = f"{base_url.rstrip('/')}/app/redeem/{inv.code}"
            status_cell = f'<code>{escape(link)}</code>'
        rows.append(
            f"<tr><td>{escape(inv.email)}</td>"
            f"<td>{escape(inv.role.value)}</td>"
            f"<td>{status_cell}</td>"
            f'<td class="muted">{inv.created_at.strftime("%Y-%m-%d")}</td></tr>'
        )
    rows_html = "".join(rows) or (
        '<tr><td colspan="4" class="muted">No invites yet.</td></tr>'
    )
    body = f"""<h1>Invites</h1>{err}
<h2>Mint a new invite</h2>
<form action="/app/admin/invites" method="post">
<label for="email">Invitee email</label>
<input type="email" name="email" id="email" required>
<label for="role">Role</label>
<select name="role" id="role">
<option value="member" selected>Member</option>
<option value="admin">Admin</option>
</select>
<button type="submit">Create invite</button>
</form>
<h2>Existing invites</h2>
<table>
<thead><tr><th>Email</th><th>Role</th><th>Redemption link / status</th>
<th>Created</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>"""
    return _page("Invites", body, user)


def format_timestamp(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def visibility_label(v: Visibility) -> str:
    return {
        Visibility.PRIVATE: "Private",
        Visibility.ORG: "Org",
        Visibility.PUBLIC: "Public",
    }[v]
