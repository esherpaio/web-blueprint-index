from datetime import datetime

from web.app.urls import url_for


class Sitemap:
    def __init__(self, endpoint: str) -> None:
        self._endpoint = endpoint

    @property
    def loc(self) -> str:
        return url_for(self._endpoint, _external=True)


class SitemapUrl:
    def __init__(self, endpoint: str, updated_at: datetime, **endpoint_args) -> None:
        self._endpoint = endpoint
        self._endpoint_args = endpoint_args
        self._updated_at = updated_at

    @property
    def loc(self) -> str:
        return url_for(self._endpoint, **self._endpoint_args, _external=True)

    @property
    def lastmod(self) -> str:
        return self._updated_at.strftime("%Y-%m-%d")
