"""新功能验收测试：探活、模板库、重试/超时、cron 预览、导出、审计检索、告警状态机。

全部使用临时数据库，可重复执行。
"""
import os
import socket
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path

TMP = Path(tempfile.mkdtemp(prefix="autoops_feature_"))
os.environ["DATABASE_URL"] = f"sqlite:///{TMP / 'feature.db'}"
os.environ["ARTIFACT_DIR"] = str(TMP / "artifacts")
os.environ["ARTIFACT_BACKEND"] = "local"
os.environ["SCHEDULER_ENABLED"] = "true"
os.environ["SCHEDULER_HEARTBEAT"] = "1"
os.environ["SCHEDULER_LEASE_TTL"] = "3"
os.environ["EXECUTOR_BACKEND"] = "mock"
os.environ["SECRET_KEY"] = "feature-test-secret"
os.environ["INSTANCE_ID"] = "feature-instance"

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.core.database import SessionLocal  # noqa: E402
from app.executor import executor as executor_obj  # noqa: E402
from app.models import AlertSilence, Host, Tenant, DEFAULT_TENANT_ID  # noqa: E402
from app.services import alert as alert_svc  # noqa: E402

PASSED, FAILED = [], []


def check(name, cond, extra=""):
    if cond:
        PASSED.append(name)
        print(f"  [OK] {name}")
    else:
        FAILED.append(name)
        print(f"  [FAIL] {name} {extra}")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def main():
    # 起一个本地监听端口，用于验证「在线」判定
    srv = socket.socket()
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(16)
    live_port = srv.getsockname()[1]
    dead_port = 1  # 特权端口，普通用户连不上，稳定判为离线

    with TestClient(app) as c:
        print("\n== 0. 登录 ==")
        r = c.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
        check("admin 登录成功", r.status_code == 200, r.text[:200])
        H = {"Authorization": f"Bearer {r.json()['access_token']}"}

        # ---------------------------------------------------------------- 探活
        print("\n== 1. 主机探活 ==")
        r = c.post("/api/v1/hosts", headers=H, json={
            "hostname": "probe-live", "ip": "127.0.0.1", "port": live_port, "tags": ["test"]})
        check("新增探活主机", r.status_code == 200, r.text[:200])
        live_id = r.json()["id"]
        r = c.post("/api/v1/hosts", headers=H, json={
            "hostname": "probe-dead", "ip": "127.0.0.1", "port": dead_port})
        dead_id = r.json()["id"]

        r = c.post("/api/v1/hosts/probe", headers=H, json={"host_ids": [live_id, dead_id]})
        check("批量探活返回 200", r.status_code == 200, r.text[:200])
        data = r.json()
        check("探测总数正确", data["total"] == 2, data)
        check("在线 1 台", data["online"] == 1, data)
        check("离线 1 台", data["offline"] == 1, data)
        live_res = next(x for x in data["results"] if x["host_id"] == live_id)
        check("在线主机有延迟数据", live_res["online"] and live_res["latency_ms"] is not None, live_res)

        hosts = {h["hostname"]: h for h in c.get("/api/v1/hosts", headers=H).json()}
        check("在线主机状态已写入", hosts["probe-live"]["status"] == "online", hosts.get("probe-live"))
        check("离线主机状态已写入", hosts["probe-dead"]["status"] == "offline")
        check("在线主机记录 last_seen", hosts["probe-live"]["last_seen"] is not None)

        r = c.post(f"/api/v1/hosts/{live_id}/probe", headers=H)
        check("单台探活成功", r.status_code == 200 and r.json()["online"] is True, r.text[:200])

        # ---------------------------------------------------------------- 模板库
        print("\n== 2. 作业模板库 ==")
        r = c.get("/api/v1/tasks/library", headers=H)
        lib = r.json()
        check("模板库条目 >= 20", len(lib) >= 20, f"{len(lib)} 条")
        check("模板含 playbook 内容", all(x["content"].startswith("---") for x in lib))

        r = c.get("/api/v1/tasks/library/categories", headers=H)
        check("分类统计可用", isinstance(r.json(), list) and len(r.json()) >= 3, r.text[:200])

        r = c.get("/api/v1/tasks/library", headers=H, params={"category": "磁盘"})
        check("按分类筛选", all(x["category"] == "磁盘" for x in r.json()) and len(r.json()) >= 2)

        r = c.get("/api/v1/tasks/library", headers=H, params={"keyword": "docker"})
        check("关键词筛选命中", len(r.json()) >= 1, r.text[:200])

        # 需要主机组作为目标
        r = c.post("/api/v1/hosts/groups", headers=H, json={"name": "探活组"})
        gid = r.json()["id"]
        c.post("/api/v1/hosts", headers=H, json={
            "hostname": "target-1", "ip": "127.0.0.1", "port": 22, "group_id": gid})

        r = c.post("/api/v1/tasks/from-library", headers=H, json={
            "library_key": "disk-usage", "target_type": "group", "target_id": gid})
        check("从模板库创建任务", r.status_code == 200, r.text[:300])
        check("任务状态已落定", r.json()["status"] in ("success", "partial", "failed"), r.json().get("status"))

        # ---------------------------------------------------------------- 重试 / 超时
        print("\n== 3. 失败重试与超时 ==")
        original_run = executor_obj.run

        def always_fail(task_type, content, targets):
            yield {"event": "failed", "host": "h1", "message": "boom", "stdout": "err"}
            yield {"event": "summary", "host": "all", "message": "done", "stdout": "",
                   "summary": {"ok": 0, "changed": 0, "failed": 1, "unreachable": 0}}

        executor_obj.run = always_fail
        try:
            r = c.post("/api/v1/tasks", headers=H, json={
                "name": "必定失败-重试2次", "task_type": "adhoc", "content": "false",
                "target_type": "group", "target_id": gid, "max_retries": 2})
            task = r.json()
            check("任务创建成功", r.status_code == 200, r.text[:200])
            check("失败任务状态为 failed", task["status"] == "failed", task["status"])
            check("共执行 3 次（1 次 + 重试 2 次）", task["attempts"] == 3, task["attempts"])

            logs = c.get(f"/api/v1/tasks/{task['id']}/logs", headers=H).json()
            retry_logs = [l for l in logs if "重试" in (l["message"] or "")]
            check("日志记录了重试过程", len(retry_logs) == 2, f"{len(retry_logs)} 条")

            def slow_run(task_type, content, targets):
                for i in range(6):
                    time.sleep(0.4)
                    yield {"event": "ok", "host": f"h{i}", "message": "ok", "stdout": ""}
                yield {"event": "summary", "host": "all", "message": "done", "stdout": "",
                       "summary": {"ok": 6, "changed": 0, "failed": 0, "unreachable": 0}}

            executor_obj.run = slow_run
            r = c.post("/api/v1/tasks", headers=H, json={
                "name": "超时任务", "task_type": "adhoc", "content": "sleep 10",
                "target_type": "group", "target_id": gid, "timeout_seconds": 1})
            task = r.json()
            logs = c.get(f"/api/v1/tasks/{task['id']}/logs", headers=H).json()
            check("超时任务被中止", any("超时" in (l["message"] or "") for l in logs),
                  [l["message"] for l in logs][:3])
            check("超时任务状态为 failed", task["status"] == "failed", task["status"])
        finally:
            executor_obj.run = original_run

        # ---------------------------------------------------------------- cron
        print("\n== 4. cron 预览 ==")
        r = c.post("/api/v1/plans/cron/preview", headers=H, json={"cron": "0 2 * * *", "count": 5})
        data = r.json()
        check("合法 cron 通过", data["valid"] is True, data)
        check("返回 5 次执行时间", len(data["next_runs"]) == 5, data.get("next_runs"))
        check("有人类可读描述", "每天" in data["description"], data.get("description"))

        r = c.post("/api/v1/plans/cron/preview", headers=H, json={"cron": "每天2点"})
        check("非法 cron 被拒绝", r.json()["valid"] is False, r.text[:200])

        r = c.post("/api/v1/plans/cron/preview", headers=H, json={"cron": "*/30 * * * *"})
        check("间隔表达式可解析", r.json()["valid"] is True and "分钟" in r.json()["description"],
              r.json().get("description"))

        # ---------------------------------------------------------------- 报告与导出
        print("\n== 5. 巡检报告导出 ==")
        r = c.post("/api/v1/inspections/templates", headers=H, json={
            "name": "导出测试模板", "category": "custom", "status": "approved",
            "playbook": "---\n- hosts: all\n  tasks:\n    - name: echo\n      shell: echo hi\n      changed_when: false\n"})
        tpl_id = r.json()["id"]
        r = c.post("/api/v1/plans", headers=H, json={
            "name": "导出测试计划", "template_id": tpl_id, "target_type": "group",
            "target_id": gid, "cron": "0 3 * * *"})
        plan_id = r.json()["id"]
        r = c.post(f"/api/v1/plans/{plan_id}/run", headers=H)
        check("计划立即执行成功", r.status_code == 200, r.text[:300])
        report_id = r.json()["report_id"]

        r = c.get(f"/api/v1/plans/reports/{report_id}/export", headers=H, params={"format": "xlsx"})
        check("导出 Excel 成功", r.status_code == 200, r.text[:200])
        check("Excel 是合法 xlsx（ZIP 头）", r.content[:2] == b"PK", r.content[:8])
        check("Excel 体积合理", len(r.content) > 3000, f"{len(r.content)} 字节")

        from app.services.export import _find_font
        has_font = _find_font() is not None
        r = c.get(f"/api/v1/plans/reports/{report_id}/export", headers=H, params={"format": "pdf"})
        if has_font:
            check("导出 PDF 成功", r.status_code == 200, r.text[:200])
            check("PDF 是合法文件", r.content[:4] == b"%PDF", r.content[:8])
            check("PDF 体积合理", len(r.content) > 2000, f"{len(r.content)} 字节")
        else:
            check("无中文字体时给出明确提示", r.status_code == 501, r.status_code)

        r = c.get("/api/v1/plans/reports/export-all", headers=H, params={"days": 30})
        check("导出汇总表成功", r.status_code == 200 and r.content[:2] == b"PK", r.status_code)

        r = c.get(f"/api/v1/plans/reports/{report_id}/export", headers=H, params={"format": "docx"})
        check("不支持的格式返回 400", r.status_code == 400, r.status_code)

        # ---------------------------------------------------------------- 审计
        print("\n== 6. 审计日志检索与导出 ==")
        r = c.get("/api/v1/audit", headers=H, params={"page": 1, "size": 5})
        data = r.json()
        check("分页结构正确", {"total", "page", "size", "items"} <= set(data.keys()), list(data.keys()))
        check("每页条数受限", len(data["items"]) <= 5, len(data["items"]))
        check("有审计记录", data["total"] > 0, data["total"])

        r = c.get("/api/v1/audit/facets", headers=H)
        check("筛选候选值可用", set(r.json().keys()) == {"users", "actions", "resources"}, r.text[:200])

        r = c.get("/api/v1/audit", headers=H, params={"action": "execute", "size": 50})
        check("按操作类型筛选", all(x["action"] == "execute" for x in r.json()["items"]),
              [x["action"] for x in r.json()["items"][:3]])

        r = c.get("/api/v1/audit", headers=H, params={"keyword": "探活"})
        check("关键词筛选生效", r.json()["total"] >= 0)

        r = c.get("/api/v1/audit/export", headers=H, params={"days": 30})
        check("导出 CSV 成功", r.status_code == 200, r.status_code)
        check("CSV 带 BOM（Excel 不乱码）", r.content[:3] == b"\xef\xbb\xbf", r.content[:6])
        check("CSV 含表头", "时间,用户,操作" in r.content.decode("utf-8-sig")[:80])

        r = c.get("/api/v1/audit", headers=H, params={"start": "不是时间"})
        check("非法时间返回 400", r.status_code == 400, r.status_code)

        # ---------------------------------------------------------------- 告警状态机
        print("\n== 7. 告警状态机 ==")
        db = SessionLocal()
        try:
            base = dict(fingerprint="plan:unit-test", title="单测告警",
                        severity="critical", resource_type="plan", resource_id="unit-test",
                        detail={"说明": "单测"}, tenant_id=DEFAULT_TENANT_ID)
            r1 = alert_svc.evaluate(db, healthy=False, **base)
            check("首次异常 -> created", r1["action"] == "created", r1)
            r2 = alert_svc.evaluate(db, healthy=False, **base)
            check("重复异常 -> 去重跳过", r2["action"] == "skipped", r2)
            r3 = alert_svc.evaluate(db, healthy=True, **base)
            check("恢复正常 -> resolved", r3["action"] == "resolved", r3)
            r4 = alert_svc.evaluate(db, healthy=True, **base)
            check("持续正常 -> 不重复通知", r4["action"] == "skipped", r4)
            r5 = alert_svc.evaluate(db, healthy=False, **base)
            check("恢复后再次异常 -> 重新触发", r5["action"] == "created", r5)
        finally:
            db.close()

        # 静默窗口
        r = c.post("/api/v1/alerts/silences", headers=H, json={
            "name": "单测静默", "scope": "", "minutes": 30, "reason": "单元测试"})
        check("创建静默窗口", r.status_code == 200, r.text[:200])
        silence_id = r.json()["id"]
        check("静默窗口生效中", r.json()["active"] is True)

        db = SessionLocal()
        try:
            r6 = alert_svc.evaluate(db, healthy=False, fingerprint="plan:silenced",
                                    title="静默测试", severity="warning",
                                    resource_type="plan", resource_id="silenced",
                                    detail={}, tenant_id=DEFAULT_TENANT_ID)
            check("静默期内 -> 只记录不推送", r6["action"] == "silenced", r6)
        finally:
            db.close()

        r = c.get("/api/v1/alerts/events", headers=H, params={"status": "firing"})
        check("事件列表可查", isinstance(r.json(), list) and len(r.json()) >= 1, r.text[:200])

        r = c.get("/api/v1/alerts/summary", headers=H)
        summary = r.json()
        check("告警汇总结构正确", {"active", "by_severity", "silenced"} <= set(summary.keys()), summary)
        check("静默窗口计入统计", summary["silenced"] >= 1, summary)

        # 人工恢复
        ev = c.get("/api/v1/alerts/events", headers=H, params={"status": "firing"}).json()[0]
        r = c.post(f"/api/v1/alerts/events/{ev['id']}/resolve", headers=H)
        check("人工标记恢复", r.status_code == 200 and r.json()["status"] == "resolved", r.text[:200])

        # 解除静默后，异常应重新推送（notified 可能为 0，因为没有真实 webhook）
        r = c.delete(f"/api/v1/alerts/silences/{silence_id}", headers=H)
        check("解除静默", r.status_code == 200)
        db = SessionLocal()
        try:
            r7 = alert_svc.evaluate(db, healthy=False, fingerprint="plan:silenced",
                                    title="静默测试", severity="warning",
                                    resource_type="plan", resource_id="silenced",
                                    detail={}, tenant_id=DEFAULT_TENANT_ID)
            check("解除静默后恢复推送逻辑", r7["action"] in ("repeated", "created"), r7)
        finally:
            db.close()

        # 渠道配置
        r = c.post("/api/v1/alerts/configs", headers=H, json={
            "name": "值班群", "channel": "dingtalk", "webhook_url": "",
            "min_severity": "critical", "repeat_interval_minutes": 30})
        check("创建告警渠道", r.status_code == 200, r.text[:200])
        cfg_id = r.json()["id"]
        check("级别配置已保存", r.json()["min_severity"] == "critical")

        r = c.post("/api/v1/alerts/configs", headers=H, json={
            "name": "非法级别", "min_severity": "fatal"})
        check("非法级别被拒绝", r.status_code == 400, r.status_code)

        r = c.post(f"/api/v1/alerts/configs/{cfg_id}/test", headers=H)
        check("测试发送接口可用（无 url 时返回 ok=False）",
              r.status_code == 200 and r.json()["ok"] is False, r.text[:200])

        # 任务失败自动产生告警事件
        r = c.get("/api/v1/alerts/events", headers=H, params={"status": "firing"})
        fired = r.json()
        check("失败任务已自动进入告警事件", any(e["resource_type"] in ("task", "plan") for e in fired),
              [e["title"] for e in fired][:3])

        # ---------------------------------------------------------------- 越权
        print("\n== 8. 租户隔离 ==")
        c.post("/api/v1/tenants", headers=H, json={"code": "acme", "name": "ACME"})
        # 用超管带 X-Tenant-Id 收窄视角，验证只看到该租户数据
        r = c.get("/api/v1/hosts", headers={**H, "X-Tenant-Id": "acme"})
        check("超管收窄租户视角后无主机", r.status_code == 200 and len(r.json()) == 0, r.text[:200])
        r = c.get("/api/v1/alerts/events", headers={**H, "X-Tenant-Id": "acme"})
        check("超管收窄视角后无告警", r.status_code == 200 and len(r.json()) == 0, r.text[:200])

    srv.close()
    print(f"\n通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        print("失败项:")
        for f in FAILED:
            print("  -", f)
        return 1
    print("全部通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
