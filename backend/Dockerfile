# syntax=docker/dockerfile:1
# AutoOps 后端镜像
# 说明：容器内使用 Python 3.12 —— bcrypt==4.0.1（passlib 1.7.4 依赖）没有 cp313 预编译包，
#      用 3.13 会在构建时触发 Rust 源码编译，慢且容易失败。3.12 有现成 wheel。
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

# PIP_INDEX_URL：国内网络可改为 https://pypi.tuna.tsinghua.edu.cn/simple
# INSTALL_ANSIBLE=true：需要真实执行（EXECUTOR_BACKEND=ansible）时开启
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG INSTALL_ANSIBLE=false

RUN apt-get update \
 && apt-get install -y --no-install-recommends tzdata openssh-client iputils-ping \
    fonts-droid-fallback \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt ./
# 显式清空代理变量：宿主机若设置了 http_proxy，Docker 会自动透传，导致 pip 卡死
RUN http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= ALL_PROXY= \
    pip install --index-url "${PIP_INDEX_URL}" -r requirements.txt

RUN if [ "${INSTALL_ANSIBLE}" = "true" ]; then \
        http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= \
        pip install --index-url "${PIP_INDEX_URL}" ansible-runner; \
    fi

COPY app ./app

RUN mkdir -p /app/data
VOLUME ["/app/data"]

EXPOSE 8000

# 注意：--workers 必须为 1。巡检计划调度器（APScheduler）是进程内的，
# 多 worker 会导致同一计划被重复触发。
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
