from collections.abc import Iterator

import pytest
from flask import Flask

from bp_index import index_bp
from bp_index.routes import sitemap as sitemap_routes
from bp_index.sitemap.models import SitemapKind


class FakeSitemapService:
    index_xml: bytes | None = b"<sitemapindex />"
    part_xml: bytes | None = b"<urlset />"
    calls: list[tuple[str, int, SitemapKind]] = []

    def render_index(self) -> bytes | None:
        return self.index_xml

    def render_part(
        self,
        group: str,
        part: int,
        kind: SitemapKind,
    ) -> bytes | None:
        self.calls.append((group, part, kind))
        return self.part_xml


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator:
    FakeSitemapService.index_xml = b"<sitemapindex />"
    FakeSitemapService.part_xml = b"<urlset />"
    FakeSitemapService.calls = []
    monkeypatch.setattr(sitemap_routes, "SitemapService", FakeSitemapService)
    app = Flask(__name__)
    app.register_blueprint(index_bp)
    with app.test_client() as client:
        yield client


def test_sitemap_index_is_xml(client) -> None:
    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert response.content_type == "application/xml"
    assert response.data == b"<sitemapindex />"


@pytest.mark.parametrize(
    ("url", "location"),
    [
        ("/sitemap-pages.xml", "/sitemap-pages-1.xml"),
        ("/sitemap-catalog-images.xml", "/sitemap-catalog-images-1.xml"),
    ],
)
def test_unnumbered_sitemap_redirects_to_first_part(
    client,
    url: str,
    location: str,
) -> None:
    response = client.get(url)

    assert response.status_code == 301
    assert response.headers["Location"] == location


@pytest.mark.parametrize(
    ("url", "call"),
    [
        ("/sitemap-pages-2.xml", ("pages", 2, SitemapKind.PAGES)),
        (
            "/sitemap-catalog-images-3.xml",
            ("catalog", 3, SitemapKind.IMAGES),
        ),
    ],
)
def test_numbered_sitemap_renders_requested_part(client, url: str, call) -> None:
    response = client.get(url)

    assert response.status_code == 200
    assert FakeSitemapService.calls == [call]


@pytest.mark.parametrize(
    "url",
    ["/sitemap.xml", "/sitemap-pages-1.xml", "/sitemap-invalid_group-1.xml"],
)
def test_missing_sitemap_returns_404(client, url: str) -> None:
    FakeSitemapService.index_xml = None
    FakeSitemapService.part_xml = None

    assert client.get(url).status_code == 404
