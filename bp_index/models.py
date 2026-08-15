from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Sitemap:
    loc: str
    lastmod: str


@dataclass(frozen=True)
class SitemapChunk:
    xml: bytes
    lastmod: datetime
    url_count: int


@dataclass(frozen=True)
class SitemapAlternate:
    hreflang: str
    href: str


@dataclass(frozen=True)
class SitemapEntry:
    loc: str
    lastmod: str
    alternates: tuple[SitemapAlternate, ...] = ()
    image_locs: tuple[str, ...] = ()


@dataclass(frozen=True)
class SitemapEntryBundle:
    entries: tuple[SitemapEntry, ...]
    lastmod: datetime
