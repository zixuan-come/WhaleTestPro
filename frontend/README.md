# 前端部署配置

Grafana 按钮默认使用访问平台时的主机名、协议和 `3000` 端口，因此云端访问不会跳到访问者本机。若 Grafana 使用独立域名、HTTPS 反向代理或其他端口，可在构建时指定完整看板地址：

```bash
docker compose -p whaletestpro build \
  --build-arg VITE_GRAFANA_URL=https://monitor.example.com/d/perf-dash frontend
```

非 Docker 构建可通过构建进程的环境变量 `VITE_GRAFANA_URL` 配置。地址不包含访问凭证；Grafana 仍使用自身的登录和访问权限。

接口调试、用例、场景和套件的同步执行请求最多等待 10 分钟，Nginx 对这些运行路径等待 660 秒。请求超时或网关报错无法证明测试未执行；界面会提示先核实报告或目标数据，避免重复发送写请求。
