from xml.etree import ElementTree

import pytest
from flask import Flask

from bp_index import index_bp
from bp_index.sitemap.models import (
    RenderedSitemapBundle,
    SitemapAlternate,
    SitemapEnvelope,
    SitemapIndexEntry,
    SitemapLimits,
    SitemapLocationBundle,
    SitemapUrl,
)
from bp_index.sitemap.renderer import (
    get_sitemap_envelope,
    iter_sitemap_parts,
    render_sitemap_bundle,
    render_sitemap_index,
    render_sitemap_part,
    validate_sitemap_index,
)


@pytest.fixture
def app() -> Flask:
    app = Flask(__name__)
    app.register_blueprint(index_bp)
    return app


def _bundle(xml: bytes, url_count: int) -> RenderedSitemapBundle:
    return RenderedSitemapBundle(xml, url_count)


def _limits(
    *,
    target_urls: int = 100,
    target_bytes: int = 100,
    max_urls: int = 200,
    max_bytes: int = 200,
) -> SitemapLimits:
    return SitemapLimits(target_urls, target_bytes, max_urls, max_bytes)


def test_partitions_complete_bundles_by_url_count() -> None:
    envelope = SitemapEnvelope(b"<urlset>", b"</urlset>")
    bundles = [_bundle(b"a", 2), _bundle(b"b", 2), _bundle(b"c", 1)]

    parts = list(
        iter_sitemap_parts(
            bundles,
            envelope,
            _limits(target_urls=3),
        )
    )

    assert [part.fragments for part in parts] == [(b"a",), (b"b", b"c")]
    assert [part.url_count for part in parts] == [2, 3]


def test_partitions_by_exact_document_size() -> None:
    envelope = SitemapEnvelope(b"<u>", b"</u>")
    bundles = [_bundle(b"1234", 1), _bundle(b"5678", 1)]

    parts = list(
        iter_sitemap_parts(
            bundles,
            envelope,
            _limits(target_bytes=11),
        )
    )

    assert [part.byte_count for part in parts] == [11, 11]
    assert render_sitemap_part(parts[0], envelope) == b"<u>1234</u>"


def test_keeps_an_atomic_bundle_above_the_soft_target() -> None:
    envelope = SitemapEnvelope(b"<u>", b"</u>")

    parts = list(
        iter_sitemap_parts(
            [_bundle(b"123456", 4)],
            envelope,
            _limits(target_urls=3, target_bytes=10),
        )
    )

    assert len(parts) == 1
    assert parts[0].url_count == 4
    assert parts[0].byte_count == 13


def test_partition_iterator_does_not_consume_later_parts() -> None:
    envelope = SitemapEnvelope(b"<u>", b"</u>")
    consumed = []

    def bundles():
        for value in (b"a", b"b", b"c"):
            consumed.append(value)
            yield _bundle(value, 1)

    parts = iter_sitemap_parts(
        bundles(),
        envelope,
        _limits(target_urls=1),
    )

    assert next(parts).fragments == (b"a",)
    assert consumed == [b"a", b"b"]


@pytest.mark.parametrize(
    ("bundle", "limits", "message"),
    [
        (_bundle(b"x", 6), _limits(max_urls=5), "6 URL references"),
        (_bundle(b"1234", 1), _limits(max_bytes=10), "11 bytes"),
    ],
)
def test_rejects_an_atomic_bundle_above_a_hard_limit(
    bundle: RenderedSitemapBundle,
    limits: SitemapLimits,
    message: str,
) -> None:
    envelope = SitemapEnvelope(b"<u>", b"</u>")

    with pytest.raises(ValueError, match=message):
        list(iter_sitemap_parts([bundle], envelope, limits))


def test_counts_locations_alternates_and_images() -> None:
    url = SitemapUrl(
        "https://example.com/page",
        "2026-08-16",
        alternates=(
            SitemapAlternate("en-US", "https://example.com/en-us/page"),
            SitemapAlternate("x-default", "https://example.com/page"),
        ),
        image_locs=("https://example.com/one.jpg", "https://example.com/two.jpg"),
    )

    assert url.reference_count == 5


def test_renders_valid_escaped_xml(app: Flask) -> None:
    url = SitemapUrl(
        "https://example.com/page?a=1&b=2",
        "2026-08-16",
        image_locs=("https://example.com/image.jpg?a=1&b=2",),
    )

    with app.test_request_context():
        envelope = get_sitemap_envelope()
        bundle = render_sitemap_bundle(SitemapLocationBundle((url,)))
        part = next(iter_sitemap_parts([bundle], envelope, SitemapLimits()))
        xml = render_sitemap_part(part, envelope)

    root = ElementTree.fromstring(xml)
    assert root.tag == "{https://www.sitemaps.org/schemas/sitemap/0.9}urlset"
    assert b"a=1&amp;b=2" in xml


def test_renders_and_validates_sitemap_index(app: Flask) -> None:
    sitemaps = [SitemapIndexEntry("https://example.com/sitemap-pages-1.xml")]

    with app.test_request_context():
        xml = render_sitemap_index(sitemaps)
        validate_sitemap_index(xml, len(sitemaps), SitemapLimits())

    root = ElementTree.fromstring(xml)
    assert root.tag == "{http://www.sitemaps.org/schemas/sitemap/0.9}sitemapindex"
    assert b"lastmod" not in xml


@pytest.mark.parametrize(
    ("xml", "count", "limits", "message"),
    [
        (b"x", 2, _limits(max_urls=1), "2 sitemaps"),
        (b"xx", 1, _limits(max_bytes=1), "2 bytes"),
    ],
)
def test_rejects_sitemap_index_above_a_hard_limit(
    xml: bytes,
    count: int,
    limits: SitemapLimits,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        validate_sitemap_index(xml, count, limits)
