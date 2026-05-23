from fastapi import Depends, HTTPException

from .admin_config import is_super_admin
from .deps import current_user
from .models import User


def require_admin(user: User = Depends(current_user)) -> User:
    if not is_super_admin(user):
        raise HTTPException(
            status_code=403,
            detail={"error": {"code": "forbidden", "message": "admin only"}},
        )
    return user
