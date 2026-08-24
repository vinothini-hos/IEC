from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import Base, engine
from .routers import threads, emails, gmail_webhook

Base.metadata.create_all(bind=engine)

app = FastAPI(title="IEC Mailbox API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(threads.router)
app.include_router(emails.router)
app.include_router(gmail_webhook.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
