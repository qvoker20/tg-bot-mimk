import os
from pathlib import Path

import uvicorn


PROJECT_DIR = Path(__file__).resolve().parent
RELOAD_ENABLED = os.getenv("ERP_RELOAD", "0") == "1"
HOST = os.getenv("ERP_HOST", "0.0.0.0")

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host=HOST,
        port=9182,
        reload=RELOAD_ENABLED,
        reload_dirs=[str(PROJECT_DIR)] if RELOAD_ENABLED else None,
        proxy_headers=True,        # Дозволяє читати заголовки від Cloudflare
        forwarded_allow_ips="*",   # Дозволяє приймати трафік від проксі-тунелю
    )