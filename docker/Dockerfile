# 国内可达性探测镜像
#
# 只做探测，不含 git：容器跑在 NAS 上，git 推送由宿主机的定时任务负责。
#
# 构建：docker build -t free-nodes-probe -f docker/Dockerfile .
# 运行：见 docker/run.sh

FROM python:3.12-slim

# aioquic 依赖 cryptography，slim 版（Debian）有现成的 manylinux wheel，
# 不用编译——这是选 slim 而不是 alpine 的原因（alpine 的 musl wheel
# 覆盖不如 Debian 全，cryptography 有时需要本地编译）
RUN pip install --no-cache-dir \
        PyYAML \
        requests \
        requests-file \
        typing_extensions \
        aioquic

WORKDIR /app
COPY probe.py /app/probe.py
COPY docker/entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

ENV LIST_URL="https://cdn.jsdelivr.net/gh/learnLi/free-nodes@output/list.meta.full.yml" \
    PROBE_TIMEOUT=5 \
    WORKERS=64 \
    OUT_DIR=/out \
    TZ=Asia/Shanghai

RUN apt-get update && apt-get install -y -q --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

ENTRYPOINT ["/app/entrypoint.sh"]
