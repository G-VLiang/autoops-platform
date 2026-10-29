"""重置用户密码（生产部署后必须改掉默认 admin/admin123）。

用法（在 backend 目录下执行）：
    venv/bin/python scripts/set_admin_password.py admin '新密码'
    venv\\Scripts\\python.exe scripts\\set_admin_password.py admin 新密码   # Windows

不传密码时进入交互输入（不回显）。
"""
import getpass
import sys
from pathlib import Path

# 允许直接以脚本方式运行（把 backend 目录加入 sys.path）
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.database import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models import User  # noqa: E402


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    username = sys.argv[1]
    if len(sys.argv) >= 3:
        password = sys.argv[2]
    else:
        password = getpass.getpass(f"为 {username} 设置新密码: ")
        if password != getpass.getpass("再输入一次确认: "):
            print("两次输入不一致")
            return 1

    if len(password) < 8:
        print("密码太短，至少 8 位")
        return 1

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.username == username).first()
        if not user:
            print(f"用户不存在: {username}")
            return 1
        user.hashed_password = hash_password(password)
        db.commit()
        print(f"已更新 {username} 的密码")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
