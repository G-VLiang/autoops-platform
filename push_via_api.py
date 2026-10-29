#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
通过 GitHub REST API 提交本地 git 已跟踪文件到远端仓库。
用途：当 git 协议通道（github.com:443）不通、但 api.github.com 可用时，
     用 Git Data API（blob -> tree -> commit -> ref）完成等价于 git push 的提交。

用法：
    python push_via_api.py <TOKEN> [--owner G-VLiang] [--repo autoops-platform]

Token 需要 repo 权限（classic）或 Contents: Read and write（fine-grained）。
"""
import base64
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

API = "https://api.github.com"
# 关键：禁用代理。本机代理对 github 返回 502，直连 api 才稳定
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(method, path, token, payload=None, retries=5):
    url = API + path
    data = json.dumps(payload).encode() if payload is not None else None
    last_err = None
    for attempt in range(1, retries + 1):
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Authorization", "Bearer " + token)
        req.add_header("Accept", "application/vnd.github+json")
        req.add_header("X-GitHub-Api-Version", "2022-11-28")
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with OPENER.open(req, timeout=60) as r:
                return json.loads(r.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            try:
                msg = json.loads(body).get("message", body) or f"HTTP {e.code}"
            except Exception:
                msg = body or f"HTTP {e.code}"
            # 5xx / 429 等瞬时错误：重试；4xx 业务错误：直接抛
            if e.code >= 500 or e.code == 429:
                last_err = RuntimeError(f"{method} {path} -> HTTP {e.code}: {msg}")
                if attempt < retries:
                    wait = min(2 ** attempt, 8)
                    print(f"      ⚠️ {e.code} 重试 {attempt}/{retries-1}（{wait}s）")
                    time.sleep(wait)
                    continue
                raise last_err from None
            raise RuntimeError(f"{method} {path} -> HTTP {e.code}: {msg}") from None
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            last_err = RuntimeError(f"{method} {path} -> 网络错误: {e}")
            if attempt < retries:
                wait = min(2 ** attempt, 8)
                print(f"      ⚠️ 网络异常重试 {attempt}/{retries-1}（{wait}s）")
                time.sleep(wait)
                continue
            raise last_err from None
    raise last_err


def git(*args):
    r = subprocess.run(["git"] + list(args), capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} 失败: {r.stderr.strip()}")
    return r.stdout


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    token = sys.argv[1]
    owner, repo, branch = "G-VLiang", "autoops-platform", "main"
    for i, a in enumerate(sys.argv[2:]):
        if a == "--owner":
            owner = sys.argv[i + 3]
        elif a == "--repo":
            repo = sys.argv[i + 3]

    # 1. 校验 token
    me = api("GET", "/user", token)
    print(f"[1/5] ✅ Token 有效，用户: {me.get('login')}")

    # 1.5 空仓库无法创建 blob（API 返回 409），需先用 Contents API 播种一次提交
    parent_sha, base_tree = None, None
    try:
        ref = api("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}", token)
        parent_sha = ref["object"]["sha"]
        print(f"[1.5] 仓库已有提交，以 {parent_sha[:10]} 为父提交")
    except RuntimeError as e:
        if "409" in str(e) or "404" in str(e) or "empty" in str(e).lower():
            print("[1.5] 检测到空仓库，正在播种初始提交...")
            api("PUT", f"/repos/{owner}/{repo}/contents/README.md", token,
                {"message": "init", "content": base64.b64encode(b"# init\n").decode()})
            ref = api("GET", f"/repos/{owner}/{repo}/git/ref/heads/{branch}", token)
            parent_sha = ref["object"]["sha"]
            print(f"      ✅ 已播种，父提交 {parent_sha[:10]}")
        else:
            raise
    if parent_sha:
        base_tree = api("GET", f"/repos/{owner}/{repo}/git/commits/{parent_sha}",
                        token)["tree"]["sha"]

    # 2. 收集文件（含 git 模式）
    out = git("ls-files", "-s")
    entries = []
    for line in out.splitlines():
        if not line.strip():
            continue
        meta, path = line.split("\t", 1)
        mode = meta.split()[0]
        entries.append((mode, path))
    print(f"[2/5] 待上传 {len(entries)} 个文件")

    # 3. 创建 blob
    tree = []
    for idx, (mode, path) in enumerate(entries, 1):
        with open(path, "rb") as f:
            content = base64.b64encode(f.read()).decode()
        blob = api("POST", f"/repos/{owner}/{repo}/git/blobs", token,
                   {"content": content, "encoding": "base64"})
        tree.append({"path": path.replace("\\", "/"), "mode": mode,
                     "type": "blob", "sha": blob["sha"]})
        if idx % 10 == 0 or idx == len(entries):
            print(f"      blob {idx}/{len(entries)}")

    # 4. 创建 tree + commit
    #    默认「镜像」：不用 base_tree，远端文件树 == 本地 git ls-files 的结果，
    #    这样本地删掉的文件在远端也会被删除。
    #    若想保留远端额外文件（多人协作场景），设置 PUSH_MERGE_TREE=1。
    tree_payload = {"tree": tree}
    if base_tree and os.environ.get("PUSH_MERGE_TREE") == "1":
        tree_payload["base_tree"] = base_tree
        print("[3.5] 合并模式：保留远端未在本地出现的文件")
    t = api("POST", f"/repos/{owner}/{repo}/git/trees", token, tree_payload)
    # 提交信息：优先用环境变量 PUSH_MESSAGE（批量推送多条本地提交时更准确），
    # 否则取本地最后一条提交信息
    msg = os.environ.get("PUSH_MESSAGE", "").strip() or git("log", "-1", "--pretty=%B").strip()
    c = api("POST", f"/repos/{owner}/{repo}/git/commits", token,
            {"message": msg or "init", "tree": t["sha"],
             "parents": [parent_sha] if parent_sha else []})
    print(f"[4/5] ✅ tree={t['sha'][:10]} commit={c['sha'][:10]}")

    # 5. 创建或更新分支引用
    try:
        api("POST", f"/repos/{owner}/{repo}/git/refs", token,
            {"ref": f"refs/heads/{branch}", "sha": c["sha"]})
        print(f"[5/5] ✅ 已创建分支 {branch}")
    except RuntimeError as e:
        if "already exists" in str(e) or "422" in str(e):
            api("PATCH", f"/repos/{owner}/{repo}/git/refs/heads/{branch}", token,
                {"sha": c["sha"], "force": True})
            print(f"[5/5] ✅ 已更新分支 {branch}")
        else:
            raise

    api("PATCH", f"/repos/{owner}/{repo}", token, {"default_branch": branch})

    print(f"\n🎉 完成: https://github.com/{owner}/{repo}")
    print(f"   提交: {c['sha']}")
    print(f"   文件: {len(entries)} 个")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"\n❌ 失败: {e}")
        sys.exit(1)
