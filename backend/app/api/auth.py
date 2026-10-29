"""认证路由。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import verify_password, create_access_token
from app.models import User
from app.schemas import LoginRequest, Token
from app.services.audit import record

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=Token)
def login(payload: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == payload.username).first()
    if not user or not verify_password(payload.password, user.hashed_password):
        record(payload.username, "login", "auth", detail="登录失败", ip="")
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    token = create_access_token(user.username)
    record(user.username, "login", "auth", detail="登录成功", ip="")
    return Token(access_token=token)
