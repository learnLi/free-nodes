# 国内可达性探测镜像
#
# 容器只做探测。仓库通过 -v 挂载到 /app，所以 probe.py 随仓库更新即可生效，
# 不需要重建镜像；/entrypoint.sh 放在镜像里，避免被挂载覆盖。
#
# 构建：docker build -t free-nodes-probe -f docker/Dockerfile .
# 运行：见 docker/run.sh

FROM python:3.12-slim

# aioquic 依赖 cryptography，slim 版（Debian）有现成的 manylinux wheel，
# 不用编译——这是选 slim 而不是 alpine 的原因（alpine 的 musl wheel
# 覆盖不如 Debian 全，cryptography 有时需要本地编译）
RUN apt-get update && apt-get install -y -q --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir \
        PyYAML \
        requests \
        requests-file \
        typing_extensions \
        aioquic

# 工作目录放在 /out（可写）。probe.py 会把摘要写在当前工作目录，
# 而 /app 是仓库的只读挂载，写不进去。
WORKDIR /out
# 兜底：正常运行时 /app 会被仓库挂载覆盖，这里只是防止裸跑容器时找不到文件
COPY probe.py /app/probe.py
COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV LIST=/in/list.meta.us.yml \
    PROBE_TIMEOUT=5 \
    WORKERS=64 \
    OUT_DIR=/out \
    TZ=Asia/Shanghai

ENTRYPOINT ["/entrypoint.sh"]
