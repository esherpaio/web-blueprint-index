import itertools

from flask import Response, abort, current_app, make_response, render_template
from sqlalchemy import true
from sqlalchemy.orm import joinedload, selectinload
from web.app.urls import url_for
from web.cache import cache
from web.database import conn
from web.database.model import AppRoute, SitemapImageMode, SitemapLocation
from web.locale import gen_locale
from web.utils.modifiers import text_to_xml

from bp_index import index_bp
from bp_index.models import (
    Sitemap,
    SitemapAlternate,
    SitemapChunk,
    SitemapEntry,
    SitemapEntryBundle,
)

SITEMAP_TARGET_URLS = 40_000
SITEMAP_TARGET_BYTES = 40 * 1024 * 1024
SITEMAP_MAX_URLS = 50_000
SITEMAP_MAX_BYTES = 50 * 1024 * 1024

LocaleVariant = tuple[dict[str, str], str]

#
# Routes
#


@index_bp.route("/sitemap.xml")
def sitemap() -> Response:
    locale_variants = _get_locale_variants()
    localized_endpoints = _get_localized_endpoints()
    sitemaps: list[Sitemap] = []

    # Sitemap groups with standard URLs
    for group in _get_sitemap_groups():
        chunks = _get_sitemap_chunks(
            group,
            locale_variants=locale_variants,
            localized_endpoints=localized_endpoints,
        )
        sitemaps.extend(
            Sitemap(
                loc=url_for(
                    "index.sitemap_group",
                    group=group,
                    part=part,
                    _external=True,
                ),
                lastmod=chunk.lastmod.strftime("%Y-%m-%d"),
            )
            for part, chunk in enumerate(chunks, start=1)
        )

    # Sitemap groups with image-only URLs
    for group in _get_sitemap_groups(image_only=True):
        chunks = _get_sitemap_chunks(
            group,
            image_only=True,
            locale_variants=locale_variants,
            localized_endpoints=localized_endpoints,
        )
        sitemaps.extend(
            Sitemap(
                loc=url_for(
                    "index.sitemap_group_images",
                    group=group,
                    part=part,
                    _external=True,
                ),
                lastmod=chunk.lastmod.strftime("%Y-%m-%d"),
            )
            for part, chunk in enumerate(chunks, start=1)
        )

    if not sitemaps:
        abort(404)
    template = render_template("sitemap_index.xml", sitemaps=sitemaps)
    return _xml_response(text_to_xml(template))


@index_bp.route("/sitemap-<string:group>.xml", defaults={"part": None})
@index_bp.route("/sitemap-<string:group>-<int:part>.xml")
def sitemap_group(group: str, part: int | None) -> Response:
    if part is None:
        url = url_for("index.sitemap_group", group=group, part=1)
        return make_response("", 301, {"Location": url})
    return _get_sitemap_part(group, part)


@index_bp.route("/sitemap-<string:group>-images.xml", defaults={"part": None})
@index_bp.route("/sitemap-<string:group>-images-<int:part>.xml")
def sitemap_group_images(group: str, part: int | None) -> Response:
    if part is None:
        url = url_for("index.sitemap_group_images", group=group, part=1)
        return make_response("", 301, {"Location": url})
    return _get_sitemap_part(group, part, image_only=True)


def _get_sitemap_part(
    group: str,
    part: int,
    image_only: bool = False,
) -> Response:
    if part < 1:
        abort(404)
    chunks = _get_sitemap_chunks(group, image_only=image_only)
    if part > len(chunks):
        abort(404)
    return _xml_response(chunks[part - 1].xml)


def _xml_response(xml: bytes) -> Response:
    response = make_response(xml)
    response.headers["Content-Type"] = "application/xml"
    return response


#
# Queries
#


