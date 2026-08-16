from collections.abc import Iterable, Iterator

from flask import render_template

from .models import (
    RenderedSitemapBundle,
    SitemapEnvelope,
    SitemapIndexEntry,
    SitemapLimits,
    SitemapLocationBundle,
    SitemapPart,
)

_ENTRY_MARKER = "__SITEMAP_URL_ENTRIES__"


def get_sitemap_envelope() -> SitemapEnvelope:
    template = render_template("sitemap.xml", entries_xml=_ENTRY_MARKER).encode()
    prefix, marker, suffix = template.partition(_ENTRY_MARKER.encode())
    if not marker:
        raise ValueError("The sitemap template does not contain its entries marker")
    return SitemapEnvelope(prefix, suffix)


def render_sitemap_bundle(bundle: SitemapLocationBundle) -> RenderedSitemapBundle:
    xml = render_template("sitemap_urls.xml", entries=bundle.urls).encode()
    return RenderedSitemapBundle(
        xml=xml,
        url_count=sum(url.reference_count for url in bundle.urls),
    )


def iter_sitemap_parts(
    bundles: Iterable[RenderedSitemapBundle],
    envelope: SitemapEnvelope,
    limits: SitemapLimits,
) -> Iterator[SitemapPart]:
    fragments: list[bytes] = []
    url_count = 0
    byte_count = envelope.byte_count

    for bundle in bundles:
        bundle_bytes = len(bundle.xml)
        _validate_bundle(bundle, bundle_bytes, envelope, limits)

        exceeds_target = fragments and (
            url_count + bundle.url_count > limits.target_urls
            or byte_count + bundle_bytes > limits.target_bytes
        )
        if exceeds_target:
            yield SitemapPart(tuple(fragments), url_count, byte_count)
            fragments = []
            url_count = 0
            byte_count = envelope.byte_count

        fragments.append(bundle.xml)
        url_count += bundle.url_count
        byte_count += bundle_bytes

    if fragments:
        yield SitemapPart(tuple(fragments), url_count, byte_count)


def render_sitemap_part(
    part: SitemapPart,
    envelope: SitemapEnvelope,
) -> bytes:
    xml = b"".join((envelope.prefix, *part.fragments, envelope.suffix))
    if len(xml) != part.byte_count:
        raise ValueError("Rendered sitemap size differs from its partitioned size")
    return xml


def render_sitemap_index(sitemaps: list[SitemapIndexEntry]) -> bytes:
    return render_template("sitemap_index.xml", sitemaps=sitemaps).encode()


def validate_sitemap_index(
    xml: bytes,
    sitemap_count: int,
    limits: SitemapLimits,
) -> None:
    if sitemap_count > limits.max_urls:
        raise ValueError(
            f"Sitemap index contains {sitemap_count} sitemaps; "
            f"the maximum is {limits.max_urls}"
        )
    if len(xml) > limits.max_bytes:
        raise ValueError(
            f"Sitemap index is {len(xml)} bytes; "
            f"the maximum is {limits.max_bytes} bytes"
        )


def _validate_bundle(
    bundle: RenderedSitemapBundle,
    bundle_bytes: int,
    envelope: SitemapEnvelope,
    limits: SitemapLimits,
) -> None:
    if bundle.url_count > limits.max_urls:
        raise ValueError(
            f"One sitemap location contains {bundle.url_count} URL references; "
            f"the maximum per sitemap is {limits.max_urls}"
        )
    document_bytes = envelope.byte_count + bundle_bytes
    if document_bytes > limits.max_bytes:
        raise ValueError(
            f"One sitemap location renders as {document_bytes} bytes; "
            f"the maximum per sitemap is {limits.max_bytes} bytes"
        )
