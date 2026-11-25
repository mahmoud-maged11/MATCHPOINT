import time
from threading import Lock


class RateLimiter:

    def __init__(self, min_interval: float):

        if min_interval < 0:
            raise ValueError(
                "Minimum interval cannot be negative"
            )

        self.min_interval = min_interval

        self.last_request_time = None

        self.lock = Lock()

    def wait(self):

        with self.lock:

            current_time = time.monotonic()

            if self.last_request_time is not None:

                elapsed = current_time - self.last_request_time

                remaining = self.min_interval - elapsed

                if remaining > 0:
                    time.sleep(remaining)

            self.last_request_time = time.monotonic()