def _get_sitemap_groups(image_only: bool = False) -> list[str]:
    with conn.begin() as s:
        query = (
            s.query(AppRoute.sitemap_group)
            .select_from(SitemapLocation)
            .join(SitemapLocation.route)
            .filter(AppRoute.in_sitemap == true())
        )
        if image_only:
            query = query.filter(
                AppRoute.sitemap_image_mode == SitemapImageMode.SEPARATE,
                SitemapLocation.images.any(),
            )
        rows = query.distinct().order_by(AppRoute.sitemap_group).all()
    return [group for (group,) in rows]


def _get_sitemap_locations(
    group: str,
    image_only: bool = False,
) -> list[SitemapLocation]:
    with conn.begin() as s:
        query = (
            s.query(SitemapLocation)
            .join(SitemapLocation.route)
            .options(
                joinedload(SitemapLocation.route),
                selectinload(SitemapLocation.images),
            )
            .filter(
                AppRoute.in_sitemap == true(),
                AppRoute.sitemap_group == group,
            )
        )
        if image_only:
            query = query.filter(
                AppRoute.sitemap_image_mode == SitemapImageMode.SEPARATE,
                SitemapLocation.images.any(),
            )
        return query.order_by(SitemapLocation.route_id, SitemapLocation.id).all()


#
# Entries
#


def _get_sitemap_entry_bundles(
    group: str,
    image_only: bool = False,
    locale_variants: tuple[LocaleVariant, ...] | None = None,
    localized_endpoints: set[str] | None = None,
) -> list[SitemapEntryBundle]:
    sitemap_locations = _get_sitemap_locations(group, image_only=image_only)
    if locale_variants is None:
        locale_variants = tuple() if image_only else _get_locale_variants()
    elif image_only:
        locale_variants = tuple()
    if localized_endpoints is None:
        localized_endpoints = _get_localized_endpoints()

    bundles: list[SitemapEntryBundle] = []
    for sitemap_location in sitemap_locations:
        route = sitemap_location.route
        is_localized = route.endpoint in localized_endpoints

        endpoint_arg_variants: tuple[dict[str, str], ...]
        if is_localized:
            if image_only:
                endpoint_arg_variants = ({"_locale": gen_locale()},)
            elif locale_variants:
                endpoint_arg_variants = tuple(
                    endpoint_args for endpoint_args, _ in locale_variants
                )
            else:
                continue
        else:
            endpoint_arg_variants = ({},)

        alternates = (
            _get_sitemap_alternates(sitemap_location, locale_variants)
            if not image_only and is_localized
            else tuple()
        )
        include_images = (
            image_only or route.sitemap_image_mode == SitemapImageMode.COMBINED
        )
        image_locs = (
            tuple(image.loc for image in sitemap_location.images)
            if include_images
            else tuple()
        )
        lastmod = sitemap_location.lastmod.strftime("%Y-%m-%d")
        entries = tuple(
            SitemapEntry(
                loc=url_for(
                    route.endpoint,
                    **(sitemap_location.endpoint_args | endpoint_arg_variant),
                    _external=True,
                ),
                lastmod=lastmod,
                alternates=alternates,
                image_locs=image_locs,
            )
            for endpoint_arg_variant in endpoint_arg_variants
        )
        bundles.append(SitemapEntryBundle(entries, sitemap_location.lastmod))

    return bundles


def _get_sitemap_alternates(
    sitemap_location: SitemapLocation,
    locale_variants: tuple[LocaleVariant, ...],
) -> tuple[SitemapAlternate, ...]:
    route = sitemap_location.route
    alternates = [
        SitemapAlternate(
            hreflang,
            url_for(
                route.endpoint,
                **(sitemap_location.endpoint_args | locale_args),
                _external=True,
            ),
        )
        for locale_args, hreflang in locale_variants
    ]
    default_args = sitemap_location.endpoint_args | {"_locale": gen_locale()}
    url = url_for(route.endpoint, **default_args, _external=True)
    alternates.append(SitemapAlternate("x-default", url))
    return tuple(alternates)


