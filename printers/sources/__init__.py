"""Where the models come from: the Icecat index and the manufacturers' sites.

Each source lists printers and hands back, for each, a way to look it up in
Icecat (a product code, an EAN or an Icecat id) and the markets it was seen
in. The sources overlap on purpose: a model missing from one is often in
another.

Left out, because they wall off plain HTTP clients with a 403: Canon's sites,
Galaxus and Digitec. Amazon forbids automated access. Lexmark is not in Open
Icecat. hp.com and brother.* are kept, since they publish model lists, but
they currently refuse non-browser clients; the run reports it and goes on.
"""

from dataclasses import dataclass, field
from typing import Protocol

from ..fetch import Fetcher

#: sources that refuse plain HTTP clients today: their failure is expected
KNOWN_WALLS = frozenset({"hp.com", "brother"})


@dataclass(frozen=True)
class Candidate:
    """A model found by a source, identified the way Icecat can look it up."""

    source: str
    brand: str = ""
    code: str = ""
    gtin: str = ""
    icecat_id: int | None = None
    url: str = ""
    markets: tuple[str, ...] = field(default=())

    @property
    def key(self) -> str:
        """Stable name of the lookup, to remember what Icecat answered."""
        if self.icecat_id is not None:
            return f"icecat:{self.icecat_id}"
        if self.gtin:
            return f"gtin:{self.gtin}"
        return f"{self.brand.lower()}:{self.code.lower()}"


class Source(Protocol):
    """A source module: its name, its markets and its discover function."""

    @property
    def NAME(self) -> str: ...  # noqa: N802 - module constants, read-only

    #: markets this source is asked about, one discover call each
    @property
    def MARKETS(self) -> tuple[str, ...]: ...  # noqa: N802

    def discover(
        self, fetcher: Fetcher, market: str, cache: dict[str, str]
    ) -> list[Candidate]: ...


def all_sources() -> list[Source]:
    # imported late: each of them imports Candidate from this module
    from . import brother, epson, hp, icecat_index  # noqa: PLC0415

    return [icecat_index, hp, brother, epson]
