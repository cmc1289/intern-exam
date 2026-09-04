#!/usr/bin/env bash
# 测试国内 Docker Hub 镜像加速器可用性，并把可用的写入 daemon.json
set -e

MIRRORS=(
  "https://docker.m.daocloud.io"
  "https://docker.1panel.live"
  "https://docker.nju.edu.cn"
  "https://mirror.ccs.tencentyun.com"
  "https://docker.mirrors.ustc.edu.cn"
)

WORKING=()
for m in "${MIRRORS[@]}"; do
  code=$(curl -sS -m 8 -o /dev/null -w "%{http_code}" "$m/v2/" 2>/dev/null || echo "000")
  echo "TEST $m -> $code"
  if [ "$code" = "200" ] || [ "$code" = "401" ]; then
    WORKING+=("\"$m\"")
  fi
done

echo "=== WORKING: ${WORKING[*]} ==="

if [ ${#WORKING[@]} -eq 0 ]; then
  echo "NO_WORKING_MIRROR"
  exit 1
fi

# 用逗号拼接
LIST=$(IFS=,; echo "${WORKING[*]}")

sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json > /dev/null <<EOF
{
  "registry-mirrors": [${LIST}]
}
EOF

sudo systemctl restart docker
sleep 2
echo "=== DAEMON_JSON ==="
cat /etc/docker/daemon.json
echo "=== VERIFY ==="
sudo docker info 2>/dev/null | grep -A10 "Registry Mirrors"
