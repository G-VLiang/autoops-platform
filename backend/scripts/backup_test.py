"""备份/恢复自检：备份 → 校验 → 破坏数据 → 恢复 → 确认数据回滚。

不触碰真实数据库（全部在临时目录），可在任意环境重复执行。
"""
import importlib.util
import os
import sys
import tempfile
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TMP = Path(tempfile.mkdtemp(prefix="autoops_backup_"))
os.environ["DATABASE_URL"] = f"sqlite:///{TMP / 'app.db'}"
os.environ["BACKUP_DIR"] = str(TMP / "backups")
os.environ["ARTIFACT_DIR"] = str(TMP / "artifacts")

sys.path.insert(0, str(BACKEND))

from app.core.database import Base, SessionLocal, engine  # noqa: E402
from app.models import Host, Tenant, DEFAULT_TENANT_ID  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, extra=""):
    if cond:
        PASSED.append(name)
        print(f"  [OK] {name}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name} {extra}")


def load_backup_module():
    spec = importlib.util.spec_from_file_location(
        "backup_mod", BACKEND / "scripts" / "backup.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def main():
    print("\n== 备份 / 恢复自检 ==")
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    db.add(Tenant(id=DEFAULT_TENANT_ID, code="default", name="默认租户"))
    db.add(Host(hostname="web-01", ip="10.0.0.1", tenant_id=DEFAULT_TENANT_ID, status="online"))
    db.add(Host(hostname="db-01", ip="10.0.0.2", tenant_id=DEFAULT_TENANT_ID, status="online"))
    db.commit()
    db.close()

    bk = load_backup_module()

    # 1. 备份
    print("\n-- 1. 执行备份 --")
    target = bk.do_backup(with_artifacts=False)
    check("备份目录已生成", target.exists(), str(target))
    check("数据库快照存在", (target / "autoops.db").exists())
    check("manifest 存在", (target / "manifest.json").exists())

    # 2. 校验
    print("\n-- 2. 校验完整性 --")
    check("校验通过", bk.verify(target) is True)

    # 3. 破坏数据（模拟误删）
    print("\n-- 3. 模拟误删数据 --")
    db = SessionLocal()
    db.query(Host).delete()
    db.commit()
    remain = db.query(Host).count()
    db.close()
    check("数据已被清空", remain == 0, f"剩余 {remain}")

    # 4. 恢复
    print("\n-- 4. 从备份恢复 --")
    bk.do_restore(target.name)

    db = SessionLocal()
    try:
        restored = db.query(Host).count()
    finally:
        db.close()
    check("主机数据已恢复", restored == 2, f"恢复后 {restored} 台")
    check("恢复前旧库已另存", len(list(TMP.glob("*.pre-restore-*.db"))) >= 1)

    # 5. 篡改检测
    print("\n-- 5. 篡改检测 --")
    db_file = target / "autoops.db"
    with open(db_file, "ab") as f:
        f.write(b"tampered")
    check("篡改后校验失败", bk.verify(target) is False)

    # 6. 轮转清理
    print("\n-- 6. 保留策略 --")
    (TMP / "backups" / "20000101-000000").mkdir(parents=True, exist_ok=True)
    bk.prune(keep=1)
    kept = [d.name for d in (TMP / "backups").iterdir() if d.is_dir()]
    check("只保留 1 份", len(kept) == 1, str(kept))

    print(f"\n通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        print("失败项:", FAILED)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
