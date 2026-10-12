# 平台沙箱镜像：短生命周期、非root、带bash+Powershell Core
FROM mcr.microsoft.com/powershell:7.4-ubuntu-22.04
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl python3 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 --shell /bin/bash sandbox \
    && mkdir -p /workspace \
    && chown -R sandbox:sandbox /workspace

USER sandbox 
WORKDIR /workspace 
# 容器保持存活，命令一律走docker exec（有状态会话）
CMD ["sleep","infinity"]