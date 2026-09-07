from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.admin import router as admin_router
from app.api.exam import router as exam_router
from app.api.records import router as records_router
from app.api.report import router as report_router
from app.config import STATIC_DIR


app = FastAPI(title="入职考核系统")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(exam_router, prefix="/api")
app.include_router(records_router, prefix="/api")
app.include_router(report_router, prefix="/api")
app.include_router(admin_router, prefix="/api/admin")


# SPA 兜底：/admin* 独立后台页、/exam/{id} 考试入口（必须在静态挂载之前注册）
@app.get("/admin", include_in_schema=False)
@app.get("/admin/{path:path}", include_in_schema=False)
async def admin_spa(path: str = ""):
    return FileResponse(STATIC_DIR / "admin.html")


@app.get("/exam/{exam_id}", include_in_schema=False)
async def exam_entry_spa(exam_id: str):
    return FileResponse(STATIC_DIR / "index.html")


if (STATIC_DIR / "index.html").is_file():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
