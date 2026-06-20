from locust import HttpUser, task, between

class URLShortenerUser(HttpUser):
    # This dictates how fast a single simulated user makes requests
    wait_time = between(1.0, 3.0) 

    @task
    def test_cache_redirect(self):
        self.client.get("/AhFLyHL", allow_redirects=False)