def _get_locale_variants() -> tuple[LocaleVariant, ...]:
    countries = (country for country in cache.countries if country.in_sitemap)
    languages = (language for language in cache.languages if language.in_sitemap)
    return tuple(
        (
            {"_locale": gen_locale(language.code, country.code)},
            f"{language.code.lower()}-{country.code.upper()}",
        )
        for country, language in itertools.product(countries, languages)
    )


def _get_localized_endpoints() -> set[str]:
    return {
        rule.endpoint
        for rule in current_app.url_map.iter_rules()
        if "_locale" in rule.arguments
    }


#
# Partitioning
#


def _get_sitemap_chunks(
    group: str,
    image_only: bool = False,
    locale_variants: tuple[LocaleVariant, ...] | None = None,
    localized_endpoints: set[str] | None = None,
) -> list[SitemapChunk]:
    bundles = _get_sitemap_entry_bundles(
        group,
        image_only=image_only,
        locale_variants=locale_variants,
        localized_endpoints=localized_endpoints,
    )
    return _partition_sitemap_bundles(bundles)


def _partition_sitemap_bundles(
    bundles: list[SitemapEntryBundle],
) -> list[SitemapChunk]:
    chunks: list[SitemapChunk] = []
    start = 0
    while start < len(bundles):
        end = _get_count_limited_end(bundles, start)
        chunk = _build_sitemap_chunk(bundles[start:end])

        if len(chunk.xml) > SITEMAP_TARGET_BYTES and end - start > 1:
            end, chunk = _find_largest_fitting_chunk(bundles, start, end)

        _validate_sitemap_chunk(chunk)
        chunks.append(chunk)
        start = end

    return chunks


def _get_count_limited_end(
    bundles: list[SitemapEntryBundle],
    start: int,
) -> int:
    url_count = 0
    end = start
    while end < len(bundles):
        bundle_url_count = len(bundles[end].entries)
        if end > start and url_count + bundle_url_count > SITEMAP_TARGET_URLS:
            break
        url_count += bundle_url_count
        end += 1
        if url_count >= SITEMAP_TARGET_URLS:
            break
    return end


def _find_largest_fitting_chunk(
    bundles: list[SitemapEntryBundle],
    start: int,
    end: int,
) -> tuple[int, SitemapChunk]:
    # The full count-limited candidate is too large. Rendering prefixes with a
    # binary search avoids repeatedly rendering the sitemap after every bundle.
    best_end: int | None = None
    best_chunk: SitemapChunk | None = None
    low = start + 1
    high = end - 1

    while low <= high:
        candidate_end = (low + high) // 2
        candidate = _build_sitemap_chunk(bundles[start:candidate_end])
        if (
            candidate.url_count <= SITEMAP_TARGET_URLS
            and len(candidate.xml) <= SITEMAP_TARGET_BYTES
        ):
            best_end = candidate_end
            best_chunk = candidate
            low = candidate_end + 1
        else:
            high = candidate_end - 1

    if best_end is not None and best_chunk is not None:
        return best_end, best_chunk

    single_bundle_end = start + 1
    return single_bundle_end, _build_sitemap_chunk(bundles[start:single_bundle_end])


def _build_sitemap_chunk(bundles: list[SitemapEntryBundle]) -> SitemapChunk:
    entries = tuple(itertools.chain.from_iterable(bundle.entries for bundle in bundles))
    template = render_template("sitemap.xml", entries=entries)
    xml = text_to_xml(template)
    lastmod = max(bundle.lastmod for bundle in bundles)
    return SitemapChunk(xml=xml, lastmod=lastmod, url_count=len(entries))


def _validate_sitemap_chunk(chunk: SitemapChunk) -> None:
    if chunk.url_count > SITEMAP_MAX_URLS:
        raise ValueError(
            f"Sitemap chunk contains {chunk.url_count} URLs; "
            f"the maximum is {SITEMAP_MAX_URLS}"
        )
    if len(chunk.xml) > SITEMAP_MAX_BYTES:
        raise ValueError(
            f"Sitemap chunk is {len(chunk.xml)} bytes; "
            f"the maximum is {SITEMAP_MAX_BYTES} bytes"
        )
