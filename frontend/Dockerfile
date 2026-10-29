# syntax=docker/dockerfile:1
# AutoOps 前端镜像：多阶段构建，产物用 nginx 托管（自带 /api 反向代理）

FROM node:22-alpine AS build
WORKDIR /app

# 国内网络可加：--build-arg NPM_REGISTRY=https://registry.npmmirror.com
ARG NPM_REGISTRY=https://registry.npmjs.org

COPY package.json package-lock.json ./
RUN http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= \
    npm ci --registry="${NPM_REGISTRY}" --no-audit --no-fund

COPY . .
RUN http_proxy= https_proxy= HTTP_PROXY= HTTPS_PROXY= npm run build

FROM nginx:1.27-alpine

ENV TZ=Asia/Shanghai
RUN rm -f /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/autoops.conf
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD wget -q --spider http://127.0.0.1/ || exit 1
