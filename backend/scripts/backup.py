"""数据库与产物备份 / 恢复 / 校验。

用法（在 backend 目录）：
    python scripts/backup.py                       # 备份数据库到 backups/
    python scripts/backup.py --with-artifacts      # 连产物目录一起打包
    python scripts/backup.py --list                # 列出已有备份
    python scripts/backup.py --restore 20261030-120000   # 从该备份恢复
    python scripts/backup.py --prune --keep 7      # 只保留最近 7 份

设计：
- SQLite 用 sqlite3 的在线备份 API（Business 场景下不锁库、不中断服务）；
  PostgreSQL 调用 pg_dump（需系统已安装客户端）。
- 备份目录内含 manifest.json（时间、库类型、大小、sha256），恢复前先验哈希。
- 恢复前会把当前数据库另存为 .pre-restore，误操作可回退。
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

try:
    from app.core.config import settings
except Exception:  # 允许在没装依赖的环境里只看帮助
    settings = None


def _cfg(name: str, default: str = "") -> str:
    if settings is not None:
        return str(getattr(settings, name, default) or default)
    return os.environ.get(name, default)


def _db_url() -> str:
    return _cfg("DATABASE_URL", "sqlite:///./autoops.db")


def _sqlite_path(url: str) -> Path:
    raw = url.replace("sqlite:///", "").replace("sqlite://", "")
    p = Path(raw)
    return p if p.is_absolute() else (BACKEND_DIR / p).resolve()


def _backup_root() -> Path:
    root = Path(os.environ.get("BACKUP_DIR", BACKEND_DIR / "backups"))
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.1f}TB"


# ---------------------------------------------------------------- 备份
def do_backup(with_artifacts: bool = False, keep: int = 0) -> Path:
    url = _db_url()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = _backup_root() / stamp
    target.mkdir(parents=True, exist_ok=True)
    manifest: dict = {"created_at": datetime.now().isoformat(timespec="seconds"),
                      "database_url_scheme": url.split("://")[0], "files": {}}

    if url.startswith("sqlite"):
        src = _sqlite_path(url)
        if not src.exists():
            raise SystemExit(f"数据库文件不存在: {src}")
        dst = target / "autoops.db"
        # 在线热备份：不锁库，服务照常读写
        with sqlite3.connect(f"file:{src}?mode=ro", uri=True) as s, sqlite3.connect(dst) as d:
            s.backup(d)
        manifest["files"]["autoops.db"] = {"size": dst.stat().st_size, "sha256": _sha256(dst)}
        print(f"[1/3] 数据库已备份: {dst.name} ({_human(dst.stat().st_size)})")
    else:
        dump = target / "autoops.sql.gz"
        cmd = ["pg_dump", "--no-owner", "--no-privileges", url.replace("postgresql+psycopg2", "postgresql")]
        try:
            res = subprocess.run(cmd, capture_output=True, timeout=600)
        except FileNotFoundError:
            raise SystemExit("未找到 pg_dump，请先安装 PostgreSQL 客户端（postgresql-client）")
        if res.returncode != 0:
            raise SystemExit(f"pg_dump 失败: {res.stderr.decode(errors='replace')[:400]}")
        with gzip.open(dump, "wb") as f:
            f.write(res.stdout)
        manifest["files"]["autoops.sql.gz"] = {"size": dump.stat().st_size, "sha256": _sha256(dump)}
        print(f"[1/3] 数据库已导出: {dump.name} ({_human(dump.stat().st_size)})")

    art_dir = Path(_cfg("ARTIFACT_DIR", "./data/artifacts"))
    if not art_dir.is_absolute():
        art_dir = (BACKEND_DIR / art_dir).resolve()
    if with_artifacts and art_dir.exists():
        tar = target / "artifacts.tar.gz"
        with tarfile.open(tar, "w:gz") as t:
            t.add(art_dir, arcname="artifacts")
        manifest["files"]["artifacts.tar.gz"] = {"size": tar.stat().st_size, "sha256": _sha256(tar)}
        print(f"[2/3] 产物体积: {_human(tar.stat().st_size)}")
    else:
        print("[2/3] 跳过产物目录" + ("" if with_artifacts else "（加 --with-artifacts 可一并备份）"))

    (target / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[3/3] 备份完成: {target}")

    if keep > 0:
        prune(keep)
    return target


def prune(keep: int) -> None:
    root = _backup_root()
    dirs = sorted([d for d in root.iterdir() if d.is_dir()], key=lambda p: p.name)
    for d in dirs[:-keep] if len(dirs) > keep else []:
        shutil.rmtree(d, ignore_errors=True)
        print(f"  已清理旧备份: {d.name}")


def list_backups() -> None:
    root = _backup_root()
    dirs = sorted([d for d in root.iterdir() if d.is_dir()], key=lambda p: p.name, reverse=True)
    if not dirs:
        print(f"{root} 下暂无备份")
        return
    print(f"备份目录: {root}\n")
    print(f"{'备份 ID':<18}{'时间':<22}{'大小':>10}  内容")
    for d in dirs:
        mf = d / "manifest.json"
        meta = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
        size = sum(f["size"] for f in meta.get("files", {}).values()) or sum(
            f.stat().st_size for f in d.iterdir() if f.is_file())
        files = ", ".join(meta.get("files", {}).keys())
        print(f"{d.name:<18}{meta.get('created_at', '-'):<22}{_human(size):>10}  {files}")


def verify(target: Path) -> bool:
    """校验备份完整性（哈希 + 表结构可读）。"""
    mf = target / "manifest.json"
    if not mf.exists():
        print(f"缺少 manifest.json: {target}")
        return False
    meta = json.loads(mf.read_text(encoding="utf-8"))
    ok = True
    for name, info in meta.get("files", {}).items():
        f = target / name
        if not f.exists():
            print(f"  缺失文件: {name}")
            ok = False
            continue
        if _sha256(f) != info["sha256"]:
            print(f"  哈希不匹配（文件被改动或损坏）: {name}")
            ok = False
        else:
            print(f"  校验通过: {name} ({_human(info['size'])})")
    db = target / "autoops.db"
    if db.exists():
        try:
            with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
                tables = [r[0] for r in c.execute(
                    "select name from sqlite_master where type='table'").fetchall()]
                hosts = c.execute("select count(*) from hosts").fetchone()[0] if "hosts" in tables else 0
                tasks = c.execute("select count(*) from tasks").fetchone()[0] if "tasks" in tables else 0
            print(f"  数据库可读: {len(tables)} 张表，主机 {hosts} 台，任务 {tasks} 个")
        except Exception as e:
            print(f"  数据库无法打开: {e}")
            ok = False
    return ok


# ---------------------------------------------------------------- 恢复
def do_restore(backup_id: str, force: bool = False) -> None:
    target = _backup_root() / backup_id
    if not target.exists():
        # 允许传完整路径
        target = Path(backup_id)
    if not target.exists():
        raise SystemExit(f"备份不存在: {backup_id}")
    if force:
        print(f"跳过校验，直接从 {target} 恢复")
    elif not verify(target):
        raise SystemExit("备份校验失败，已中止恢复（如确认无误可加 --force）")

    url = _db_url()
    if url.startswith("sqlite"):
        dst = _sqlite_path(url)
        src = target / "autoops.db"
        if not src.exists():
            raise SystemExit("该备份不含 autoops.db")
        if dst.exists():
            aside = dst.with_suffix(f".pre-restore-{datetime.now():%Y%m%d%H%M%S}.db")
            shutil.copy2(dst, aside)
            print(f"当前数据库已另存: {aside.name}")
        shutil.copy2(src, dst)
        print(f"已恢复数据库 -> {dst}")
    else:
        dump = target / "autoops.sql.gz"
        if not dump.exists():
            raise SystemExit("该备份不含 SQL 导出文件")
        with gzip.open(dump, "rb") as f:
            res = subprocess.run(["psql", "-f", "-"], stdin=f, capture_output=True, timeout=1800)
        if res.returncode != 0:
            raise SystemExit(f"psql 恢复失败: {res.stderr.decode(errors='replace')[:400]}")
        print("已恢复 PostgreSQL 数据")

    tar = target / "artifacts.tar.gz"
    if tar.exists():
        art_dir = Path(_cfg("ARTIFACT_DIR", "./data/artifacts"))
        if not art_dir.is_absolute():
            art_dir = (BACKEND_DIR / art_dir).resolve()
        with tempfile.TemporaryDirectory() as tmp:
            with tarfile.open(tar) as t:
                t.extractall(tmp)
            src = Path(tmp) / "artifacts"
            if src.exists():
                shutil.copytree(src, art_dir, dirs_exist_ok=True)
                print(f"已恢复产物目录 -> {art_dir}")

    print("\n恢复完成。如果服务正在运行，请重启以加载新数据。")


def main() -> None:
    ap = argparse.ArgumentParser(description="AutoOps 备份/恢复工具")
    ap.add_argument("--with-artifacts", action="store_true", help="连产物目录一起打包")
    ap.add_argument("--keep", type=int, default=0, help="备份后只保留最近 N 份（0=不清理）")
    ap.add_argument("--prune", action="store_true", help="只做清理，不备份")
    ap.add_argument("--list", action="store_true", help="列出已有备份")
    ap.add_argument("--restore", metavar="ID", help="从指定备份恢复")
    ap.add_argument("--verify", metavar="ID", help="只校验指定备份")
    ap.add_argument("--force", action="store_true", help="跳过校验强制恢复（危险）")
    args = ap.parse_args()

    if args.list:
        list_backups()
    elif args.prune:
        prune(args.keep or 7)
    elif args.verify:
        target = _backup_root() / args.verify
        ok = verify(target if target.exists() else Path(args.verify))
        sys.exit(0 if ok else 1)
    elif args.restore:
        do_restore(args.restore, force=args.force)
    else:
        do_backup(args.with_artifacts, args.keep)


if __name__ == "__main__":
    main()
