"""轻量增量迁移：为已存在的库补齐新增列。

设计取舍：本项目定位「单文件可跑」，不引入 Alembic。只需要「加列」这一种能力——
新增列一律可空 + 回填，因此 ALTER TABLE ADD COLUMN 在 SQLite / PostgreSQL 上都安全。
新表由 Base.metadata.create_all 自动创建。
"""
import logging

from sqlalchemy import inspect, text

from app.core.database import engine

logger = logging.getLogger("autoops.migrate")

# {表名: [(列名, 类型, 回填表达式 或 None)]}
_COLUMNS = {
    "users": [
        ("tenant_id", "VARCHAR(32)", "'default'"),
        ("is_super", "BOOLEAN", "0"),
        ("auth_source", "VARCHAR(16)", "'local'"),
        ("display_name", "VARCHAR(64)", "''"),
        ("email", "VARCHAR(128)", "''"),
        ("last_login_at", "DATETIME", None),
    ],
    "host_groups": [("tenant_id", "VARCHAR(32)", "'default'")],
    "hosts": [
        ("tenant_id", "VARCHAR(32)", "'default'"),
        ("last_seen", "DATETIME", None),
        ("probe_at", "DATETIME", None),
        ("probe_latency_ms", "INTEGER", None),
        ("probe_message", "VARCHAR(255)", "''"),
    ],
    "credentials": [("tenant_id", "VARCHAR(32)", "'default'")],
    "tasks": [
        ("tenant_id", "VARCHAR(32)", "'default'"),
        ("artifact_uri", "TEXT", "''"),
        ("max_retries", "INTEGER", "0"),
        ("timeout_seconds", "INTEGER", "0"),
        ("attempts", "INTEGER", "0"),
    ],
    "inspection_templates": [("tenant_id", "VARCHAR(32)", "'default'")],
    "inspection_plans": [("tenant_id", "VARCHAR(32)", "'default'")],
    "inspection_reports": [
        ("tenant_id", "VARCHAR(32)", "'default'"),
        ("artifact_uri", "TEXT", "''"),
    ],
    "alert_configs": [
        ("tenant_id", "VARCHAR(32)", "'default'"),
        ("min_severity", "VARCHAR(16)", "'info'"),
        ("repeat_interval_minutes", "INTEGER", "0"),
    ],
    "audit_logs": [("tenant_id", "VARCHAR(32)", "'default'")],
}


def run_migrations() -> list[str]:
    """幂等地补齐缺失列，返回本次实际新增的列描述。"""
    applied: list[str] = []
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    bool_literal = "FALSE" if engine.dialect.name != "sqlite" else "0"

    for table, columns in _COLUMNS.items():
        if table not in tables:
            continue
        existing = {c["name"] for c in inspector.get_columns(table)}
        for name, type_, backfill in columns:
            if name in existing:
                continue
            expr = backfill
            if expr == "0":
                expr = bool_literal
            try:
                with engine.begin() as conn:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {type_}"))
                    if expr is not None:
                        conn.execute(text(
                            f"UPDATE {table} SET {name} = {expr} WHERE {name} IS NULL"
                        ))
                applied.append(f"{table}.{name}")
                logger.info("迁移：%s 新增列 %s", table, name)
            except Exception as e:  # 并发启动时可能被别人先加了列
                logger.warning("迁移 %s.%s 跳过：%s", table, name, e)
    return applied
