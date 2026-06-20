from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.openapi.docs import get_swagger_ui_html
from app.routers import interface as api_router
from app.routers import case as case_router
from app.database import Base, engine
import uvicorn
import app.models.interface
import app.models.case

Base.metadata.create_all(bind=engine)

app = FastAPI(docs_url=None)

app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(api_router.router)
app.include_router(case_router.router)


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


