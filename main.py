import json

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
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
from app.routers import team as team_router
from app.routers import scenario as scenario_router
from app.routers import suite as suite_router

from app.database import Base, engine, engine_shadow, SessionLocal
from app.core.bootstrap import (
    ensure_perf_schema,
    ensure_test_suite_schema,
    ensure_user_schema,
)
from app.core.migrations import run_all_migrations
from app.core.recording_monitor import recording_failure_monitor
from app.core.recording_publisher import publish_recording
from app.core.recording_policy import RECORD_SKIP_PREFIXES
from prometheus_fastapi_instrumentator import Instrumentator
import uvicorn
from app.core.shadow_ctx import set_shadow
from app.core.shadow_access import SHADOW_TOKEN_HEADER, shadow_request_allowed
from app.core.health_checks import (
    celery_broker_is_ready,
    database_is_ready,
    redis_is_ready,
)
from app.core.redis_client import redis_client
from app.core.celery_app import celery_app
from app.core.exception_handlers import (
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.schemas.traffic_record import TrafficRecordCreate
from app.schemas.response import success_response
from app.tasks.traffic import record_traffic, _mask
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
import app.models.scenario
import app.models.team
import app.models.team_member
import app.models.team_invitation
import app.models.team_permission
import app.models.scenario_report


Base.metadata.create_all(bind=engine)
Base.metadata.create_all(bind=engine_shadow)
run_all_migrations(engine, engine_shadow)
ensure_test_suite_schema(engine)
ensure_test_suite_schema(engine_shadow)
ensure_user_schema(engine)
ensure_user_schema(engine_shadow)

with SessionLocal() as db:
    ensure_perf_schema(db)

# 录制采样最简形式：不录这些"自身"接口（否则录制接口自己也被录、还会污染统计）
# 多项目改造:公共接口(auth/projects)没有 pid 上下文,不录制反而更干净


def _safe_json(raw: bytes):
    # body 不一定是 JSON（表单/空/二进制），不是就存 None，别让中间件崩
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _extract_project_id(request):
    """Only the server-authorized route may assign recording ownership."""
    return getattr(request.state, "recording_project_id", None)


app = FastAPI(docs_url=None)
app.add_exception_handler(HTTPException, http_exception_handler)
app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(Exception, unhandled_exception_handler)

@app.middleware("http")
async def shadow_middleware(request: Request, call_next):
    set_shadow(False)
    if request.headers.get("X-Shadow") == "1":
        if not shadow_request_allowed(request.method, request.url.path,
                                      request.headers.get(SHADOW_TOKEN_HEADER)):
            return JSONResponse(status_code=403, content={
                "code": 403, "message": "不允许使用此影子请求凭证", "data": None,
            })
        set_shadow(True)
    try:
        return await call_next(request)
    finally:
        set_shadow(False)


@app.middleware("http")
async def recording_middleware(request: Request, call_next):
    path = request.url.path
    if any(path.startswith(p) for p in RECORD_SKIP_PREFIXES):
        return await call_next(request)          # 自身接口，直接放行不录

    # —— 坑1：读请求体后塞回去，下游才能正常读 ——
    req_body = await request.body()
    request._body = req_body

    response = await call_next(request)

    project_id = _extract_project_id(request)
    if project_id is None or request.headers.get("X-Shadow") == "1":
        return response

    # —— 坑2：迭代响应体会耗尽流，读出来后必须重建 Response ——
    chunks = [chunk async for chunk in response.body_iterator]
    resp_body = b"".join(chunks)

    # 丢进 MQ（中间件只管抄一份扔进队列，立刻返回；落库/脱敏这些慢活由 worker 后台干）
    try:
        record = TrafficRecordCreate(
            method=request.method,
            path=path,
            request_headers=_mask(dict(request.headers)),
            request_body=_mask(_safe_json(req_body)),
            response_status=response.status_code,
            response_body=_mask(_safe_json(resp_body)),
            project_id=project_id,
        )
        # mode="json" 把 datetime 等转成可序列化的字符串，否则丢进 RabbitMQ 会序列化失败
        await publish_recording(record_traffic, record.model_dump(mode="json"))
    except Exception as exc:
        # 录制失败仍不影响业务响应，但必须留下可告警的指标和限频日志。
        recording_failure_monitor.report(
            exc,
            method=request.method,
            path=path,
        )

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
app.include_router(team_router.router)
app.include_router(scenario_router.router)
app.include_router(suite_router.router)

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

@app.get("/health/live")
def health_live():
    return success_response({"status": "alive"}, message="\u670d\u52a1\u5b58\u6d3b")


@app.get("/health/ready")
def health_ready():
    components = {
        "main_database": "ok" if database_is_ready(engine) else "unavailable",
        "shadow_database": "ok" if database_is_ready(engine_shadow) else "unavailable",
        "redis": "ok" if redis_is_ready(redis_client) else "unavailable",
        "rabbitmq": "ok" if celery_broker_is_ready(celery_app) else "unavailable",
    }
    if "unavailable" in components.values():
        return JSONResponse(
            status_code=503,
            content={
                "code": 503,
                "message": "\u670d\u52a1\u6682\u672a\u5c31\u7eea",
                "data": components,
            },
        )
    return success_response(
        {"status": "ready", **components},
        message="\u670d\u52a1\u5df2\u5c31\u7eea",
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
