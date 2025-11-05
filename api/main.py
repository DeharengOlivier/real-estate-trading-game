"""
FastAPI main application for Real Estate Simulation
Refactored following SOLID principles - Single Responsibility
Main file only handles application setup and router registration
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.requests import Request
from contextlib import asynccontextmanager
import logging
import time

from api.database import (
    connect_to_mongo, connect_to_redis, 
    close_mongo_connection, close_redis_connection
)

# Import routers
from api.routers import health, auth, admin, portfolio, trading, game, charts

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
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
    lifespan=lifespan
)

# Configure CORS
# For production, you should restrict this to your frontend's domain
origins = [
    "http://localhost:5173",  # React local dev server
    "http://127.0.0.1:5173",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== MIDDLEWARE ====================

@app.middleware("http")
async def log_requests(request: Request, call_next):
    """
    Request logging middleware
    Logs all HTTP requests with timing information
    """
    start_time = time.time()
    
    try:
        response = await call_next(request)
        process_time = time.time() - start_time
        
        logger.info(
            f"{request.method} {request.url.path} "
            f"completed in {process_time:.3f}s with status {response.status_code}"
        )
        
        return response
    except Exception as e:
        process_time = time.time() - start_time
        logger.error(f"Request failed after {process_time:.3f}s: {str(e)}")
        raise


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """
    Global exception handler
    Catches unhandled exceptions and returns consistent error response
    """
    logger.error(f"Unhandled exception: {str(exc)}", exc_info=True)
    
    return JSONResponse(
        status_code=500,
        content={
            "detail": "Internal server error",
            "type": "server_error"
        }
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
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
