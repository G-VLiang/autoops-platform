"""执行引擎。backend=mock 时模拟 ansible 事件流；ansible 时调用 ansible-runner。

统一返回结构化事件，前端据此渲染实时进度。
"""
import random
import time
from typing import List, Dict, Any, Iterator

from app.core.config import settings


class Executor:
    """执行器门面，按配置选择后端。"""

    def __init__(self, backend: str | None = None):
        self.backend = backend or settings.EXECUTOR_BACKEND

    def run(self, task_type: str, content: str, targets: List[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
        if self.backend == "ansible":
            yield from self._run_ansible(task_type, content, targets)
        else:
            yield from self._run_mock(task_type, content, targets)

    # ---- Mock 后端 ----
    def _run_mock(self, task_type: str, content: str, targets: List[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
        if not targets:
            yield {"event": "info", "host": "all", "message": "没有匹配到目标主机"}
            return

        yield {"event": "info", "host": "all", "message": f"开始执行 {task_type}: {content[:60]}"}
        time.sleep(0.3)

        ok = changed = failed = unreachable = 0
        for t in targets:
            hostname = t.get("hostname", t.get("ip", "unknown"))
            time.sleep(random.uniform(0.2, 0.6))
            # 模拟 5% 不可达、10% 失败，其余成功
            r = random.random()
            if r < 0.05:
                unreachable += 1
                yield {
                    "event": "unreachable", "host": hostname,
                    "message": "连接超时", "stdout": "ssh: connect to host timeout"
                }
            elif r < 0.15:
                failed += 1
                yield {
                    "event": "failed", "host": hostname,
                    "message": "命令执行失败", "stdout": f"$ {content}\ncommand not found"
                }
            else:
                ok += 1
                if random.random() < 0.5:
                    changed += 1
                yield {
                    "event": "ok", "host": hostname,
                    "message": "执行成功",
                    "stdout": f"$ {content}\n(mock output) ok on {hostname}"
                }

        yield {"event": "summary", "host": "all", "message": "执行完成",
               "stdout": "", "summary": {"ok": ok, "changed": changed, "failed": failed, "unreachable": unreachable}}

    # ---- Ansible 后端（接入 ansible-runner）----
    def _run_ansible(self, task_type: str, content: str, targets: List[Dict[str, Any]]) -> Iterator[Dict[str, Any]]:
        try:
            import ansible_runner
        except ImportError:
            yield {"event": "info", "host": "all",
                   "message": "未安装 ansible-runner，已回退到 mock 模式，请 pip install ansible-runner"}
            yield from self._run_mock(task_type, content, targets)
            return

        if not targets:
            yield {"event": "info", "host": "all", "message": "没有匹配到目标主机"}
            return

        inventory_hosts = [f"{t.get('hostname')} ansible_host={t.get('ip')} ansible_port={t.get('port', 22)}"
                           for t in targets]
        # ansible-runner 需要 ssh 免密或凭据，此处需通过 extravars/凭据注入；
        # 无凭据时连接会 unreachable，事件流会如实反映。
        run_args = {
            "inventory": "\n".join(inventory_hosts),
            "quiet": True,
        }

        ok = changed = failed = unreachable = 0
        try:
            if task_type == "adhoc":
                res = ansible_runner.run(
                    host_pattern="all", module="shell", module_args=content, **run_args,
                )
            else:
                # playbook / inspection
                res = ansible_runner.run(playbook=_write_tmp_playbook(content), **run_args)

            if res is None:
                yield {"event": "info", "host": "all", "message": "ansible-runner 无结果返回"}
                return

            for host_ev in res.events:
                ev = host_ev.get("event", "")
                host = host_ev.get("event_data", {}).get("host", "all")
                if ev == "runner_on_ok":
                    ok += 1
                    yield {"event": "ok", "host": host, "message": "执行成功",
                           "stdout": str(host_ev.get("event_data", {}).get("res", {}))[:500]}
                elif ev == "runner_on_failed":
                    failed += 1
                    yield {"event": "failed", "host": host, "message": "执行失败",
                           "stdout": str(host_ev.get("event_data", {}).get("res", {}))[:500]}
                elif ev == "runner_on_unreachable":
                    unreachable += 1
                    yield {"event": "unreachable", "host": host, "message": "主机不可达",
                           "stdout": str(host_ev.get("event_data", {}).get("msg", ""))[:500]}
                elif ev == "runner_on_changed":
                    pass  # changed 已在 ok 中体现，这里不重复计数

        except Exception as e:
            yield {"event": "failed", "host": "all", "message": f"ansible 执行异常: {e}", "stdout": ""}

        yield {"event": "summary", "host": "all", "message": "执行完成",
               "stdout": "", "summary": {"ok": ok, "changed": 0, "failed": failed, "unreachable": unreachable}}


def _write_tmp_playbook(content: str) -> str:
    import tempfile
    import os
    fd, path = tempfile.mkstemp(suffix=".yml", prefix="autoops_")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return path


executor = Executor()
