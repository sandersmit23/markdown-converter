"""Wat de ophaal van EUR-Lex en het Hof meldt als er geen document komt (kb WP-105, F7 van plan 6).

De grote test van de kennisbank (oktober 2026) liet zes documenten vastlopen op een melding
die niet klopte. Twee EUR-Lex-foutpagina's ("The requested document does not exist.") werden
als bron bewaard en `ok` gemeld (32004D0411, 32004L0048; M9). Een 404 op de Formex van het
Hof heette altijd "een arrest van de laatste dagen of weken", ook voor Inteligo Media en
Russmedia, die in het Nederlands alleen HTML hebben (M5), en voor Advies 1/15, waarvan het
CELEX `62015CV0001(01)` niet URL-gecodeerd werd (M22). Geen netwerk: `net.documents` wordt
vervangen; de metadata-antwoorden hebben de vorm van het SPARQL-endpoint, met de aantallen
die de Cellar op 6 oktober 2026 voor de getuigen gaf.
"""

from __future__ import annotations

import io
import json
import zipfile

import pytest

from mdconv.errors import ConversionError
from mdconv.sources import eurlex, from_link

TALEN_22 = ["BUL", "CES", "DAN", "DEU", "ENG", "EST", "FIN", "FRA", "GLE", "HRV", "HUN",
            "ITA", "LAV", "LIT", "MLT", "POL", "POR", "SLK", "SLV", "SPA", "SWE", "RON"]


def sparql(rijen: list[tuple[str, str, str]]) -> bytes:
    """Een SPARQL-antwoord met per rij (celex, taal, manifestatietype)."""
    return json.dumps({"results": {"bindings": [
        {"celex": {"value": celex},
         "lang": {"value": f"http://publications.europa.eu/resource/authority/language/{taal}"},
         "type": {"value": soort}}
        for celex, taal, soort in rijen]}}).encode()


class Antwoord:
    def __init__(self, status: int, inhoud: bytes, url: str = ""):
        self.status_code, self.content, self.url = status, inhoud, url
        self.text = inhoud.decode("utf-8", errors="ignore")
        self.apparent_encoding, self.encoding = "utf-8", "utf-8"

    def json(self):
        return json.loads(self.content)


def nep_netwerk(monkeypatch, antwoorden: dict[str, tuple[int, bytes]]):
    """Per URL-deel een vast antwoord (het eerste deel dat past); de rest 404. Telt de aanroepen."""
    aanroepen = []

    def get(url, headers=None, timeout=None, allow_redirects=None, params=None):
        aanroepen.append((url, dict(headers or {}), params))
        for deel, (status, inhoud) in antwoorden.items():
            if deel in url:
                return Antwoord(status, inhoud, url)
        return Antwoord(404, b"", url)

    monkeypatch.setattr(eurlex.net, "documents", lambda: type("S", (), {"get": staticmethod(get)})())
    monkeypatch.setattr(eurlex.net, "decoded_text", lambda r: r.text)
    return aanroepen


def documentverzoeken(aanroepen) -> list[str]:
    return [url for url, _, _ in aanroepen if "webapi/rdf/sparql" not in url]


# --------------------------------------------------------------------------
# M22: een CELEX met een volgnummer tussen haakjes wordt gecodeerd
# --------------------------------------------------------------------------

OPINION = """<?xml version="1.0" encoding="UTF-8"?>
<OPINION><BIB.OPINION><NO.CELEX>62015CV0001(01)</NO.CELEX></BIB.OPINION>
<OPINION.INIT><P>Advies 1/15</P></OPINION.INIT></OPINION>"""


def advies_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("ECR_62015CV0001_01_NL_01.xml", OPINION.encode("utf-8"))
    return buf.getvalue()


def test_een_celex_met_volgnummer_wordt_gecodeerd_en_een_advies_weigert_met_de_ware_reden(monkeypatch):
    # De Cellar antwoordt alleen op de gecodeerde vorm (gemeten in kb WP-92: kaal 404, `%2801%29`
    # 303 naar de zip); het nep-netwerk doet hetzelfde.
    aanroepen = nep_netwerk(monkeypatch, {"62015CV0001%2801%29": (200, advies_zip())})
    vraag = "https://eur-lex.europa.eu/legal-content/NL/TXT/HTML/?uri=CELEX:62015CV0001(01)"
    with pytest.raises(ConversionError) as fout:
        from_link(vraag, "NL")
    assert documentverzoeken(aanroepen) == ["http://publications.europa.eu/resource/celex/62015CV0001%2801%29"]
    # Na de codering is de weigering die van de adviesroute (M22b, genoemd): zij klopt.
    assert "soort OPINION wordt niet ondersteund" in str(fout.value)
    assert "geen Formex-manifestatie" not in str(fout.value)


@pytest.mark.parametrize("celex, gecodeerd", [
    ("62015CV0001(01)", "62015CV0001%2801%29"),
    ("32020D1022(01)", "32020D1022%2801%29"),
    ("02014R0910-20241018", "02014R0910-20241018"),   # het koppelteken blijft
    ("32016R0679", "32016R0679"),
])
def test_elke_cellar_resource_van_een_celex_is_gecodeerd(celex, gecodeerd):
    assert eurlex._celex_url(celex) == f"http://publications.europa.eu/resource/celex/{gecodeerd}"


def test_ook_de_wetgevingsroute_codeert_formex_en_cellar_html(monkeypatch):
    aanroepen = nep_netwerk(monkeypatch, {"webapi/rdf/sparql": (200, sparql([]))})
    with pytest.raises(ConversionError):
        from_link("32020D1022(01)", "NL")
    cellar = [u for u in documentverzoeken(aanroepen) if "publications.europa.eu" in u]
    assert cellar == ["http://publications.europa.eu/resource/celex/32020D1022%2801%29"] * 2
