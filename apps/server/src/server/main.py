from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.context_api import router as context_router
from server.exports import router as exports_router
from server.pipeline import router as pipeline_router
from server.templates import router as templates_router

app = FastAPI(title="project-preza server")
app.include_router(context_router)
app.include_router(templates_router)
app.include_router(pipeline_router)
app.include_router(exports_router)

# Dev-only: apps/web runs on a different port. Tighten this once there's a real
# deployment target — see ARCHITECTURE.md's apps/server boundary note.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
