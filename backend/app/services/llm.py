"""大模型服务：自然语言 → 巡检 Playbook。

配置了 LLM_BASE_URL/KEY/MODEL 时走真实 OpenAI 兼容接口；否则走内置 Mock，
返回一份结构合理的巡检 Playbook，保证流程可跑通。
"""
import re
import json
from typing import Optional

import httpx

from app.core.config import settings

# 常见巡检对象 -> 生成巡检 playbook 的模板片段
_CATEGORY_HINTS = {
    "mysql": "检查 MySQL 服务状态、主从复制状态、慢查询数量、连接数、磁盘占用",
    "redis": "检查 Redis 服务状态、内存使用率、命中率、连接数、慢日志",
    "disk": "检查各分区磁盘使用率，超过阈值告警",
    "cpu": "检查 CPU 负载、使用率",
    "memory": "检查内存使用率",
    "network": "检查网卡状态、丢包率",
}


def _detect_category(prompt: str) -> str:
    for key in _CATEGORY_HINTS:
        if key in prompt.lower():
            return key
    return "custom"


def _mock_playbook(prompt: str, category: str) -> dict:
    cat_hint = _CATEGORY_HINTS.get(category, "检查系统基础状态")
    return {
        "name": f"巡检-{category or 'custom'}",
        "description": f"由自然语言生成：{prompt[:60]}",
        "category": category or "custom",
        "generated_by_llm": True,
        "is_mock": True,
        "playbook": f"""---
- name: {cat_hint}
  hosts: all
  gather_facts: true
  tasks:
    - name: 采集系统基础信息
      ansible.builtin.setup:

    - name: 检查服务状态（{category}）
      ansible.builtin.shell: |
        # 根据巡检对象执行对应检查
        echo "inspecting {category}"
        date
      register: inspect_result
      changed_when: false

    - name: 输出巡检结果
      ansible.builtin.debug:
        msg: "{{{{ inspect_result.stdout_lines }}}}"
""",
    }


def _real_llm(prompt: str, category: str) -> dict:
    system_prompt = (
        "你是一名资深运维专家，负责把用户的自然语言需求转换为 Ansible Playbook（YAML）。"
        "只输出合法的 YAML，不要输出多余解释或 markdown 代码块标记。"
        "巡检类任务需 gather_facts、加 changed_when: false，避免危险操作（禁止 rm/reboot/shutdown）。"
    )
    body = {
        "model": settings.LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
    }
    headers = {"Authorization": f"Bearer {settings.LLM_API_KEY}"}
    with httpx.Client(timeout=60) as client:
        resp = client.post(f"{settings.LLM_BASE_URL}/chat/completions", json=body, headers=headers)
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]

    playbook = _strip_code_fence(content)
    return {
        "name": f"巡检-{category}",
        "description": f"由大模型生成：{prompt[:60]}",
        "category": category,
        "generated_by_llm": True,
        "is_mock": False,
        "playbook": playbook,
    }


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    return text.strip()


def generate_playbook(prompt: str, category: str = "custom") -> dict:
    if not category or category == "custom":
        category = _detect_category(prompt)

    if settings.LLM_BASE_URL and settings.LLM_API_KEY:
        try:
            return _real_llm(prompt, category)
        except Exception:
            # 真实调用失败时回退 mock，保证流程可用
            return _mock_playbook(prompt, category)
    return _mock_playbook(prompt, category)
