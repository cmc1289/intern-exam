#!/usr/bin/env bash
set -e

# 腾讯云服务器优先使用腾讯云自己的镜像加速器（内网，速度最快）
sudo tee /etc/docker/daemon.json > /dev/null <<'EOF'
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.1panel.live",
    "https://docker.m.daocloud.io"
  ]
}
EOF

sudo systemctl restart docker
sleep 2
echo "=== DAEMON_JSON ==="
cat /etc/docker/daemon.json
echo "=== VERIFY ==="
sudo docker info 2>/dev/null | grep -A6 "Registry Mirrors"
