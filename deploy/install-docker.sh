#!/usr/bin/env bash
set -e

# 使用清华镜像源安装 Docker（国内直连 Docker 官方源会超时/被重置）

# 清理上一次可能残留的仓库/密钥，避免 gpg 覆盖时交互询问
sudo rm -f /etc/apt/keyrings/docker.gpg /etc/apt/sources.list.d/docker.list

sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg

sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu/gpg | sudo gpg --batch --yes --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg

echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://mirrors.tuna.tsinghua.edu.cn/docker-ce/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

sudo systemctl enable --now docker

echo "=== DOCKER_INSTALLED ==="
docker --version
docker compose version
