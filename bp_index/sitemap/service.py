import itertools
from collections import defaultdict

from flask import current_app
from sqlalchemy import true
from sqlalchemy.orm import Query, Session, joinedload
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
    SitemapKind,
    SitemapLimits,
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

_GROUP_ENDPOINTS = {
    SitemapKind.PAGES: "index.sitemap_group",
    SitemapKind.IMAGES: "index.sitemap_group_images",
}


class SitemapService:
    def __init__(self, limits: SitemapLimits | None = None) -> None:
        self._limits = limits or SitemapLimits()
        self._locale_variants = self._get_locale_variants()
        self._endpoints, self._localized_endpoints = self._get_endpoints()
        self._envelope = get_sitemap_envelope()
        self._parts: dict[tuple[str, SitemapKind], list[SitemapPart]] = {}

    def render_index(self) -> bytes | None:
        locs = [
            url_for(_GROUP_ENDPOINTS[kind], group=group, part=part, _external=True)
            for kind in SitemapKind
            for group in self._get_groups(kind)
            for part, _ in enumerate(self._get_parts(group, kind), start=1)
        ]
        if not locs:
            return None
        xml = render_sitemap_index(locs)
        validate_sitemap_index(xml, len(locs), self._limits)
        return xml

    def render_part(
        self,
        group: str,
        part_number: int,
        kind: SitemapKind,
    ) -> bytes | None:
        parts = self._get_parts(group, kind)
        if not 1 <= part_number <= len(parts):
            return None
        return render_sitemap_part(parts[part_number - 1], self._envelope)

    def _get_parts(self, group: str, kind: SitemapKind) -> list[SitemapPart]:
        if (group, kind) not in self._parts:
            bundles = (
                render_sitemap_bundle(urls)
                for urls in self._get_location_urls(group, kind)
            )
            self._parts[(group, kind)] = list(
                iter_sitemap_parts(bundles, self._envelope, self._limits)
            )
        return self._parts[(group, kind)]

    def _filter_routes(self, query: Query, kind: SitemapKind) -> Query:
        query = query.filter(
            AppRoute.in_sitemap == true(),
            AppRoute.endpoint.in_(self._endpoints),
        )
        if kind is SitemapKind.IMAGES:
            query = query.filter(
                AppRoute.sitemap_image_mode == SitemapImageMode.SEPARATE,
                SitemapLocation.images.any(),
            )
        return query

    def _get_groups(self, kind: SitemapKind) -> list[str]:
        with conn.begin() as session:
            query = (
                session.query(AppRoute.sitemap_group)
                .select_from(SitemapLocation)
                .join(SitemapLocation.route)
            )
            rows = (
                self._filter_routes(query, kind)
                .distinct()
                .order_by(AppRoute.sitemap_group)
                .all()
            )
        return [group for (group,) in rows]

    def _get_location_urls(
        self,
        group: str,
        kind: SitemapKind,
    ) -> list[tuple[SitemapUrl, ...]]:
        with conn.begin() as session:
            query = (
                session.query(SitemapLocation)
                .join(SitemapLocation.route)
                .options(joinedload(SitemapLocation.route))
                .filter(AppRoute.sitemap_group == group)
            )
            locations = (
                self._filter_routes(query, kind)
                .order_by(SitemapLocation.route_id, SitemapLocation.id)
                .all()
            )
            images = self._get_images(session, locations, kind)
            bundles = []
            for location in locations:
                urls = self._get_urls(location, kind, tuple(images[location.id]))
                if urls:
                    bundles.append(urls)
            return bundles

    @staticmethod
    def _get_images(
        session: Session,
        locations: list[SitemapLocation],
        kind: SitemapKind,
    ) -> defaultdict[int, list[str]]:
        location_ids = [
            location.id
            for location in locations
            if kind is SitemapKind.IMAGES
            or location.route.sitemap_image_mode == SitemapImageMode.COMBINED
        ]
        images: defaultdict[int, list[str]] = defaultdict(list)
        if not location_ids:
            return images
        rows = (
            session.query(SitemapImage.location_id, SitemapImage.loc)
            .filter(SitemapImage.location_id.in_(location_ids))
            .order_by(SitemapImage.location_id, SitemapImage.loc)
            .all()
        )
        for location_id, loc in rows:
            images[location_id].append(loc)
        return images

    def _get_urls(
        self,
        location: SitemapLocation,
        kind: SitemapKind,
        image_locs: tuple[str, ...],
    ) -> tuple[SitemapUrl, ...]:
        route = location.route
        is_localized = route.endpoint in self._localized_endpoints

        if not is_localized:
            locale_variants: tuple[dict[str, str], ...] = ({},)
        elif kind is SitemapKind.IMAGES:
            locale_variants = ({"_locale": gen_locale()},)
        elif self._locale_variants:
            locale_variants = tuple(args for args, _ in self._locale_variants)
        else:
            return ()

        alternates = (
            self._get_alternates(location)
            if kind is SitemapKind.PAGES and is_localized
            else ()
        )
        lastmod = location.lastmod.strftime("%Y-%m-%d")
        return tuple(
            SitemapUrl(
                loc=url_for(
                    route.endpoint,
                    **(location.endpoint_args | locale_args),
                    _external=True,
                ),
                lastmod=lastmod,
                alternates=alternates,
                image_locs=image_locs,
            )
            for locale_args in locale_variants
        )

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
            return ()
        return tuple(alternates)

    @staticmethod
    def _get_locale_variants() -> tuple[LocaleVariant, ...]:
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
                gen_locale(language_code, country_code, style=LocaleStyle.BCP47),
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
