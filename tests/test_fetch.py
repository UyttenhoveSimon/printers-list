"""The fetcher's reading of what a site answered; the session is a fake."""

import pytest
import requests

from printers.fetch import BotWallError, Fetcher, FetchError


class Response:
    def __init__(self, status=200, text="", content_type="text/plain", body=None):
        self.status_code = status
        self.text = text
        self.headers = {"Content-Type": content_type}
        self.body = body

    def json(self):
        if self.body is None:
            raise ValueError
        return self.body


class Session:
    def __init__(self, response):
        self.response = response
        self.headers = {}

    def get(self, url, **kwargs):
        if isinstance(self.response, Exception):
            raise self.response
        return self.response


def fetcher(response):
    return Fetcher(session=Session(response), delay=0)


def test_text():
    assert fetcher(Response(text="hello")).text("https://a.example/") == "hello"


@pytest.mark.parametrize("status", [401, 403, 429])
def test_refusals_are_walls(status):
    with pytest.raises(BotWallError):
        fetcher(Response(status)).text("https://a.example/")


def test_challenge_pages_are_walls():
    page = Response(text='<script src="/cdn-cgi/challenge-platform/x.js">')
    with pytest.raises(BotWallError, match="challenge-platform"):
        fetcher(page).text("https://a.example/")


def test_an_image_instead_of_a_list_is_an_error():
    with pytest.raises(FetchError, match="image/png"):
        fetcher(Response(content_type="image/png")).text("https://a.example/")


def test_other_statuses_and_network_errors():
    with pytest.raises(FetchError, match="HTTP 500"):
        fetcher(Response(500)).text("https://a.example/")
    with pytest.raises(FetchError):
        fetcher(requests.ConnectionError("reset")).text("https://a.example/")


def test_json():
    assert fetcher(Response(404, body={})).json("https://a.example/", {}) == (404, {})
    with pytest.raises(FetchError, match="not JSON"):
        fetcher(Response(502)).json("https://a.example/", {})


def test_the_user_agent_says_who_it_is():
    session = Session(Response())
    Fetcher(session=session)
    assert "printers-list" in session.headers["User-Agent"]
