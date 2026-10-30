"""预置作业模板库。

定位：开箱即用的只读巡检/采集剧本，用户不必自己写 playbook。
全部使用 `changed_when: false` + `failed_when: false`，保证只读、不误报变更、不因单项失败中断。
"""
from __future__ import annotations

from typing import Dict, List


def _pb(name: str, tasks: str) -> str:
    return f"""---
- name: {name}
  hosts: all
  gather_facts: false
  tasks:
{tasks}
"""


def _shell(title: str, cmd: str, reg: str) -> str:
    return f"""    - name: {title}
      ansible.builtin.shell: |
        {cmd}
      register: {reg}
      changed_when: false
      failed_when: false
"""


def _debug(msg: str) -> str:
    return f"""    - name: 输出结果
      ansible.builtin.debug:
        msg: "{msg}"
"""


LIBRARY: List[Dict] = [
    {
        "key": "disk-usage", "name": "磁盘使用率巡检", "category": "磁盘",
        "description": "列出各分区使用率，超过 80% 的会置顶显示", "tags": ["disk", "capacity"],
        "content": _pb("磁盘使用率巡检", _shell(
            "查看分区使用率", "df -hPT | awk 'NR==1 || int($6)>=80'", "df_out") + _debug("{{ df_out.stdout_lines }}")),
    },
    {
        "key": "inode-usage", "name": "Inode 使用率巡检", "category": "磁盘",
        "description": "inode 耗尽会导致无法创建新文件，比磁盘满更隐蔽", "tags": ["disk", "inode"],
        "content": _pb("Inode 使用率巡检", _shell(
            "查看 inode 使用率", "df -iPT | awk 'NR==1 || int($6)>=80'", "inode_out") + _debug("{{ inode_out.stdout_lines }}")),
    },
    {
        "key": "memory-usage", "name": "内存与 Swap 巡检", "category": "内存",
        "description": "内存占用、Swap 使用量与可用内存", "tags": ["memory"],
        "content": _pb("内存与 Swap 巡检", _shell(
            "查看内存", "free -m && echo '---' && cat /proc/meminfo | grep -E 'MemAvailable|SwapFree'", "mem_out")
            + _debug("{{ mem_out.stdout_lines }}")),
    },
    {
        "key": "cpu-load", "name": "CPU 负载巡检", "category": "CPU",
        "description": "1/5/15 分钟负载与核数对比", "tags": ["cpu", "load"],
        "content": _pb("CPU 负载巡检", _shell(
            "查看负载与核数", "uptime && echo '---' && nproc", "load_out") + _debug("{{ load_out.stdout_lines }}")),
    },
    {
        "key": "top-process", "name": "资源占用 Top 进程", "category": "CPU",
        "description": "按 CPU 与内存分别列出前 10 个进程", "tags": ["process"],
        "content": _pb("资源占用 Top 进程", _shell(
            "CPU Top10", "ps -eo pid,ppid,user,%cpu,%mem,etime,cmd --sort=-%cpu | head -11", "cpu_out")
            + _shell("内存 Top10", "ps -eo pid,ppid,user,%cpu,%mem,etime,cmd --sort=-%mem | head -11", "mem_out")
            + _debug("{{ cpu_out.stdout_lines }} + {{ mem_out.stdout_lines }}")),
    },
    {
        "key": "zombie-process", "name": "僵尸进程检查", "category": "进程",
        "description": "统计状态为 Z 的进程，过多说明父进程未回收", "tags": ["process"],
        "content": _pb("僵尸进程检查", _shell(
            "统计僵尸进程", "ps -eo stat,pid,ppid,cmd | awk '$1 ~ /Z/ {print}' | head -30", "z_out")
            + _debug("{{ z_out.stdout_lines }}")),
    },
    {
        "key": "service-status", "name": "关键服务状态巡检", "category": "服务",
        "description": "检查 sshd/crond/nginx/docker 等常见服务是否在运行", "tags": ["service"],
        "content": _pb("关键服务状态巡检", _shell(
            "服务状态", "for s in sshd ssh crond cron nginx docker firewalld; do systemctl is-active $s >/dev/null 2>&1 && echo \"[OK] $s active\" || echo \"[--] $s inactive/absent\"; done", "svc_out")
            + _debug("{{ svc_out.stdout_lines }}")),
    },
    {
        "key": "port-listen", "name": "监听端口巡检", "category": "网络",
        "description": "列出所有 LISTEN 端口，便于发现意外暴露的服务", "tags": ["network", "security"],
        "content": _pb("监听端口巡检", _shell(
            "监听端口", "ss -lntup 2>/dev/null || netstat -lntup", "port_out") + _debug("{{ port_out.stdout_lines }}")),
    },
    {
        "key": "network-config", "name": "网络配置采集", "category": "网络",
        "description": "IP、路由、DNS 配置", "tags": ["network"],
        "content": _pb("网络配置采集", _shell(
            "网络信息", "ip -4 addr show 2>/dev/null | grep -E 'inet |^[0-9]' ; echo '--- route ---'; ip route; echo '--- dns ---'; cat /etc/resolv.conf", "net_out")
            + _debug("{{ net_out.stdout_lines }}")),
    },
    {
        "key": "log-errors", "name": "系统错误日志巡检", "category": "日志",
        "description": "最近 200 条中 error/fail 关键字（journalctl 或 messages）", "tags": ["log"],
        "content": _pb("系统错误日志巡检", _shell(
            "错误日志", "journalctl -p err -n 50 --no-pager 2>/dev/null || grep -iE 'error|fail' /var/log/messages /var/log/syslog 2>/dev/null | tail -50", "log_out")
            + _debug("{{ log_out.stdout_lines }}")),
    },
    {
        "key": "log-size", "name": "日志文件体积巡检", "category": "日志",
        "description": "找出 /var/log 下大于 100MB 的文件", "tags": ["log", "disk"],
        "content": _pb("日志文件体积巡检", _shell(
            "大日志文件", "find /var/log -type f -size +100M -exec ls -lh {} \\; 2>/dev/null | awk '{print $5, $9}'", "lsz_out")
            + _debug("{{ lsz_out.stdout_lines }}")),
    },
    {
        "key": "cert-expiry", "name": "SSL 证书到期检查", "category": "安全",
        "description": "扫描 Nginx 证书文件，30 天内到期的会列出", "tags": ["security", "cert"],
        "content": _pb("SSL 证书到期检查", _shell(
            "证书剩余天数", "for f in $(find /etc/nginx /etc/ssl -name '*.pem' -o -name '*.crt' 2>/dev/null | head -20); do end=$(openssl x509 -in \"$f\" -noout -enddate 2>/dev/null | cut -d= -f2); [ -n \"$end\" ] && echo \"$f => $end\"; done", "cert_out")
            + _debug("{{ cert_out.stdout_lines }}")),
    },
    {
        "key": "ntp-time", "name": "时间同步巡检", "category": "系统",
        "description": "系统时间、时区与 NTP 同步状态", "tags": ["time"],
        "content": _pb("时间同步巡检", _shell(
            "时间状态", "timedatectl 2>/dev/null || date '+%Y-%m-%d %H:%M:%S %Z'", "time_out")
            + _debug("{{ time_out.stdout_lines }}")),
    },
    {
        "key": "docker-status", "name": "Docker 容器巡检", "category": "服务",
        "description": "容器列表、异常退出容器、磁盘占用", "tags": ["docker"],
        "content": _pb("Docker 容器巡检", _shell(
            "容器状态", "docker ps -a --format 'table {{.Names}}\\t{{.Status}}\\t{{.Image}}' 2>/dev/null | head -40; echo '--- 非运行容器 ---'; docker ps -a --filter status=exited --format '{{.Names}} {{.Status}}' 2>/dev/null", "dk_out")
            + _debug("{{ dk_out.stdout_lines }}")),
    },
    {
        "key": "nginx-status", "name": "Nginx 状态巡检", "category": "服务",
        "description": "配置语法检查、进程数与连接数", "tags": ["nginx"],
        "content": _pb("Nginx 状态巡检", _shell(
            "Nginx 状态", "nginx -t 2>&1; echo '---'; ps -ef | grep -c '[n]ginx'; echo '--- 连接 ---'; ss -s 2>/dev/null | head -5", "ng_out")
            + _debug("{{ ng_out.stdout_lines }}")),
    },
    {
        "key": "mysql-status", "name": "MySQL 状态巡检", "category": "数据库",
        "description": "连接数、慢查询、主从状态（需本机可免密登录或已配置凭据）", "tags": ["mysql", "db"],
        "content": _pb("MySQL 状态巡检", _shell(
            "MySQL 状态", "mysql -e \"show global status like 'Threads_connected'; show global status like 'Slow_queries'; show slave status\\G\" 2>&1 | head -40", "my_out")
            + _debug("{{ my_out.stdout_lines }}")),
    },
    {
        "key": "redis-status", "name": "Redis 状态巡检", "category": "数据库",
        "description": "内存占用、命中率、连接数、持久化状态", "tags": ["redis", "db"],
        "content": _pb("Redis 状态巡检", _shell(
            "Redis Info", "redis-cli info 2>/dev/null | grep -E 'used_memory_human|connected_clients|keyspace_hits|keyspace_misses|rdb_last_bgsave_status|aof_last_write_status'", "rd_out")
            + _debug("{{ rd_out.stdout_lines }}")),
    },
    {
        "key": "security-baseline", "name": "安全基线巡检", "category": "安全",
        "description": "SSH 配置（root 登录/密码认证）、空口令账号、SUID 文件", "tags": ["security", "baseline"],
        "content": _pb("安全基线巡检", _shell(
            "SSH 关键配置", "grep -iE '^(PermitRootLogin|PasswordAuthentication|PermitEmptyPasswords)' /etc/ssh/sshd_config 2>/dev/null", "ssh_out")
            + _shell("空口令账号", "awk -F: '($2==\"\"){print $1}' /etc/shadow 2>/dev/null", "empty_out")
            + _shell("SUID 文件", "find / -xdev -perm -4000 -type f 2>/dev/null | head -20", "suid_out")
            + _debug("{{ ssh_out.stdout_lines }} / 空口令:{{ empty_out.stdout_lines }} / SUID:{{ suid_out.stdout_lines }}")),
    },
    {
        "key": "account-audit", "name": "账号审计", "category": "安全",
        "description": "UID=0 账号、可登录 shell 的账号、最近登录记录", "tags": ["security", "account"],
        "content": _pb("账号审计", _shell(
            "UID=0 与可登录账号", "awk -F: '($3==0){print \"root权限: \"$1} ($7!~/nologin|false/){print \"可登录: \"$1}' /etc/passwd", "acc_out")
            + _shell("最近登录", "last -n 10 2>/dev/null", "last_out")
            + _debug("{{ acc_out.stdout_lines }} / {{ last_out.stdout_lines }}")),
    },
    {
        "key": "crontab-audit", "name": "定时任务审计", "category": "系统",
        "description": "系统与应用用户的 crontab，排查来源不明任务", "tags": ["cron"],
        "content": _pb("定时任务审计", _shell(
            "全部 crontab", "for u in $(cut -f1 -d: /etc/passwd); do c=$(crontab -l -u $u 2>/dev/null | grep -v '^#'); [ -n \"$c\" ] && echo \"=== $u ===\" && echo \"$c\"; done; echo '--- system ---'; ls -1 /etc/cron.d /etc/cron.daily 2>/dev/null", "cr_out")
            + _debug("{{ cr_out.stdout_lines }}")),
    },
    {
        "key": "disk-io", "name": "磁盘 IO 巡检", "category": "磁盘",
        "description": "各磁盘 IO 利用率与等待时间", "tags": ["disk", "io"],
        "content": _pb("磁盘 IO 巡检", _shell(
            "IO 状态", "iostat -dx 1 2 2>/dev/null | tail -20 || cat /proc/diskstats | head -10", "io_out")
            + _debug("{{ io_out.stdout_lines }}")),
    },
    {
        "key": "sysinfo", "name": "系统信息采集", "category": "系统",
        "description": "OS 版本、内核、CPU 型号、内存总量、运行时长", "tags": ["system"],
        "content": _pb("系统信息采集", _shell(
            "系统信息", "cat /etc/os-release | head -4; uname -r; lscpu 2>/dev/null | grep -E 'Model name|^CPU\\(s\\)' ; free -h | head -2; uptime", "sys_out")
            + _debug("{{ sys_out.stdout_lines }}")),
    },
]

LIBRARY_MAP: Dict[str, Dict] = {item["key"]: item for item in LIBRARY}


def list_items(category: str | None = None, keyword: str | None = None) -> List[Dict]:
    items = LIBRARY
    if category:
        items = [i for i in items if i["category"] == category]
    if keyword:
        kw = keyword.lower()
        items = [i for i in items if kw in i["name"].lower() or kw in i["description"].lower()
                 or any(kw in t.lower() for t in i.get("tags", []))]
    return items


def get_item(key: str) -> Dict | None:
    return LIBRARY_MAP.get(key)
