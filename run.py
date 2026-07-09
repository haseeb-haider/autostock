"""Local entry point: seed demo data (once) then start the server.

    python run.py
"""
import uvicorn

from app.seed import seed

if __name__ == "__main__":
    seed()
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)
