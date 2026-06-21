# High-Concurrency URL Shortener

A highly concurrent URL shortener service built with FastAPI, PostgreSQL, and Redis. It features in-memory caching for rapid redirects, asynchronous background tasks for click analytics, and rate limiting to prevent abuse.

## Features
- **URL Shortening:** Generates cryptographically secure 7-character Base62 short codes.
- **High Concurrency Caching:** Utilizes Redis to cache active URLs (24-hour TTL) for sub-millisecond redirect resolution.
- **Asynchronous Analytics:** Logs visitor data (IP address, Timestamp, User-Agent) to PostgreSQL via FastAPI background tasks without blocking the redirect response.
- **Rate Limiting:** Implements IP-based rate limiting (10 requests per 60 seconds) using Redis.
- **Frontend Dashboard:** A built-in HTML/TailwindCSS UI for generating short links and viewing analytics.

## Tech Stack
- **Backend:** Python 3.11, FastAPI, Uvicorn
- **Database:** PostgreSQL (`asyncpg`)
- **Cache / Rate Limiter:** Redis (`redis.asyncio`)
- **Load Testing:** Locust
- **Frontend:** HTML5, TailwindCSS (via CDN)

## Performance and Load Testing

The system is designed for high-concurrency read operations. Load testing was conducted using Locust to evaluate redirect performance under stress. The test bypassed redirects (`allow_redirects=False`) to measure the raw throughput of the cache and routing layers.

During the stress test, the service successfully handled over 1,600 requests with a 0% failure rate. It sustained an impressive continuous throughput of over 40 requests per second (RPS) (peaking around 44 RPS), while maintaining a swift median response time of just 260ms. These numbers clearly demonstrate the architecture's robust capability to manage high traffic volumes efficiently, directly validating the effectiveness of the Redis caching layer and the asynchronous database operations under the hood.

## Prerequisites
- Python 3.11
- PostgreSQL server
- Redis server

## Installation and Setup

1. **Clone the repository and navigate to the directory.**

2. **Create and activate a virtual environment:**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```

3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Configuration:**
   Create a `.env` file in the root directory and define the following variables:
   ```env
   DATABASE_URL=postgresql://user:password@localhost:5432/dbname
   REDIS_URL=redis://localhost:6379/0
   ```

5. **Database Initialization:**
   Ensure your PostgreSQL database has the following tables created:
   - `urls` (columns: `original_url`, `short_code` [UNIQUE])
   - `clicks` (columns: `short_code`, `ip_address`, `user_agent`, `timestamp`)

6. **Run the application:**
   ```bash
   uvicorn main:app --host 0.0.0.0 --port 8000
   ```
   The dashboard will be available at `http://localhost:8000/`.

7. **Running the Load Test:**
   To replicate the load test, start the FastAPI server and run Locust using the provided script:
   ```bash
   locust -f locustfile.py
   ```
   Access the Locust web interface at `http://localhost:8089` to configure user spawn rates and initiate the test.

## API Endpoints

- `GET /`: Serves the frontend dashboard.
- `POST /shorten`: Accepts a JSON payload `{"url": "https://..."}` and returns the shortened URL.
- `GET /{short_code}`: Redirects to the original URL (cached via Redis) and triggers asynchronous analytics logging.
- `GET /stats/{short_code}`: Returns total clicks and recent activity (last 5 clicks) for the specified short code.
