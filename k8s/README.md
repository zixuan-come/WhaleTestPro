# WhaleTestPro on Kubernetes（架构线 E #22）

把 `docker-compose.yml` 的 9 个服务转成 Kubernetes 部署清单，作为架构线 E 的 K8s 半块产物。**定位：学习/演示**——理解 `compose → K8s` 的映射心智，不追求生产级完备（生产还需 Ingress、SealedSecrets、资源 limits、HPA、监控 provisioning ConfigMap 化等）。

## compose → K8s 映射心智

| docker-compose 概念 | Kubernetes 对应 | 本项目实例 |
|---|---|---|
| 有状态服务 + named volume | StatefulSet + volumeClaimTemplates + headless Service | `mysql`（mysql-data → PVC 2Gi） |
| 无状态服务 | Deployment + Service | `app` `worker` `redis` `rabbitmq` `frontend` `prometheus` `grafana` `locust-*` |
| `depends_on`（启动依赖） | 无原生等价 → initContainer 探测端口 / 应用层重试 | `app` 等 mysql、`worker` 等 rabbitmq |
| `environment`（明文） | ConfigMap | `REDIS_URL`、`CELERY_BROKER_URL` |
| `environment`（敏感） | Secret | `MYSQL_ROOT_PASSWORD`、`SECRET_KEY`、含密码的连接串 |
| `ports`（发布到宿主机） | Service `type: NodePort`（或 LoadBalancer/Ingress） | `frontend`:30080、`grafana`:30300、`locust-master`:30089 |
| 挂载配置文件 | ConfigMap + volumeMount subPath | `prometheus.yml` |
| 同一 compose network | 同 namespace 内 Service DNS `<svc>.<ns>.svc` | 全部服务 |
| `--scale locust-worker=N` | 声明式 `replicas: N` / `kubectl scale` | `locust-worker` replicas=2 |

## 文件结构

| 文件 | 内容 |
|---|---|
| `00-namespace.yaml` | Namespace `whaletestpro` |
| `01-config.yaml` | Secret（密码/密钥）+ ConfigMap（非敏感 env、prometheus.yml） |
| `10-mysql.yaml` | MySQL StatefulSet + PVC + headless Service |
| `11-redis-rabbitmq.yaml` | Redis / RabbitMQ Deployment + Service |
| `20-app-worker.yaml` | FastAPI 后端 app（+ initContainer 等 mysql）+ Celery worker |
| `30-observability.yaml` | Prometheus + Grafana |
| `40-frontend-locust.yaml` | 前端 Nginx + Locust master/worker |

## 前置：镜像

manifest 里 `whaletestpro-app` / `whaletestpro-frontend` 是本地构建镜像的占位名。用 minikube 时先灌入：

```bash
docker compose build app frontend        # 或 docker build 各自 Dockerfile
minikube image load whaletestpro-app:latest
minikube image load whaletestpro-frontend:latest
```

或把 image 改成你 registry 的可拉取地址。

## 部署与校验

```bash
# 不连集群，纯校验 manifest 合法性（本项目已验证 22 个资源全部通过）
kubectl apply --dry-run=client -f k8s/

# 真集群部署（minikube/kind）
kubectl apply -f k8s/00-namespace.yaml
kubectl apply -f k8s/

# 查看状态
kubectl get all -n whaletestpro

# 浏览器访问（minikube 打通 NodePort）
minikube service frontend -n whaletestpro
minikube service grafana  -n whaletestpro

# 压测 worker 扩容（对标 compose 的 --scale）
kubectl scale deployment/locust-worker -n whaletestpro --replicas=5
```

## ⚠️ 安全提示

`01-config.yaml` 的 Secret 是**占位明文**，仅供理解结构。真部署请：
- 用 `kubectl create secret generic whaletestpro-secret --from-env-file=.env` 从 `.env` 生成，或
- 用 SealedSecrets / External Secrets Operator，

**绝不把真实密码/密钥提交进仓库**（与项目铁律一致）。
