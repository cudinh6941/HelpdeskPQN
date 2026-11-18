from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import authenticate_user, create_access_token, get_current_user
from app.models.models import User
from app.schemas.schemas import DemoAccountOut, LoginRequest, TokenResponse, UserOut

router = APIRouter(prefix="/auth", tags=["Authentication (LDAP / AD)"])


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    settings = get_settings()
    user = await authenticate_user(db, payload.username, payload.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sai tài khoản công ty (LDAP/AD) hoặc mật khẩu.",
        )

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


@router.get("/me", response_model=UserOut)
async def get_me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
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
