import json

from fastapi import FastAPI, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from app.routers import interface as api_router
from app.routers import case as case_router
from app.routers import user as user_router
from app.routers import perf as perf_router
from app.routers import report as report_router
from app.routers import regression as regression_router
from app.routers import environment as environment_router
from app.routers import mock as mock_router
from app.routers import schedule as schedule_router
from app.routers import demo_order as demo_order_router
from app.routers import traffic_record as traffic_record_router
from app.routers import traffic_replay as traffic_replay_router
from app.routers import project as project_router

from app.database import Base, engine, engine_shadow
from prometheus_fastapi_instrumentator import Instrumentator
import uvicorn
from app.core.shadow_ctx import set_shadow
from app.schemas.traffic_record import TrafficRecordCreate
from app.tasks.traffic import record_traffic
import app.models.interface
import app.models.case
import app.models.user
import app.models.perf
import app.models.report
import app.models.environment
import app.models.mock
import app.models.schedule
import app.models.demo_order
import app.models.traffic_record
import app.models.project


Base.metadata.create_all(bind=engine)
Base.metadata.create_all(bind=engine_shadow)

# 录制采样最简形式：不录这些"自身"接口（否则录制接口自己也被录、还会污染统计）
# 多项目改造:公共接口(auth/projects)没有 pid 上下文,不录制反而更干净
RECORD_SKIP_PREFIXES = ("/traffic", "/metrics", "/docs", "/openapi.json", "/static", "/health", "/auth", "/projects")


def _safe_json(raw: bytes):
    # body 不一定是 JSON（表单/空/二进制），不是就存 None，别让中间件崩
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _extract_project_id(request):
    """
    从请求提取 project_id 用于流量归属,优先级:
    ① HTTP header X-Project-Id  —— 前端调业务接口时带
    ② URL 前缀 /mock/{pid}/xxx —— 被测系统调挡板时(URL 里带)
    ③ 兜底 pid=1(默认项目)—— 极少数漏网,不阻塞录制
    """
    pid = request.headers.get("X-Project-Id")
    if pid:
        try:
            return int(pid)
        except (ValueError, TypeError):
            pass
    parts = request.url.path.strip("/").split("/", 2)
    if len(parts) >= 2 and parts[0] == "mock" and parts[1].isdigit():
        return int(parts[1])
    return 1


app = FastAPI(docs_url=None)

@app.middleware("http")
async def shadow_middleware(request: Request, call_next):
    set_shadow(request.headers.get("X-Shadow") == "1")
    response = await call_next(request)
    return response


@app.middleware("http")
async def recording_middleware(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(p) for p in RECORD_SKIP_PREFIXES):
        return await call_next(request)          # 自身接口，直接放行不录

    # —— 坑1：读请求体后塞回去，下游才能正常读 ——
    req_body = await request.body()
    request._body = req_body

    response = await call_next(request)

    # —— 坑2：迭代响应体会耗尽流，读出来后必须重建 Response ——
    chunks = [chunk async for chunk in response.body_iterator]
    resp_body = b"".join(chunks)

    # 丢进 MQ（中间件只管抄一份扔进队列，立刻返回；落库/脱敏这些慢活由 worker 后台干）
    try:
        record = TrafficRecordCreate(
            method=request.method,
            path=path,
            request_headers=dict(request.headers),
            request_body=_safe_json(req_body),
            response_status=response.status_code,
            response_body=_safe_json(resp_body),
            project_id=_extract_project_id(request),   # ← 中间件从请求提取项目归属
        )
        # mode="json" 把 datetime 等转成可序列化的字符串，否则丢进 RabbitMQ 会序列化失败
        record_traffic.delay(record.model_dump(mode="json"))
    except Exception:
        pass                                     # 录制失败绝不影响正常业务请求

    # 用读出来的 body 重建响应返回（原 response 的流已被读光）
    return Response(
        content=resp_body,
        status_code=response.status_code,
        headers=dict(response.headers),
        media_type=response.media_type,
    )

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(api_router.router)
app.include_router(case_router.router)
app.include_router(user_router.router)
app.include_router(perf_router.router)
app.include_router(report_router.router)
app.include_router(regression_router.router)
app.include_router(environment_router.router)
app.include_router(mock_router.router)
app.include_router(mock_router.hit_router)
app.include_router(schedule_router.router)
app.include_router(demo_order_router.router)
app.include_router(traffic_record_router.router)
app.include_router(traffic_replay_router.router)
app.include_router(project_router.router)

# Prometheus 埋点：自动统计每个路由的请求数/耗时/进行中数，并暴露 /metrics 供抓取
Instrumentator().instrument(app).expose(app)


# 自己重写 /docs：内容还是 Swagger UI，但 JS/CSS/图标都改指向本地 /static，不再走 CDN
@app.get("/docs", include_in_schema=False)
def custom_swagger_ui_html():
    return get_swagger_ui_html(
        openapi_url=app.openapi_url,
        title="WhaleTestPro - Swagger UI",
        swagger_js_url="/static/swagger-ui-bundle.js",
        swagger_css_url="/static/swagger-ui.css",
        swagger_favicon_url="/static/favicon.png",
    )

@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)


