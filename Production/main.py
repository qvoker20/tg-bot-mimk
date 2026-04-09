import uvicorn
from app.config import PRODUCTION_PORT
from app.main import app


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=PRODUCTION_PORT,
        reload=True,
    )
