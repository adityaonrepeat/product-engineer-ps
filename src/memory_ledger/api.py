"""Thin FastAPI transport for the memory engine."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import JSONResponse

from memory_ledger.database import DatabasePath, initialize_database
from memory_ledger.models import (
    CreateResult,
    HealthResponse,
    MemoryConflictError,
    MemoryCreate,
    MemoryInspection,
    MemoryNotFoundError,
    MemoryRecord,
    RetrievalRequest,
    RetrievalResponse,
)
from memory_ledger.reconciliation import (
    correct_memory,
    delete_memory,
    flag_conflict,
    inspect_memory,
)
from memory_ledger.repository import create_memory
from memory_ledger.retrieval import retrieve_memories

DEFAULT_DATABASE = Path("memory-ledger.db")


def get_database(request: Request) -> DatabasePath:
    return request.app.state.database


DatabaseDependency = Annotated[DatabasePath, Depends(get_database)]


def create_app(database: DatabasePath = DEFAULT_DATABASE) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        initialize_database(app.state.database)
        yield

    app = FastAPI(
        title="Memory Ledger",
        summary="Deterministic, provenance-aware long-term memory",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.state.database = database

    @app.exception_handler(MemoryNotFoundError)
    async def memory_not_found(_request: Request, error: MemoryNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(error)})

    @app.exception_handler(MemoryConflictError)
    async def memory_conflict(_request: Request, error: MemoryConflictError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(error)})

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse()

    @app.post("/v1/memories", response_model=CreateResult, tags=["memories"])
    def store_memory(
        candidate: MemoryCreate,
        response: Response,
        database_path: DatabaseDependency,
    ) -> CreateResult:
        result = create_memory(database_path, candidate)
        response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return result

    @app.get(
        "/v1/memories/{memory_id}",
        response_model=MemoryInspection,
        tags=["memories"],
    )
    def inspect(memory_id: UUID, database_path: DatabaseDependency) -> MemoryInspection:
        return inspect_memory(database_path, memory_id)

    @app.post(
        "/v1/memories/{memory_id}/corrections",
        response_model=CreateResult,
        tags=["memories"],
    )
    def correct(
        memory_id: UUID,
        candidate: MemoryCreate,
        response: Response,
        database_path: DatabaseDependency,
    ) -> CreateResult:
        result = correct_memory(database_path, memory_id, candidate)
        response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return result

    @app.post(
        "/v1/memories/{memory_id}/conflicts",
        response_model=CreateResult,
        tags=["memories"],
    )
    def conflict(
        memory_id: UUID,
        candidate: MemoryCreate,
        response: Response,
        database_path: DatabaseDependency,
    ) -> CreateResult:
        result = flag_conflict(database_path, memory_id, candidate)
        response.status_code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return result

    @app.post("/v1/retrievals", response_model=RetrievalResponse, tags=["retrieval"])
    def retrieve(
        retrieval_request: RetrievalRequest,
        database_path: DatabaseDependency,
    ) -> RetrievalResponse:
        return retrieve_memories(database_path, retrieval_request)

    @app.delete(
        "/v1/memories/{memory_id}",
        response_model=MemoryRecord,
        tags=["memories"],
    )
    def delete(memory_id: UUID, database_path: DatabaseDependency) -> MemoryRecord:
        return delete_memory(database_path, memory_id)

    return app


app = create_app()
