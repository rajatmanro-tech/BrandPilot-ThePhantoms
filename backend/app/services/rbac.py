from fastapi import HTTPException, status


ROLE_PERMISSIONS = {
    "owner": [
        "brand:read",
        "brand:update",
        "brand:delete",
        "members:manage",
        "rules:manage",
        "reports:read",
        "reviews:decide",
    ],
    "admin": [
        "brand:read",
        "brand:update",
        "members:manage",
        "rules:manage",
        "reports:read",
        "reviews:decide",
    ],
    "viewer": [
        "brand:read",
        "reports:read",
    ],
}


def check_permission(role: str, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS.get(role, [])
    return permission in permissions


def require_permission(role: str, permission: str):
    if not check_permission(role, permission):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to perform this action.",
        )