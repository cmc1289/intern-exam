from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.exam import router as exam_router
from app.api.records import router as records_router
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

if (STATIC_DIR / "index.html").is_file():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
