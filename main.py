from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from app.routers import interface as api_router
from app.routers import case as case_router
from app.routers import user as user_router
from app.routers import perf as perf_router
from app.database import Base, engine
from prometheus_fastapi_instrumentator import Instrumentator
import uvicorn
import app.models.interface
import app.models.case
import app.models.user
import app.models.perf

Base.metadata.create_all(bind=engine)

app = FastAPI(docs_url=None)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(api_router.router)
app.include_router(case_router.router)
app.include_router(user_router.router)
app.include_router(perf_router.router)

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


