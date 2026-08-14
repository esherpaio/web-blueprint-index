from dataclasses import dataclass

from web.database.model import SitemapLocation


@dataclass(frozen=True)
class SitemapAlternate:
    hreflang: str
    href: str


@dataclass(frozen=True)
class SitemapEntry:
    location: SitemapLocation
    loc: str
    alternates: tuple[SitemapAlternate, ...] = ()
    image_locs: tuple[str, ...] = ()


@dataclass(frozen=True)
class Sitemap:
    loc: str
    lastmod: str
