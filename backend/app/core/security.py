from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import logging
import secrets
from typing import Any, Optional
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from ldap3 import ALL, Connection, Server
from ldap3.core.exceptions import LDAPException
from ldap3.utils.conv import escape_filter_chars
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import Department, User, UserRole

logger = logging.getLogger(__name__)
bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    """Hash password with PBKDF2-HMAC-SHA256 using per-password random salt."""
    salt = secrets.token_hex(16)
    iterations = 200_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
    return f"pbkdf2_sha256${iterations}${salt}${digest.hex()}"


def verify_password(password: str, stored_hash: Optional[str]) -> bool:
    if not stored_hash:
        return False
    try:
        algo, iter_str, salt, expected_hex = stored_hash.split("$", 3)
        if algo != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations)
        return hmac.compare_digest(digest.hex(), expected_hex)
    except Exception:
        return False


def normalize_username(raw_username: str) -> str:
    """Strip DOMAIN\\username or username@company.local down to sAMAccountName."""
    username = raw_username.strip()
    if "\\" in username:
        username = username.split("\\", 1)[1]
    if "@" in username:
        username = username.split("@", 1)[0]
    return username.lower()


def _resolve_role_from_ad_groups(member_of: list[str], settings) -> UserRole:
    joined = " | ".join(member_of).lower()
    if settings.LDAP_ADMIN_GROUP and settings.LDAP_ADMIN_GROUP.lower() in joined:
        return UserRole.SYS_ADMIN
    if settings.LDAP_LEAD_GROUP and settings.LDAP_LEAD_GROUP.lower() in joined:
        return UserRole.IT_LEAD
    if settings.LDAP_AGENT_GROUP and settings.LDAP_AGENT_GROUP.lower() in joined:
        return UserRole.IT_AGENT
    return UserRole.END_USER


def authenticate_ldap(raw_username: str, password: str) -> Optional[dict[str, Any]]:
    """
    Synchronously authenticate against Corporate LDAP / Active Directory via ldap3.
    Returns user attributes dict on valid corporate credentials, or None if bind fails.
    """
    settings = get_settings()
    if not settings.LDAP_ENABLED:
        return None
    if not password:
        return None

    username = normalize_username(raw_username)
    bind_user = (
        raw_username.strip()
        if ("@" in raw_username or "\\" in raw_username)
        else settings.LDAP_USER_DN_TEMPLATE.format(
            username=username,
            domain=settings.LDAP_DOMAIN,
        )
    )

    try:
        server = Server(
            settings.LDAP_SERVER_URI,
            use_ssl=settings.LDAP_USE_SSL,
            get_info=ALL,
            connect_timeout=settings.LDAP_BIND_TIMEOUT_SECONDS,
        )
        conn = Connection(
            server,
            user=bind_user,
            password=password,
            receive_timeout=settings.LDAP_BIND_TIMEOUT_SECONDS,
            auto_bind=True,
        )
    except LDAPException as exc:
        logger.info("LDAP bind failed for '%s': %s", username, exc)
        return None
    except Exception as exc:
        logger.warning("Unexpected LDAP error for '%s': %s", username, exc)
        return None

    try:
        escaped_user = escape_filter_chars(username)
        search_filter = settings.LDAP_SEARCH_FILTER.format(username=escaped_user)
        conn.search(
            search_base=settings.LDAP_BASE_DN,
            search_filter=search_filter,
            attributes=["sAMAccountName", "displayName", "cn", "mail", "department", "memberOf", "distinguishedName"],
        )

        if conn.entries:
            entry = conn.entries[0]
            attrs = entry.entry_attributes_as_dict
            sam = (attrs.get("sAMAccountName") or [username])[0]
            full_name = (attrs.get("displayName") or attrs.get("cn") or [sam])[0]
            mail = (attrs.get("mail") or [f"{sam}@company.local"])[0]
            department_name = (attrs.get("department") or [None])[0]
            member_of = [str(g) for g in (attrs.get("memberOf") or [])]
            ldap_dn = (attrs.get("distinguishedName") or [entry.entry_dn])[0]
            role = _resolve_role_from_ad_groups(member_of, settings)
        else:
            sam = username
            full_name = username
            mail = f"{username}@company.local"
            department_name = None
            ldap_dn = bind_user
            role = UserRole.END_USER

        return {
            "username": sam.lower(),
            "full_name": str(full_name),
            "email": str(mail).lower(),
            "department_name": str(department_name) if department_name else None,
            "ldap_dn": str(ldap_dn),
            "role": role,
        }
    finally:
        try:
            conn.unbind()
        except Exception:
            pass


