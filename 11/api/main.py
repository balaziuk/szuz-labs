import os
import time
from collections import defaultdict

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field


class Ask(BaseModel):
    question: str = Field(min_length=3, max_length=500)


def create_app(answer_fn, chunks, limit=30, window=60.0):
    app = FastAPI(title="Фінансовий RAG", version="1.0")
    keys = {
        os.environ.get("LAB11_PUBLIC_KEY", "demo-public"): "public",
        os.environ.get("LAB11_ANALYST_KEY", "demo-analyst"): "analyst",
    }
    hits = defaultdict(list)

    def role_of(x_api_key):
        if not x_api_key or x_api_key not in keys:
            raise HTTPException(status_code=401, detail="потрібен дійсний X-API-Key")
        now = time.time()
        recent = [t for t in hits[x_api_key] if now - t < window]
        if len(recent) >= limit:
            raise HTTPException(status_code=429, detail="перевищено ліміт запитів")
        recent.append(now)
        hits[x_api_key] = recent
        return keys[x_api_key]

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.post("/ask")
    def ask(body: Ask, x_api_key: str | None = Header(default=None)):
        role = role_of(x_api_key)
        result = answer_fn(body.question, role)
        return {
            "answer": result["answer"], "sources": result["source_meta"], "graph_nodes": result["graph_nodes"],
            "rejected": result["rejected"], "role": role,
        }

    @app.get("/sources/{chunk_id}")
    def source(chunk_id: str, x_api_key: str | None = Header(default=None)):
        role = role_of(x_api_key)
        chunk = chunks.get(chunk_id)
        if chunk is None:
            raise HTTPException(status_code=404, detail="джерело не знайдено")
        if role == "public" and chunk["sensitivity"] != "public":
            raise HTTPException(status_code=403, detail="немає доступу до цього рівня sensitivity")
        return {
            "id": chunk["chunk_id"], "title": chunk["title"], "sensitivity": chunk["sensitivity"],
            "type": chunk["type"], "date": chunk["date"], "text": chunk["text"],
        }

    return app
