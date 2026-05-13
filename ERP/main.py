import os
from pathlib import Path

import uvicorn


PROJECT_DIR = Path(__file__).resolve().parent
RELOAD_ENABLED = os.getenv("ERP_RELOAD", "0") == "1"

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=9182,
        reload=RELOAD_ENABLED,
        reload_dirs=[str(PROJECT_DIR)] if RELOAD_ENABLED else None,
    )