async def _sync_ldap_user(db: AsyncSession, ldap_info: dict[str, Any]) -> User:
    """Upsert an LDAP-authenticated user into the local users table."""
    username = ldap_info["username"]
    result = await db.execute(select(User).where(User.username == username))
    user = result.scalar_one_or_none()

    department_id: Optional[uuid.UUID] = None
    if ldap_info.get("department_name"):
        dept_res = await db.execute(
            select(Department).where(Department.name == ldap_info["department_name"])
        )
        dept = dept_res.scalar_one_or_none()
        if dept:
            department_id = dept.id

    now = datetime.now(timezone.utc)
    if user is None:
        user = User(
            username=username,
            email=ldap_info["email"],
            full_name=ldap_info["full_name"],
            ldap_dn=ldap_info.get("ldap_dn"),
            role=ldap_info.get("role", UserRole.END_USER),
            department_id=department_id,
            is_active=True,
            last_login_at=now,
        )
        db.add(user)
    else:
        user.full_name = ldap_info["full_name"]
        user.email = ldap_info["email"]
        user.ldap_dn = ldap_info.get("ldap_dn")
        if department_id:
            user.department_id = department_id
        user.last_login_at = now

    await db.commit()
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, raw_username: str, password: str) -> Optional[User]:
    """
    Authenticate user via Corporate LDAP first (if enabled).
    Falls back to local password verification when LDAP_ENABLED=false or LDAP_ALLOW_LOCAL_FALLBACK=true.
    """
    settings = get_settings()
    username = normalize_username(raw_username)

    if settings.LDAP_ENABLED:
        ldap_info = authenticate_ldap(raw_username, password)
        if ldap_info is not None:
            return await _sync_ldap_user(db, ldap_info)
        if not settings.LDAP_ALLOW_LOCAL_FALLBACK:
            return None

    if not settings.LDAP_ENABLED or settings.LDAP_ALLOW_LOCAL_FALLBACK:
        stmt = select(User).where(
            or_(User.username == username, User.email == raw_username.strip().lower())
        )
        res = await db.execute(stmt)
        user = res.scalar_one_or_none()
        if user and user.is_active and verify_password(password, user.password_hash):
            user.last_login_at = datetime.now(timezone.utc)
            await db.commit()
            await db.refresh(user)
            return user

    return None


def create_access_token(user: User) -> str:
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "role": user.role.value,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_scoped_token(user: User, scope: str, expires_seconds: int = 300) -> str:
    """Create a short-lived JWT restricted to a specific channel ('ws' or 'media')."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(seconds=expires_seconds)
    payload = {
        "sub": str(user.id),
        "scope": scope,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Vui lòng đăng nhập bằng tài khoản công ty.",
        )

    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        if payload.get("scope") is not None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ cho API này.")
        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token không hợp lệ.")
        user_uuid = uuid.UUID(user_id_str)
    except (JWTError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Phiên đăng nhập hết hạn hoặc không hợp lệ.")

    res = await db.execute(select(User).where(User.id == user_uuid))
    user = res.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tài khoản không tồn tại hoặc đã bị khóa.")
    return user


def require_roles(*allowed_roles: UserRole):
    async def _role_guard(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Bạn không có quyền thực hiện thao tác này.",
            )
        return current_user

    return _role_guard
