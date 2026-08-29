"""
FastAPI main application for Real Estate Simulation
Refactored following SOLID principles - Single Responsibility
Main file only handles application setup and router registration
"""

import logging
import os
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.requests import Request
from fastapi.responses import JSONResponse

from api.cors import ENV_VAR, allowed_origins_from_env
from api.database import (
    close_mongo_connection,
    close_redis_connection,
    connect_to_mongo,
    connect_to_redis,
)
from api.observability import (
    REQUEST_ID_HEADER,
    bind_request_id,
    configure_logging,
    current_request_id,
    reset_request_id,
    sanitize_request_id,
)

# Import routers
from api.routers import admin, auth, charts, game, health, portfolio, trading

# Every log line carries the id of the request being handled; see
# api/observability.py.
configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager
    Handles startup and shutdown of external connections
    """
    # Startup
    logger.info("🚀 Starting Real Estate Game API...")
    await connect_to_mongo()
    await connect_to_redis()
    logger.info("✅ All connections established")

    yield

    # Shutdown
    logger.info("🛑 Shutting down Real Estate Game API...")
    await close_mongo_connection()
    await close_redis_connection()
    logger.info("✅ All connections closed")


# Create FastAPI application
app = FastAPI(
    title="Real Estate Simulation API",
    description="Backend API for real estate trading game with market simulation",
    version="2.0.0",
    lifespan=lifespan,
)

# Which browser origins may call this API. Set CORS_ALLOWED_ORIGINS to a comma
# separated list in any deployment that is not the local compose stack; see
# api/cors.py for what is accepted and why a wildcard is not.
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins_from_env(os.getenv(ENV_VAR)),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== MIDDLEWARE ====================


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Give the request an id, log what happened to it, hand the id back.

    The id is what makes a reported failure findable: it is on every log line
    emitted while this request is handled, and it is in the response, so the
    string in a bug report is the string to search for.
    """
    request_id = sanitize_request_id(request.headers.get(REQUEST_ID_HEADER))
    token = bind_request_id(request_id)
    start_time = time.perf_counter()

    try:
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start_time) * 1000

        # Key=value rather than a sentence: these lines get counted and
        # filtered far more often than they get read.
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
    except Exception:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        logger.exception(
            "request method=%s path=%s status=failed duration_ms=%.1f",
            request.method,
            request.url.path,
            elapsed_ms,
        )
        raise
    finally:
        reset_request_id(token)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Answer an unhandled failure with something the caller can quote.

    The message stays generic on purpose, since an exception string can carry
    internals. The request id does not: it is the handle that connects this
    answer to the traceback in the logs.
    """
    request_id = current_request_id()
    logger.exception("unhandled path=%s", request.url.path)

    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "type": "server_error",
            "requestId": request_id,
        },
        headers={REQUEST_ID_HEADER: request_id},
    )


# ==================== ROUTER REGISTRATION ====================
# Following SOLID principles: each router handles a single responsibility

# System health monitoring
app.include_router(health.router)

# User authentication and authorization
app.include_router(auth.router)

# Administrative operations (CRUD for properties, renovations, trades)
app.include_router(admin.router)

# Portfolio management and reporting
app.include_router(portfolio.router)

# Property trading (buy/sell, listings)
app.include_router(trading.router)

# Game mechanics (renovations, time advancement)
app.include_router(game.router)

# Data visualization and analytics
app.include_router(charts.router)


# ==================== APPLICATION ENTRY POINT ====================

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api.main:app", host="0.0.0.0", port=8000, reload=True, log_level="info")
