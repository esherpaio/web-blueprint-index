import itertools
from collections import defaultdict
from collections.abc import Iterator

from flask import current_app
from sqlalchemy import true
from sqlalchemy.orm import joinedload
from web.app.urls import url_for
from web.database import conn
from web.database.model import (
    AppRoute,
    Country,
    Language,
    SitemapImage,
    SitemapImageMode,
    SitemapLocation,
)
from web.locale import LocaleStyle, gen_locale

from .models import (
    SitemapAlternate,
    SitemapIndexEntry,
    SitemapKind,
    SitemapLimits,
    SitemapLocationBundle,
    SitemapPart,
    SitemapUrl,
)
from .renderer import (
    get_sitemap_envelope,
    iter_sitemap_parts,
    render_sitemap_bundle,
    render_sitemap_index,
    render_sitemap_part,
    validate_sitemap_index,
)

LocaleVariant = tuple[dict[str, str], str]


class SitemapService:
    def __init__(self, limits: SitemapLimits | None = None) -> None:
        self._limits = limits or SitemapLimits()
        self._locale_variants = self._get_locale_variants()
        self._endpoints, self._localized_endpoints = self._get_endpoints()
        self._envelope = get_sitemap_envelope()

    def render_index(self) -> bytes | None:
        sitemaps: list[SitemapIndexEntry] = []
        for kind in SitemapKind:
            endpoint = (
                "index.sitemap_group"
                if kind is SitemapKind.PAGES
                else "index.sitemap_group_images"
            )
            for group in self._get_groups(kind):
                for part, _ in enumerate(self._iter_parts(group, kind), start=1):
                    sitemaps.append(
                        SitemapIndexEntry(
                            url_for(
                                endpoint,
                                group=group,
                                part=part,
                                _external=True,
                            )
                        )
                    )

        if not sitemaps:
            return None
        xml = render_sitemap_index(sitemaps)
        validate_sitemap_index(xml, len(sitemaps), self._limits)
        return xml

    def render_part(
        self,
        group: str,
        part_number: int,
        kind: SitemapKind,
    ) -> bytes | None:
        if part_number < 1:
            return None
        for number, part in enumerate(self._iter_parts(group, kind), start=1):
            if number == part_number:
                return render_sitemap_part(part, self._envelope)
        return None

    def _iter_parts(
        self,
        group: str,
        kind: SitemapKind,
    ) -> Iterator[SitemapPart]:
        bundles = (
            render_sitemap_bundle(bundle)
            for bundle in self._get_location_bundles(group, kind)
        )
        return iter_sitemap_parts(bundles, self._envelope, self._limits)

    def _get_groups(self, kind: SitemapKind) -> list[str]:
        with conn.begin() as session:
            query = (
                session.query(AppRoute.sitemap_group)
                .select_from(SitemapLocation)
                .join(SitemapLocation.route)
                .filter(
                    AppRoute.in_sitemap == true(),
                    AppRoute.endpoint.in_(self._endpoints),
                )
            )
            if kind is SitemapKind.IMAGES:
                query = query.filter(
                    AppRoute.sitemap_image_mode == SitemapImageMode.SEPARATE,
                    SitemapLocation.images.any(),
                )
            rows = query.distinct().order_by(AppRoute.sitemap_group).all()

        groups = [group for (group,) in rows]
        return groups

    def _get_location_bundles(
        self,
        group: str,
        kind: SitemapKind,
    ) -> list[SitemapLocationBundle]:
        with conn.begin() as session:
            query = (
                session.query(SitemapLocation)
                .join(SitemapLocation.route)
                .options(joinedload(SitemapLocation.route))
                .filter(
                    AppRoute.in_sitemap == true(),
                    AppRoute.endpoint.in_(self._endpoints),
                    AppRoute.sitemap_group == group,
                )
            )
            if kind is SitemapKind.IMAGES:
                query = query.filter(
                    AppRoute.sitemap_image_mode == SitemapImageMode.SEPARATE,
                    SitemapLocation.images.any(),
                )
            locations = query.order_by(
                SitemapLocation.route_id,
                SitemapLocation.id,
            ).all()

            image_location_ids = [
                location.id
                for location in locations
                if kind is SitemapKind.IMAGES
                or location.route.sitemap_image_mode == SitemapImageMode.COMBINED
            ]
            images_by_location: defaultdict[int, list[str]] = defaultdict(list)
            if image_location_ids:
                images = (
                    session.query(SitemapImage.location_id, SitemapImage.loc)
                    .filter(SitemapImage.location_id.in_(image_location_ids))
                    .order_by(SitemapImage.location_id, SitemapImage.loc)
                    .all()
                )
                for location_id, loc in images:
                    images_by_location[location_id].append(loc)

            bundles = []
            for location in locations:
                bundle = self._get_location_bundle(
                    location,
                    kind,
                    tuple(images_by_location[location.id]),
                )
                if bundle is not None:
                    bundles.append(bundle)
            return bundles

    def _get_location_bundle(
        self,
        location: SitemapLocation,
        kind: SitemapKind,
        image_locs: tuple[str, ...],
    ) -> SitemapLocationBundle | None:
        route = location.route
        is_localized = route.endpoint in self._localized_endpoints

        if not is_localized:
            endpoint_arg_variants: tuple[dict[str, str], ...] = ({},)
        elif kind is SitemapKind.IMAGES:
            endpoint_arg_variants = ({"_locale": gen_locale()},)
        elif self._locale_variants:
            endpoint_arg_variants = tuple(
                endpoint_args for endpoint_args, _ in self._locale_variants
            )
        else:
            return None

        alternates = (
            self._get_alternates(location)
            if kind is SitemapKind.PAGES and is_localized
            else tuple()
        )
        lastmod = location.lastmod.strftime("%Y-%m-%d")
        urls = tuple(
            SitemapUrl(
                loc=url_for(
                    route.endpoint,
                    **(location.endpoint_args | endpoint_arg_variant),
                    _external=True,
                ),
                lastmod=lastmod,
                alternates=alternates,
                image_locs=image_locs,
            )
            for endpoint_arg_variant in endpoint_arg_variants
        )
        return SitemapLocationBundle(urls)

    def _get_alternates(
        self,
        location: SitemapLocation,
    ) -> tuple[SitemapAlternate, ...]:
        route = location.route
        alternates = [
            SitemapAlternate(
                hreflang,
                url_for(
                    route.endpoint,
                    **(location.endpoint_args | locale_args),
                    _external=True,
                ),
            )
            for locale_args, hreflang in self._locale_variants
        ]
        default_args = location.endpoint_args | {"_locale": gen_locale()}
        alternates.append(
            SitemapAlternate(
                "x-default",
                url_for(route.endpoint, **default_args, _external=True),
            )
        )
        if len({alternate.href for alternate in alternates}) < 2:
            return tuple()
        return tuple(alternates)

    @staticmethod
    def _get_locale_variants() -> tuple[LocaleVariant, ...]:
        # Every enabled country/language combination must be a routable locale.
        with conn.begin() as session:
            country_codes = (
                session.query(Country.code)
                .filter(Country.in_sitemap == true())
                .order_by(Country.code)
                .all()
            )
            language_codes = (
                session.query(Language.code)
                .filter(Language.in_sitemap == true())
                .order_by(Language.code)
                .all()
            )
        return tuple(
            (
                {"_locale": gen_locale(language_code, country_code)},
                gen_locale(
                    language_code,
                    country_code,
                    style=LocaleStyle.BCP47,
                ),
            )
            for (country_code,), (language_code,) in itertools.product(
                country_codes,
                language_codes,
            )
        )

    @staticmethod
    def _get_endpoints() -> tuple[set[str], set[str]]:
        endpoints = set()
        localized_endpoints = set()
        for rule in current_app.url_map.iter_rules():
            endpoints.add(rule.endpoint)
            if "_locale" in rule.arguments:
                localized_endpoints.add(rule.endpoint)
        return endpoints, localized_endpoints
