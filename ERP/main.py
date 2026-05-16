import os
from pathlib import Path

import uvicorn

PROJECT_DIR = Path(__file__).resolve().parent
RELOAD_ENABLED = os.getenv("ERP_RELOAD", "0") == "1"
HOST = os.getenv("ERP_HOST", "0.0.0.0")

# For production: use multiple workers (default = cpu_count).
# For development with reload: force workers=1 (reload incompatible with multiple workers).
# Can be overridden via ERP_WORKERS env var.
DEFAULT_WORKERS = 1 if RELOAD_ENABLED else None  # None = auto-detect cpu_count
WORKERS = int(os.getenv("ERP_WORKERS", DEFAULT_WORKERS or 1))

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=9182,
        workers=WORKERS,
        reload=RELOAD_ENABLED,
        reload_dirs=[str(PROJECT_DIR)] if RELOAD_ENABLED else None,
        proxy_headers=True,        # Дозволяє читати заголовки від Cloudflare
        forwarded_allow_ips="*",   # Дозволяє приймати трафік від проксі-тунелю
    )