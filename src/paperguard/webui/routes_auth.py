"""Auth routes mounted under /app: login / logout / invite redemption."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Form, HTTPException, Request, Response, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from paperguard.webui.deps import CurrentUser, CurrentUserOptional, DBSession
from paperguard.webui.models import InviteCode, User, UserRole
from paperguard.webui.ratelimit import get_rate_limiter
from paperguard.webui.security import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SECONDS,
    behind_proxy,
    client_ip,
    encode_session,
    hash_password,
    verify_password,
)
from paperguard.webui.templates import login_page, redeem_page

router = APIRouter()

# Per-IP rate limits on auth endpoints (2.3.0). Defaults are deliberately
# conservative — login is the most common credential-stuffing target.
_LOGIN_MAX_REQUESTS = 10
_LOGIN_WINDOW_SECONDS = 300  # 10 attempts per 5 min per IP
_REDEEM_MAX_REQUESTS = 5
_REDEEM_WINDOW_SECONDS = 600  # 5 attempts per 10 min per IP


@router.get("/login", response_class=HTMLResponse)
async def login_form(user: CurrentUserOptional) -> HTMLResponse:
    if user is not None:
        return HTMLResponse(
            status_code=status.HTTP_303_SEE_OTHER,
            content="",
            headers={"location": "/app"},
        )
    return HTMLResponse(login_page())


@router.post("/login")
async def login_submit(
    request: Request,
    session: DBSession,
    email: str = Form(...),
    password: str = Form(...),
) -> Response:
    # Per-IP rate-limit on /login to defend against credential stuffing.
    # 10 attempts per 5 min per source IP. Successful logins also count
    # against the budget, but that's the right call: an attacker who
    # cycles credentials and happens to find a working one shouldn't
    # have a free pass on the next 9 attempts.
    limiter = get_rate_limiter()
    ip = client_ip(request)
    decision = limiter.hit(
        f"login:ip:{ip}",
        max_requests=_LOGIN_MAX_REQUESTS,
        window_seconds=_LOGIN_WINDOW_SECONDS,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many login attempts from this IP. "
                f"Try again in {decision.retry_after_seconds:.0f} s."
            ),
            headers={"Retry-After": str(int(decision.retry_after_seconds) + 1)},
        )

    normalised = email.strip().lower()
    user = await session.scalar(select(User).where(User.email == normalised))
    if (
        user is None
        or not user.is_active
        or not verify_password(password, user.password_hash)
    ):
        return HTMLResponse(
            login_page(error="Invalid email or password.", email_prefill=normalised),
            status_code=status.HTTP_401_UNAUTHORIZED,
        )
    token = encode_session(user.id)
    resp = RedirectResponse("/app", status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=behind_proxy(),
    )
    return resp


@router.post("/logout")
async def logout(_user: CurrentUser) -> Response:
    resp = RedirectResponse("/app/login", status_code=status.HTTP_303_SEE_OTHER)
    resp.delete_cookie(SESSION_COOKIE_NAME)
    return resp


@router.get("/redeem/{code}", response_class=HTMLResponse)
async def redeem_form(code: str, session: DBSession) -> HTMLResponse:
    invite = await session.scalar(
        select(InviteCode).where(InviteCode.code == code)
    )
    return HTMLResponse(redeem_page(code, invite))


@router.post("/redeem/{code}")
async def redeem_submit(
    code: str,
    request: Request,
    session: DBSession,
    display_name: str = Form(...),
    password: str = Form(...),
) -> Response:
    # Per-IP rate-limit on /redeem to slow invite-code brute-force.
    # 5 attempts per 10 min per source IP. Stricter than /login because
    # invite codes are higher-entropy targets and there's no legitimate
    # reason a single IP would redeem more than a handful in 10 min.
    limiter = get_rate_limiter()
    ip = client_ip(request)
    decision = limiter.hit(
        f"redeem:ip:{ip}",
        max_requests=_REDEEM_MAX_REQUESTS,
        window_seconds=_REDEEM_WINDOW_SECONDS,
    )
    if not decision.allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Too many redeem attempts from this IP. "
                f"Try again in {decision.retry_after_seconds:.0f} s."
            ),
            headers={"Retry-After": str(int(decision.retry_after_seconds) + 1)},
        )

    invite = await session.scalar(
        select(InviteCode).where(InviteCode.code == code)
    )
    if invite is None or invite.is_redeemed:
        return HTMLResponse(redeem_page(code, invite))
    if len(password) < 10:
        return HTMLResponse(
            redeem_page(
                code, invite, error="Password must be at least 10 characters."
            ),
            status_code=status.HTTP_400_BAD_REQUEST,
        )
    # Ensure the invited email is still unused.
    existing = await session.scalar(select(User).where(User.email == invite.email))
    if existing is not None:
        return HTMLResponse(
            redeem_page(
                code,
                invite,
                error="An account with this email already exists.",
            ),
            status_code=status.HTTP_409_CONFLICT,
        )
    new_user = User(
        email=invite.email,
        display_name=display_name.strip()[:120] or invite.email.split("@", 1)[0],
        password_hash=hash_password(password),
        role=invite.role,
        is_active=True,
    )
    session.add(new_user)
    await session.flush()
    invite.redeemed_at = datetime.now(UTC)
    invite.redeemed_user_id = new_user.id
    await session.commit()
    await session.refresh(new_user)
    token = encode_session(new_user.id)
    resp = RedirectResponse("/app", status_code=status.HTTP_303_SEE_OTHER)
    resp.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_MAX_AGE_SECONDS,
        httponly=True,
        samesite="lax",
        secure=behind_proxy(),
    )
    return resp


def _verify_admin_role(user: User) -> bool:
    """Convenience used by /app/admin routes for clarity in tests."""
    return user.role == UserRole.ADMIN
