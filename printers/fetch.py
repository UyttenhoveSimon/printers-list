"""Polite HTTP: one session, a pause between requests, walls reported as such.

A site that answers with an anti-bot interstitial, a 403 or an image where a
text file was expected is walled off. That is reported with `BotWallError`
and the source is skipped for the run; nothing here tries to get past it.
"""

import logging
import time
from http import HTTPStatus
from typing import Any
from urllib.parse import urlsplit

import requests

logger = logging.getLogger(__name__)

USER_AGENT = (
    "printers-list/0.1 (+https://github.com/UyttenhoveSimon/printers-list) "
    "python-requests"
)
TIMEOUT = 30
#: courtesy pause between two requests to the same host
DELAY_SECONDS = 0.5

#: pages served instead of the real content by the common bot walls
BOT_WALL_MARKERS = (
    "captcha-delivery.com",
    "/cdn-cgi/challenge-platform",
    "_Incapsula_Resource",
    "Access Denied</title>",
)
WALL_STATUSES = frozenset(
    {HTTPStatus.FORBIDDEN, HTTPStatus.TOO_MANY_REQUESTS, HTTPStatus.UNAUTHORIZED}
)


class FetchError(RuntimeError):
    """The page could not be read: network error or an unexpected status."""


class BotWallError(FetchError):
    """The site served an anti-bot wall instead of the page."""


class Fetcher:
    def __init__(
        self,
        session: requests.Session | None = None,
        delay: float = DELAY_SECONDS,
    ) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(
            {"User-Agent": USER_AGENT, "Accept-Language": "en,fr;q=0.8,nl;q=0.6"}
        )
        self.delay = delay
        self._last_request: dict[str, float] = {}

    def _pause(self, url: str) -> None:
        host = urlsplit(url).netloc
        last = self._last_request.get(host)
        if last is not None:
            wait = self.delay - (time.monotonic() - last)
            if wait > 0:
                time.sleep(wait)
        self._last_request[host] = time.monotonic()

    def get(self, url: str, params: dict[str, str] | None = None) -> requests.Response:
        """Return the response whatever its status; only the network can fail."""
        self._pause(url)
        try:
            return self.session.get(url, params=params, timeout=TIMEOUT)
        except requests.RequestException as error:
            raise FetchError(f"{url}: {error}") from error

    def text(self, url: str) -> str:
        """Return the body of a page or text file, or raise when it is walled."""
        response = self.get(url)
        host = urlsplit(url).netloc
        if response.status_code in WALL_STATUSES:
            raise BotWallError(f"{host} refused the request ({response.status_code})")
        if response.status_code != HTTPStatus.OK:
            raise FetchError(f"{url}: HTTP {response.status_code}")
        content_type = response.headers.get("Content-Type", "")
        if content_type.startswith("image/"):
            # hp.com answers a market without an online shop with a picture
            raise FetchError(f"{url}: served {content_type}, not a page")
        body = response.text
        for marker in BOT_WALL_MARKERS:
            if marker in body:
                raise BotWallError(f"{host} served an anti-bot page ({marker})")
        return body

    def stream(self, url: str, auth: tuple[str, str]) -> requests.Response:
        """Open a large authenticated download, to be read as it arrives."""
        self._pause(url)
        try:
            response = self.session.get(url, auth=auth, stream=True, timeout=TIMEOUT)
        except requests.RequestException as error:
            raise FetchError(f"{url}: {error}") from error
        if response.status_code == HTTPStatus.UNAUTHORIZED:
            raise FetchError(f"{url}: login or password refused")
        if response.status_code != HTTPStatus.OK:
            raise FetchError(f"{url}: HTTP {response.status_code}")
        return response

    def json(
        self,
        url: str,
        params: dict[str, str],
        headers: dict[str, str] | None = None,
    ) -> tuple[int, Any]:
        """Return the status and decoded body of a JSON API call."""
        self._pause(url)
        try:
            response = self.session.get(
                url, params=params, headers=headers, timeout=TIMEOUT
            )
        except requests.RequestException as error:
            raise FetchError(f"{url}: {error}") from error
        try:
            return response.status_code, response.json()
        except ValueError as error:
            raise FetchError(f"{url}: not JSON ({response.status_code})") from error
