from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import login_rate_limiter
from app.core.security import (
    authenticate_user,
    create_access_token,
    create_scoped_token,
    get_current_user,
    normalize_username,
)
from app.models.models import User
from app.schemas.schemas import (
    DemoAccountOut,
    LoginRequest,
    ScopedTokenRequest,
    ScopedTokenResponse,
    TokenResponse,
    UserOut,
    UserProfileUpdate,
)

router = APIRouter(prefix="/auth", tags=["Authentication (LDAP / AD)"])


def _get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        first_ip = forwarded.split(",", 1)[0].strip()
        if first_ip:
            return first_ip
    return request.client.host if request.client else "unknown"


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, request: Request, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    client_ip = _get_client_ip(request)
    norm_user = normalize_username(payload.username)

    retry_after = login_rate_limiter.check_allowed(client_ip, norm_user)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Quá nhiều lần đăng nhập sai. Vui lòng thử lại sau {retry_after} giây để tránh khóa tài khoản công ty.",
            headers={"Retry-After": str(retry_after)},
        )

    user = await authenticate_user(db, payload.username, payload.password)
    if user is None:
        login_rate_limiter.record_failure(client_ip, norm_user)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai tài khoản công ty (LDAP/AD) hoặc mật khẩu.",
        )

    login_rate_limiter.record_success(client_ip, norm_user)
    res = await db.execute(
        select(User).options(selectinload(User.department)).where(User.id == user.id)
    )
    loaded_user = res.scalar_one()
    token = create_access_token(loaded_user)
    provider = "LDAP_AD" if settings.LDAP_ENABLED else "LOCAL_FALLBACK"

    return TokenResponse(
        access_token=token,
        auth_provider=provider,
        user=UserOut.model_validate(loaded_user),
    )


@router.post("/scoped-token", response_model=ScopedTokenResponse)
async def issue_scoped_token(
    payload: ScopedTokenRequest,
    current_user: User = Depends(get_current_user),
):
    expires_in = 60 if payload.scope == "ws" else 300
    token = create_scoped_token(current_user, scope=payload.scope, expires_seconds=expires_in)
    return ScopedTokenResponse(token=token, scope=payload.scope, expires_in=expires_in)


@router.get("/me", response_model=UserOut)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    res = await db.execute(
        select(User).options(selectinload(User.department)).where(User.id == current_user.id)
    )
    return UserOut.model_validate(res.scalar_one())


@router.patch("/me", response_model=UserOut)
async def update_my_profile(
    payload: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if "telegram_chat_id" in payload.model_fields_set:
        current_user.telegram_chat_id = (
            payload.telegram_chat_id.strip() or None
            if payload.telegram_chat_id is not None
            else None
        )
    if "zalo_user_id" in payload.model_fields_set:
        current_user.zalo_user_id = (
            payload.zalo_user_id.strip() or None
            if payload.zalo_user_id is not None
            else None
        )
    await db.commit()
    res = await db.execute(
        select(User).options(selectinload(User.department)).where(User.id == current_user.id)
    )
    return UserOut.model_validate(res.scalar_one())


@router.get("/demo-accounts", response_model=list[DemoAccountOut])
async def list_demo_accounts(db: AsyncSession = Depends(get_db)):
    """List seeded test accounts when local fallback is enabled in non-production."""
    settings = get_settings()
    if not settings.LDAP_ALLOW_LOCAL_FALLBACK:
        return []

    res = await db.execute(
        select(User)
        .options(selectinload(User.department))
        .where(
            User.username.in_(
                ["nhanvien", "nhanvien2", "nhanvien3", "nhanvien4", "kythuat", "truongnhom", "admin"]
            )
        )
        .order_by(User.created_at)
    )
    users = res.scalars().all()
    return [
        DemoAccountOut(
            username=u.username,
            full_name=u.full_name,
            role=u.role,
            department_name=u.department.name if u.department else None,
            default_password="Password123!",
        )
        for u in users
    ]
