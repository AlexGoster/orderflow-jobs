from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_session
from app.core.exceptions import UnauthorizedError
from app.core.security import decode_access_token
from app.models import User

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    session: AsyncSession = Depends(get_session),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token")
    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise UnauthorizedError("Invalid or expired token")
    user = await session.scalar(select(User).where(User.id == int(subject)))
    if user is None:
        raise UnauthorizedError("User no longer exists")
    return user
