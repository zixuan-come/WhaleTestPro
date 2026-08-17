# WhaleTestPro 云服务器部署

本文适用于 Ubuntu 22.04 LTS 云服务器,使用 Docker Compose 部署完整平台。代码目录约定为 `/srv/whaletestpro`,部署账号使用普通用户并通过 `sudo` 操作 Docker。

## 部署拓扑

Docker Compose 会启动以下服务:

| 服务 | 宿主端口 | 用途 |
|------|----------|------|
| frontend | `8080` | 平台入口,Nginx 将 `/api` 反向代理到后端 |
| app | `8001` | FastAPI 与 Swagger |
| RabbitMQ | `5672` / `15672` | Celery broker / 管理台 |
| Grafana | `3000` | 监控看板 |
| Prometheus | `9090` | 指标查询 |
| Locust | `8089` | 压测控制台 |

MySQL 和 Redis 只加入 Compose 内部网络,不映射公网端口。生产演示时建议安全组只开放 SSH 和前端 `8080`;其余管理端口按需限制来源 IP。

## 服务器准备

确认服务器已安装 Git、Docker Engine 和 Docker Compose 插件:

```bash
git --version
docker --version
sudo docker compose version
sudo systemctl is-active docker
```

创建部署目录并交给部署用户:

```bash
sudo mkdir -p /srv/whaletestpro
sudo chown -R "$USER":"$USER" /srv/whaletestpro
```

## 配置只读 GitHub SSH

服务器只负责拉取和部署,建议为仓库配置只读 Deploy Key,不要授予写权限。网络无法稳定访问 GitHub 22 端口时可通过 `ssh.github.com:443` 连接:

```sshconfig
Host github-whaletestpro
    HostName ssh.github.com
    Port 443
    User git
    IdentityFile ~/.ssh/whaletestpro_deploy
    IdentitiesOnly yes
```

验证并克隆:

```bash
ssh -T github-whaletestpro
git clone github-whaletestpro:zixuan-come/WhaleTestPro.git /srv/whaletestpro
cd /srv/whaletestpro
git status -sb
```

只读密钥可以降低服务器凭据泄漏后仓库被篡改的风险。开发和提交仍在本地完成,服务器只执行 `fetch` 和快进合并。

## 准备环境变量

先生成随机值:

```bash
openssl rand -hex 24
openssl rand -hex 32
```

在项目根创建 `.env`,只保存以下配置:

```dotenv
MYSQL_ROOT_PASSWORD=<第一段随机值>
SECRET_KEY=<第二段随机值>
FEISHU_WEBHOOK=
```

限制文件权限并检查变量名,不要输出变量值:

```bash
chmod 600 .env
grep -E '^[A-Z_][A-Z0-9_]*=' .env | cut -d= -f1
```

Compose 会在容器内组装主库、影子库、Redis 和 RabbitMQ 连接地址,无需在 `.env` 重复配置 `DATABASE_URL`。

## 首次部署

```bash
cd /srv/whaletestpro
sudo docker compose config --quiet
sudo docker compose pull
sudo docker compose up -d --build --remove-orphans
```

首次创建 MySQL 数据卷时,`docker/mysql/init/01-create-shadow-db.sql` 会自动创建 `whale_test_pro_shadow`;FastAPI 启动后在主库和影子库自动建表。

检查容器、健康接口和前端代理:

```bash
sudo docker compose ps -a
curl -fsS http://127.0.0.1:8001/health
curl -fsS http://127.0.0.1:8080/api/health
sudo docker stats --no-stream
```

浏览器访问 `http://<服务器公网地址>:8080`。首次使用时注册账号,登录后创建项目和环境。

## 日常更新

仓库提供 `scripts/deploy.sh`,执行前要求:

- 当前分支与 `DEPLOY_BRANCH` 一致,默认 `main`。
- 服务器工作区没有本地修改或未跟踪文件。
- `.env` 已存在。
- 远端历史可以快进合并,服务器不存在未推送提交。

执行:

```bash
cd /srv/whaletestpro
bash scripts/deploy.sh
```

脚本会依次执行 GitHub 同步、Compose 配置校验、镜像重建、健康检查和异常容器检查。`flock` 会阻止两个部署任务同时运行。

可覆盖的部署参数:

```bash
DEPLOY_BRANCH=main \
HEALTH_URL=http://127.0.0.1:8080/api/health \
HEALTH_MAX_ATTEMPTS=30 \
HEALTH_WAIT_SECONDS=2 \
bash scripts/deploy.sh
```

## 常用运维命令

```bash
sudo docker compose ps -a
sudo docker compose logs --tail=100 app frontend
sudo docker compose logs -f app
sudo docker compose restart app frontend
sudo docker compose stop
sudo docker compose start
```

`docker compose down` 会删除容器和网络但保留命名卷;不要在未备份的情况下使用 `docker compose down -v`,该命令会删除 MySQL 数据卷。

## 故障排查

### GitHub 拉取超时

先验证 SSH 443 和远端:

```bash
ssh -T github-whaletestpro
git ls-remote origin HEAD
```

### 后端端口拒绝连接

```bash
sudo docker compose ps -a
sudo docker compose logs --tail=150 app mysql rabbitmq
curl -i http://127.0.0.1:8001/health
```

重点检查 MySQL、RabbitMQ 是否 healthy,以及 `.env` 是否包含 `MYSQL_ROOT_PASSWORD` 和 `SECRET_KEY`。

### 旧数据卷缺少影子库

初始化脚本只对空数据卷执行。已有 MySQL 数据卷可幂等补建:

```bash
sudo docker compose exec mysql sh -c \
  'mysql -uroot -p"$MYSQL_ROOT_PASSWORD" -e "CREATE DATABASE IF NOT EXISTS whale_test_pro_shadow CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;"'
```

### 前端正常但 `/api` 请求失败

先分别验证后端和 Nginx 代理:

```bash
curl -i http://127.0.0.1:8001/health
curl -i http://127.0.0.1:8080/api/health
sudo docker compose logs --tail=100 app frontend
```

后端直连正常而 `/api/health` 失败时,优先检查 frontend 容器和 Nginx 反向代理;两者都失败时先处理 app 容器。
