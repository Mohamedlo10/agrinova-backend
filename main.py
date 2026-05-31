from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.database import engine, Base
from app.routes import router
import os

Base.metadata.create_all(bind=engine)
os.makedirs("static/images", exist_ok=True)

app = FastAPI(
    title="Agrinova API",
    description="API du marketplace agricole Agrinova",
    version="2.0.0",
    docs_url="/docs" if os.getenv("ENV") != "production" else None,
    redoc_url=None,
)

# CORS — en prod, mettre l'URL exacte du frontend dans FRONTEND_URL
FRONTEND_URL = os.getenv("FRONTEND_URL", "*")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL] if FRONTEND_URL != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix="/api")
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
def health():
    return {"status": "ok", "version": "2.0.0"}
