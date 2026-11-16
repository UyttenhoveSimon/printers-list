"""Pages read through headless Chromium, for makers' sites that refuse plain HTTP.

HP's shop answers only clients that run its scripts like a browser. The same
courtesy as `Fetcher` holds: one page at a time, a pause between two requests
to a host, and a wall or an error status raised, never retried.
"""

import time
from types import TracebackType
from typing import Any, Self
from urllib.parse import urlsplit

from .fetch import (
    BOT_WALL_MARKERS,
    DELAY_SECONDS,
    TIMEOUT,
    WALL_STATUSES,
    BotWallError,
    FetchError,
)

FIRST_ERROR_STATUS = 400


class Browser:
    """A `Fetcher` look-alike (``text(url)``) backed by one Chromium tab."""

    def __init__(self, delay: float = DELAY_SECONDS) -> None:
        self.delay = delay
        self._last_request: dict[str, float] = {}
        self._engine: Any = None
        self._browser: Any = None
        self._page: Any = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        self.close()

    def _open(self) -> None:
        # imported here: only a run that needs a browser pays for starting one
        from rustwright.sync_api import sync_playwright  # noqa: PLC0415

        self._engine = sync_playwright().start()
        self._browser = self._engine.chromium.launch(headless=True)
        self._page = self._browser.new_page()

    def _pause(self, url: str) -> None:
        host = urlsplit(url).netloc
        last = self._last_request.get(host)
        if last is not None:
            wait = self.delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request[host] = time.monotonic()

    def text(self, url: str) -> str:
        """The body the server sent for ``url``, or raise when it is walled."""
        if self._page is None:
            self._open()
        self._pause(url)
        host = urlsplit(url).netloc
        try:
            response = self._page.goto(url, timeout=TIMEOUT * 1000)
        except Exception as error:  # rustwright raises its own error types
            raise FetchError(f"{url}: {error}") from error
        if response is None:
            raise FetchError(f"{url}: no response")
        if response.status in WALL_STATUSES:
            raise BotWallError(f"{host} refused the browser ({response.status})")
        if response.status >= FIRST_ERROR_STATUS:
            raise FetchError(f"{url}: HTTP {response.status}")
        try:
            body = response.text()
        except Exception:  # noqa: BLE001 - Chromium may evict a large or redirected body
            body = self._page.content()
        for marker in BOT_WALL_MARKERS:
            if marker in body:
                raise BotWallError(f"{host} served an anti-bot page ({marker})")
        return body

    def close(self) -> None:
        if self._browser is not None:
            self._browser.close()
            self._engine.stop()
        self._engine = self._browser = self._page = None
