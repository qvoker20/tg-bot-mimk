import os
import sys

import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware

try:
    from .config import PRODUCTION_PORT, SECRET_KEY, STATIC_DIR, TEMPLATES_DIR
    from .routers import auth, komplekt_api, pages, reestr_api, zapusky_api
except ImportError:
    # Allows running this file directly: python Production/app/main.py
    CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
    PARENT_DIR = os.path.dirname(CURRENT_DIR)
    if PARENT_DIR not in sys.path:
        sys.path.insert(0, PARENT_DIR)

    from app.config import PRODUCTION_PORT, SECRET_KEY, STATIC_DIR, TEMPLATES_DIR
    from app.routers import auth, komplekt_api, pages, reestr_api, zapusky_api

app = FastAPI(title="MIMK Production")
app.add_middleware(
    SessionMiddleware,
    secret_key=SECRET_KEY,
    max_age=60 * 60 * 12,
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
templates = Jinja2Templates(directory=TEMPLATES_DIR)
pages.set_templates(templates)

app.include_router(pages.router)
app.include_router(auth.router)
app.include_router(komplekt_api.router)
app.include_router(reestr_api.router)
app.include_router(zapusky_api.router)


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=PRODUCTION_PORT, reload=True)
