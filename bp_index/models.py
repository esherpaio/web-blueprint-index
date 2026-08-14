from datetime import datetime

from web.app.urls import url_for


class Sitemap:
    def __init__(
        self,
        endpoint: str,
        lastmod: datetime,
        **endpoint_args: str,
    ) -> None:
        self._endpoint = endpoint
        self._endpoint_args = endpoint_args
        self._lastmod = lastmod

    @property
    def loc(self) -> str:
        return url_for(self._endpoint, **self._endpoint_args, _external=True)

    @property
    def lastmod(self) -> str:
        return self._lastmod.strftime("%Y-%m-%d")
