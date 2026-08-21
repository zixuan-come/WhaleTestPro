# API 统一响应规范

本文档定义 WhaleTestPro 业务 API 的统一响应契约，作为后端、前端和独立接口自动化测试项目之间的协作约定。

## 1. 适用范围

除特殊协议接口外，业务 API 的成功和失败响应统一使用以下字段：

```json
{
  "code": 0,
  "message": "操作成功",
  "data": {}
}
```

适用模块包括认证、项目、环境、接口、用例、Mock、成员、场景、报告、回归和定时任务等。

以下接口不强制使用该格式：

- Prometheus 指标接口；
- Swagger/OpenAPI 文档接口；
- 文件下载、流式响应和 WebSocket 接口；
- 其他由协议本身规定响应格式的接口。

## 2. 字段定义

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `code` | integer | 业务结果码；成功固定为 `0`，失败时使用对应 HTTP 状态码 |
| `message` | string | 面向调用方的结果说明 |
| `data` | object / array / null | 业务数据；无数据时统一使用 `null` |

HTTP 状态码和响应体中的 `code` 同时保留：HTTP 状态码表示 HTTP 层结果，`code` 表示业务层结果。

当前阶段不单独设计 `10001`、`20001` 等复杂业务码，避免 HTTP 状态码和业务码含义重复。后续确有多端调用、国际化或复杂错误分类需求时再扩展。

## 3. 成功响应

### 3.1 单条资源

```json
{
  "code": 0,
  "message": "查询成功",
  "data": {
    "id": 1,
    "name": "WhaleTestPro"
  }
}
```

### 3.2 列表资源

```json
{
  "code": 0,
  "message": "查询成功",
  "data": [
    {
      "id": 1,
      "name": "WhaleTestPro"
    }
  ]
}
```

### 3.3 分页资源

分页数据统一放在 `data` 中：

```json
{
  "code": 0,
  "message": "查询成功",
  "data": {
    "items": [],
    "total": 0,
    "page": 1,
    "page_size": 20,
    "pages": 0
  }
}
```

### 3.4 无业务数据

需要返回操作结果但没有业务数据时，使用 `data: null`：

```json
{
  "code": 0,
  "message": "登出成功",
  "data": null
}
```

为保持响应格式一致，业务删除接口统一使用 `200 OK` 返回该结构，不使用带空响应体的 `204 No Content`。

## 4. 失败响应

### 4.1 通用错误

```json
{
  "code": 404,
  "message": "项目不存在",
  "data": null
}
```

失败响应仍然使用正确的 HTTP 状态码，不能只返回 `200` 再通过 `code` 表示失败。

### 4.2 认证失败

```json
{
  "code": 401,
  "message": "未登录或登录已过期",
  "data": null
}
```

### 4.3 权限不足

```json
{
  "code": 403,
  "message": "没有权限执行此操作",
  "data": null
}
```

### 4.4 业务冲突

```json
{
  "code": 409,
  "message": "用户已经是项目成员",
  "data": null
}
```

### 4.5 参数校验失败

参数校验失败时，统一保留可供前端定位字段的错误详情：

```json
{
  "code": 422,
  "message": "请求参数校验失败",
  "data": {
    "errors": [
      {
        "field": "name",
        "message": "名称不能为空"
      }
    ]
  }
}
```

### 4.6 服务端异常

对外只返回通用信息：

```json
{
  "code": 500,
  "message": "服务器内部错误",
  "data": null
}
```

真实异常堆栈写入服务端日志，不直接向调用方暴露 SQL、文件路径、依赖服务地址或内部实现细节。

## 5. 特殊响应处理

统一响应规范不覆盖所有 HTTP 响应。以下接口按照自身协议返回：

| 类型 | 处理方式 |
| --- | --- |
| 健康检查 | 作为普通业务 API，可统一为 `code/message/data` |
| Prometheus 指标 | 保留 Prometheus 文本格式 |
| Swagger/OpenAPI | 保留 OpenAPI 规范格式 |
| 文件下载 | 返回文件流，不包装 JSON |
| 流式响应 | 返回流，不包装 JSON |
| WebSocket | 按 WebSocket 消息协议处理 |

## 6. 前端调用约定

前端 HTTP 客户端负责统一拆包：

1. HTTP 请求成功后检查 `code`；
2. `code === 0` 时向页面层返回 `data`；
3. `code !== 0` 时使用 `message` 创建错误；
4. HTTP 状态码为 `401` 时清理本地 Token 并跳转登录页；
5. 页面组件不重复处理 `response.data.data`。

## 7. 接口自动化测试约定

WhaleTestPro-APITest 保持独立 HTTP 黑盒，不导入 WhaleTestPro 的代码。

成功用例至少校验：

- HTTP 状态码；
- `code == 0`；
- 必要时校验 `message`；
- 业务字段从 `data` 下提取。

示例：

```yaml
assert_response:
  code: 0
  message: 查询成功

extract:
  project_id: data.id
```

失败用例至少校验：

```yaml
assert_response:
  code: 404
  message: 项目不存在
```

## 8. 当前迁移状态

统一响应迁移已覆盖以下业务模块:

- 认证、健康检查、项目、环境和项目成员;
- 接口、测试用例、Mock 管理;
- 场景、普通报告和场景报告;
- 回归、定时任务、性能任务、流量记录、流量回放和 Demo 接口。

前端通过 HTTP 客户端统一拆包,页面组件继续使用业务数据;独立接口自动化测试通过 HTTP 黑盒校验外层响应,不依赖后端源码。Mock 命中、Prometheus、Swagger、静态资源和文件/流式协议仍按各自协议返回。

## 9. 迁移原则

统一响应迁移按模块进行，不一次性修改全部接口：

1. 先实现后端公共响应模型和全局异常处理；
2. 再迁移认证和系统基础接口；
3. 然后迁移项目、环境和成员模块；
4. 最后迁移接口、用例、场景、报告和异步任务模块；
5. 每个模块迁移后同步更新前端、APITest 和接口文档；
6. 被测接口的原始响应只作为执行结果中的业务数据保存，不强行改写。

最终验收至少包括后端单测、APITest 黑盒回归、前端生产构建、Docker Compose 配置校验、容器状态检查和健康接口检查。
