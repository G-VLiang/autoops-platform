"""主机探活。

默认用 TCP 连接 SSH 端口判断可用性（比 ICMP 更贴近"能不能被管"的语义：
端口通了才可能下发任务；很多云主机禁 ping 但 SSH 正常）。
可切换为 ICMP ping（PROBE_METHOD=ping），并发执行，单机超时不阻塞整体。
"""
from __future__ import annotations

import logging
import platform
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Iterable, List, Optional

logger = logging.getLogger("autoops.probe")


def probe_tcp(ip: str, port: int, timeout: float) -> tuple[bool, Optional[int], str]:
    """TCP 握手探测。返回 (online, latency_ms, message)。"""
    started = time.monotonic()
    try:
        with socket.create_connection((ip, port), timeout=timeout):
            latency = int((time.monotonic() - started) * 1000)
            return True, latency, f"tcp/{port} 可达"
    except socket.timeout:
        return False, None, f"tcp/{port} 连接超时"
    except ConnectionRefusedError:
        return False, None, f"tcp/{port} 拒绝连接（主机在线但端口未监听）"
    except socket.gaierror:
        return False, None, "地址解析失败"
    except OSError as e:
        return False, None, f"网络错误: {e}"


def probe_icmp(ip: str, timeout: float) -> tuple[bool, Optional[int], str]:
    """系统 ping 探测（不依赖第三方库；Windows 与 Linux 参数不同）。"""
    is_win = platform.system().lower().startswith("win")
    if is_win:
        cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(max(1, int(timeout))), ip]
    started = time.monotonic()
    try:
        res = subprocess.run(cmd, capture_output=True, timeout=timeout + 2)
        latency = int((time.monotonic() - started) * 1000)
        if res.returncode == 0:
            return True, latency, "icmp 可达"
        return False, None, "icmp 无响应"
    except subprocess.TimeoutExpired:
        return False, None, "icmp 超时"
    except Exception as e:
        return False, None, f"ping 执行失败: {e}"


def probe_one(host: dict, method: str = "tcp", port: Optional[int] = None,
              timeout: float = 3.0) -> dict:
    """探测单台主机，返回结果字典。"""
    ip = host.get("ip") or ""
    target_port = port or host.get("port") or 22
    if method == "ping":
        online, latency, msg = probe_icmp(ip, timeout)
    else:
        online, latency, msg = probe_tcp(ip, int(target_port), timeout)
    return {
        "host_id": host.get("id", ""),
        "hostname": host.get("hostname", ""),
        "ip": ip,
        "online": online,
        "latency_ms": latency,
        "message": msg,
    }


def probe_many(hosts: Iterable[dict], method: str = "tcp", port: Optional[int] = None,
               timeout: float = 3.0, workers: int = 32) -> List[dict]:
    """并发探测多台主机。结果顺序与入参一致。"""
    items = list(hosts)
    if not items:
        return []
    results: List[dict] = []
    with ThreadPoolExecutor(max_workers=max(1, min(workers, len(items)))) as pool:
        futures = [pool.submit(probe_one, h, method, port, timeout) for h in items]
        for f in futures:
            try:
                results.append(f.result())
            except Exception as e:  # 单台异常不影响整体
                logger.warning("探测异常: %s", e)
    return results
