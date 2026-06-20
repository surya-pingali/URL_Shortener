import os
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request, BackgroundTasks
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncpg
import redis.asyncio as redis
from dotenv import load_dotenv

# Load
load_dotenv(override=True)

DATABASE_URL = os.getenv("DATABASE_URL")
REDIS_URL = os.getenv("REDIS_URL")

# Global variables
db_pool = None
redis_client = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global db_pool, redis_client
    # Startup
    db_pool = await asyncpg.create_pool(DATABASE_URL)
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    yield
    # Shutdown
    await db_pool.close()
    await redis_client.aclose()

app = FastAPI(lifespan=lifespan, title="High-Concurrency URL Shortener")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic model
class URLRequest(BaseModel):
    url: str

def generate_short_code(length=7):
    """Generates a cryptographically secure Base62 string."""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
    return ''.join(secrets.choice(chars) for _ in range(length))

@app.get("/")
async def serve_ui():
    """Serves the frontend dashboard."""
    return FileResponse("dashboard.html")

@app.post("/shorten")
async def shorten_url(payload: URLRequest, request: Request):
    global db_pool, redis_client
    
    # Rate Limiting Logic (10 requests per 60 seconds)
    client_ip = request.client.host if request.client else "unknown"
    rate_key = f"rate_limit:{client_ip}"
    
    request_count = await redis_client.incr(rate_key)
    if request_count == 1:
        await redis_client.expire(rate_key, 60)
        
    if request_count > 10:
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Try again in a minute.")

    # Input Validation
    target_url = payload.url
    if not target_url.startswith(("http://", "https://")):
        target_url = "https://" + target_url

    short_code = generate_short_code()
    
    # Database Insertion
    async with db_pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO urls (original_url, short_code) VALUES ($1, $2)",
                target_url, short_code
            )
        except asyncpg.exceptions.UniqueViolationError:
            raise HTTPException(status_code=500, detail="Collision detected, please try again.")
    
    return {
        "original_url": target_url, 
        "short_code": short_code, 
        "shortened_url": f"http://localhost:8000/{short_code}"
    }

async def log_click(short_code: str, ip_address: str, user_agent: str):
    """Asynchronously logs click data to the PostgreSQL database."""
    global db_pool
    if not db_pool:
        return
        
    async with db_pool.acquire() as conn:
        try:
            await conn.execute(
                "INSERT INTO clicks (short_code, ip_address, user_agent) VALUES ($1, $2, $3)",
                short_code, ip_address, user_agent
            )
        except Exception as e:
            # Silently handle logging failures
            print(f"Logging failed: {e}")

@app.get("/{short_code}")
async def redirect_to_url(short_code: str, request: Request, background_tasks: BackgroundTasks):
    global db_pool, redis_client
    
    # High-Concurrency Read
    cached_url = await redis_client.get(short_code)
    
    if cached_url:
        # Cache Hit
        client_ip = request.client.host if request.client else "unknown"
        user_agent = request.headers.get("user-agent", "unknown")
        background_tasks.add_task(log_click, short_code, client_ip, user_agent)
        
        return RedirectResponse(url=cached_url, status_code=307)
    
    # Cache Miss
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT original_url FROM urls WHERE short_code = $1", short_code
        )
        
    if not row:
        raise HTTPException(status_code=404, detail="URL not found")
        
    original_url = row["original_url"]
    
    # Write back to Redis for future requests (Cache TTL set to 24 hours / 86400 seconds)
    await redis_client.setex(short_code, 86400, original_url)
    
    # Trigger analytics
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "unknown")
    background_tasks.add_task(log_click, short_code, client_ip, user_agent)
    
    return RedirectResponse(url=original_url, status_code=307)

@app.get("/stats/{short_code}")
async def get_stats(short_code: str):
    global db_pool
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database connection failed")
        
    async with db_pool.acquire() as conn:
        # Verify the URL exists
        exists = await conn.fetchval("SELECT 1 FROM urls WHERE short_code = $1", short_code)
        if not exists:
            raise HTTPException(status_code=404, detail="Short code not found")
            
        # Aggregate the data
        total_clicks = await conn.fetchval("SELECT COUNT(*) FROM clicks WHERE short_code = $1", short_code)
        recent_clicks = await conn.fetch(
            "SELECT ip_address, timestamp FROM clicks WHERE short_code = $1 ORDER BY timestamp DESC LIMIT 5", 
            short_code
        )
        
    return {
        "short_code": short_code,
        "total_clicks": total_clicks,
        "recent_activity": [
            {"ip": record["ip_address"], "time": record["timestamp"].strftime("%Y-%m-%d %H:%M:%S")} 
            for record in recent_clicks
        ]
    }