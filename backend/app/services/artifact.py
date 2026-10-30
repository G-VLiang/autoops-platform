"""任务产物归档：把执行明细（含完整日志）落到本地磁盘或 S3 兼容对象存储。

为什么要归档：数据库只适合存结构化摘要，ansible 的原始 stdout 体积大、留存久。
把明细压缩成 JSON 存对象存储，数据库只保留一个 URI，库更轻、也便于外部审计系统取用。

后端：
- local：默认，落 ARTIFACT_DIR，零依赖
- s3   ：任意 S3 兼容存储（AWS S3 / MinIO / 阿里云 OSS / 腾讯云 COS），需 pip install boto3
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings

logger = logging.getLogger("autoops.artifact")


class ArtifactError(RuntimeError):
    pass


class ArtifactStore:
    """产物存储门面。失败时降级为「不归档」，绝不能影响任务本身的结果。"""

    def __init__(self, backend: str | None = None):
        self.backend = (backend or settings.ARTIFACT_BACKEND or "local").lower()

    # ---------------- 写入 ----------------
    def put_json(self, key: str, data: Dict[str, Any]) -> str:
        payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        body = gzip.compress(payload, compresslevel=6)
        if self.backend == "s3":
            return self._s3_put(key, body)
        return self._local_put(key, body)

    def _local_put(self, key: str, body: bytes) -> str:
        base = Path(settings.ARTIFACT_DIR).resolve()
        target = (base / key).resolve()
        if not str(target).startswith(str(base)):
            raise ArtifactError("非法的产物路径")
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".tmp")
        tmp.write_bytes(body)
        os.replace(tmp, target)
        return f"local:{key}"

    def _s3_put(self, key: str, body: bytes) -> str:
        client = _s3_client()
        bucket = settings.ARTIFACT_S3_BUCKET
        client.put_object(Bucket=bucket, Key=key, Body=body,
                          ContentType="application/json", ContentEncoding="gzip")
        return f"s3://{bucket}/{key}"

    # ---------------- 读取 ----------------
    def read_json(self, uri: str) -> Dict[str, Any]:
        if uri.startswith("s3://"):
            bucket, _, key = uri[5:].partition("/")
            obj = _s3_client().get_object(Bucket=bucket, Key=key)
            raw = obj["Body"].read()
        elif uri.startswith("local:"):
            path = Path(settings.ARTIFACT_DIR).resolve() / uri[len("local:"):]
            if not path.is_file():
                raise ArtifactError("产物不存在或已被清理")
            raw = path.read_bytes()
        else:
            raise ArtifactError(f"不支持的产物地址: {uri}")
        try:
            raw = gzip.decompress(raw)
        except OSError:
            pass
        return json.loads(raw.decode("utf-8"))

    def local_file(self, uri: str) -> Optional[Path]:
        if not uri.startswith("local:"):
            return None
        path = (Path(settings.ARTIFACT_DIR).resolve() / uri[len("local:"):]).resolve()
        return path if path.is_file() else None

    def presigned_url(self, uri: str) -> Optional[str]:
        """S3 后端返回临时下载链接；本地后端由 API 直接流式返回文件。"""
        if self.backend != "s3" or not uri.startswith("s3://"):
            return None
        bucket, _, key = uri[5:].partition("/")
        try:
            return _s3_client().generate_presigned_url(
                "get_object",
                Params={"Bucket": bucket, "Key": key},
                ExpiresIn=settings.ARTIFACT_PRESIGN_SECONDS,
            )
        except Exception as e:
            logger.warning("生成预签名链接失败: %s", e)
            return None

    # ---------------- 清理 ----------------
    def cleanup(self, days: Optional[int] = None) -> int:
        days = settings.ARTIFACT_RETENTION_DAYS if days is None else days
        if not days or days <= 0 or self.backend != "local":
            return 0
        base = Path(settings.ARTIFACT_DIR)
        if not base.exists():
            return 0
        cutoff = time.time() - days * 86400
        removed = 0
        for p in base.rglob("*.json.gz"):
            try:
                if p.stat().st_mtime < cutoff:
                    p.unlink()
                    removed += 1
            except OSError:
                pass
        if removed:
            logger.info("产物清理：删除 %s 个过期文件（>%s 天）", removed, days)
        return removed


_s3_client_cache = {}


def _s3_client():
    try:
        import boto3
    except ImportError:
        raise ArtifactError("未安装 boto3，无法使用 S3 产物存储（pip install boto3）")
    sig = (settings.ARTIFACT_S3_ENDPOINT, settings.ARTIFACT_S3_REGION,
           settings.ARTIFACT_S3_ACCESS_KEY)
    if sig not in _s3_client_cache:
        _s3_client_cache[sig] = boto3.client(
            "s3",
            endpoint_url=settings.ARTIFACT_S3_ENDPOINT or None,
            region_name=settings.ARTIFACT_S3_REGION,
            aws_access_key_id=settings.ARTIFACT_S3_ACCESS_KEY or None,
            aws_secret_access_key=settings.ARTIFACT_S3_SECRET_KEY or None,
        )
    return _s3_client_cache[sig]


def artifact_key(prefix: str, obj_id: str, when: Optional[datetime] = None) -> str:
    when = when or datetime.now(timezone.utc)
    # 多租户下按日期分目录，便于按时间做生命周期清理
    return f"{prefix}/{when:%Y/%m/%d}/{obj_id}.json.gz"


store = ArtifactStore()
