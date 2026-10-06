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


# --------------------------------------------------------------------------
# M5: een 404 op de Formex van het Hof noemt wat de Cellar wél heeft
# --------------------------------------------------------------------------

INTELIGO = sparql([("62023CJ0654", t, s) for t in TALEN_22 for s in ("fmx4", "xhtml")]
                  + [("62023CJ0654", t, "html") for t in ("NLD", "ELL", "RON")])


@pytest.mark.parametrize("metadata, verwacht", [
    # Inteligo Media (62023CJ0654): Formex in 22 talen, in het Nederlands alleen HTML.
    ((200, INTELIGO), "In het Nederlands heeft de Cellar 62023CJ0654 alleen als html; "
                      "fmx4 is er in 22 van de 24 talen."),
    # Een nieuw arrest dat er in het Nederlands nog niet is.
    ((200, sparql([("62023CJ0654", "FRA", "fmx4"), ("62023CJ0654", "FRA", "xhtml")])),
     "In het Nederlands heeft de Cellar 62023CJ0654 (nog) niet; fmx4 is er in het Frans."),
    # Een document dat nergens als Formex bestaat.
    ((200, sparql([("62023CJ0654", "NLD", "html"), ("62023CJ0654", "FRA", "pdf")])),
     "In het Nederlands heeft de Cellar 62023CJ0654 alleen als html; fmx4 is er in geen enkele taal."),
    # Een tikfout: de metadata kennen het document niet.
    ((200, sparql([])), "De Cellar-metadata kennen 62023CJ0654 niet."),
    # Volgens de metadata is de Nederlandse Formex er wel: dan ligt het aan het verzoek.
    ((200, sparql([("62023CJ0654", "NLD", "fmx4")])),
     "Volgens de Cellar-metadata bestaat 62023CJ0654 in het Nederlands wel als fmx4; "
     "het verzoek kreeg die toch niet."),
    # De metadata zijn niet bereikbaar: dat staat er, geen gok.
    ((500, b""), "Welke vormen de Cellar wél heeft, was niet na te gaan"),
    ((200, b"geen json"), "Welke vormen de Cellar wél heeft, was niet na te gaan"),
])
def test_een_404_op_de_formex_van_het_hof_noemt_wat_de_cellar_wel_heeft(monkeypatch, metadata, verwacht):
    aanroepen = nep_netwerk(monkeypatch, {"resource/celex/": (404, b""), "webapi/rdf/sparql": metadata})
    with pytest.raises(ConversionError) as fout:
        from_link("62023CJ0654", "NL")
    melding = str(fout.value)
    assert melding.startswith("Voor 62023CJ0654 is geen Formex-manifestatie in de Cellar (HTTP 404) in taal NL.")
    assert verwacht in melding
    assert "laatste dagen of weken" not in melding
    assert melding.endswith("Er is geen terugval op HTML of op een andere taal.")
    # Eén documentverzoek; de metadata zijn geen tweede route.
    assert documentverzoeken(aanroepen) == ["http://publications.europa.eu/resource/celex/62023CJ0654"]


def test_op_een_ecli_telt_de_samenvatting_van_het_arrest_niet_mee(monkeypatch):
    # Een ECLI hangt ook aan het werk `62023CJ0654_RES`, met Formex in het Nederlands; dat is
    # de samenvatting, niet het arrest (Cellar, 6 oktober 2026).
    antwoord = sparql([("62023CJ0654", "NLD", "html"), ("62023CJ0654", "FRA", "fmx4"),
                       ("62023CJ0654_RES", "NLD", "fmx4")])
    aanroepen = nep_netwerk(monkeypatch, {"resource/ecli/": (404, b""), "webapi/rdf/sparql": (200, antwoord)})
    with pytest.raises(ConversionError) as fout:
        from_link("ECLI:EU:C:2025:871", "NL")
    assert ("In het Nederlands heeft de Cellar ECLI:EU:C:2025:871 alleen als html; fmx4 is er in het Frans."
            in str(fout.value))
    vraag = [p for url, _, p in aanroepen if "sparql" in url][0]["query"]
    assert 'cdm:case-law_ecli "ECLI:EU:C:2025:871"' in vraag


def test_een_id_dat_geen_celex_of_ecli_is_gaat_niet_naar_de_metadata(monkeypatch):
    aanroepen = nep_netwerk(monkeypatch, {})
    assert eurlex._manifestaties('62023CJ0654" } DROP') is None
    assert aanroepen == []


# --------------------------------------------------------------------------
# M9: een EUR-Lex-foutpagina is een weigering, geen document
# --------------------------------------------------------------------------

# De vorm van de pagina die EUR-Lex op 5 oktober 2026 voor 32004D0411 gaf (kb WP-90, G1 R8),
# ingekort tot het skelet: de portaalpagina met een blok `#errorDocumentView`.
FOUTPAGINA = """<!DOCTYPE html><html lang="en"><head><title>EUR-Lex - CELEX:32004D0411 - EN</title></head>
<body><a href="#">Skip to main content</a><div>My EUR-Lex</div>
<div class="row row-offcanvas" id="errorDocumentView"><div class="col-md-12"><div class="EurlexContent">
<div class="alert alert-warning" role="alert">
    <span class="fa fa-exclamation-circle" aria-hidden="true">&nbsp;</span>
     The requested document does not exist.
</div></div></div></div></body></html>"""

ISLE_OF_MAN = sparql([("32004D0411", t, "pdf") for t in TALEN_22[:21] + ["NLD"]]
                     + [("32004D0411", t, "print") for t in TALEN_22 + ["NLD"]]
                     + [("32004D0411", t, s) for t in ("ENG", "FRA", "HRV") for s in ("fmx4", "xhtml")]
                     + [("32004D0411", t, "html") for t in TALEN_22[:12]])

DOCUMENT = ("<html><body><p>BESCHIKKING VAN DE COMMISSIE</p><p>"
            + "Juridische tekst van de beschikking. " * 10 + "</p></body></html>")


def test_een_foutpagina_van_eur_lex_is_een_weigering_met_de_melding_en_wat_er_wel_is(monkeypatch):
    nep_netwerk(monkeypatch, {"publications.europa.eu/resource/celex/": (404, b""),
                              "eur-lex.europa.eu/legal-content/": (200, FOUTPAGINA.encode()),
                              "webapi/rdf/sparql": (200, ISLE_OF_MAN)})
    with pytest.raises(ConversionError) as fout:
        from_link("https://eur-lex.europa.eu/legal-content/NL/TXT/HTML/?uri=CELEX:32004D0411", "NL")
    melding = str(fout.value)
    assert melding.startswith('EUR-Lex gaf voor CELEX:32004D0411 in taal NL geen document maar een foutpagina '
                              '("The requested document does not exist.").')
    assert ("In het Nederlands heeft de Cellar 32004D0411 alleen als pdf en print; fmx4 is er in het Engels, "
            "Frans en Kroatisch; xhtml is er in het Engels, Frans en Kroatisch; html is er in 12 van de 24 talen."
            in melding)


def test_een_portal_die_niets_geeft_noemt_ook_wat_de_cellar_heeft(monkeypatch):
    # Op 6 oktober 2026 gaf EUR-Lex voor dezelfde twee zes keer HTTP 202, zonder pagina.
    monkeypatch.setattr(eurlex.time, "sleep", lambda s: None)
    nep_netwerk(monkeypatch, {"publications.europa.eu/resource/celex/": (404, b""),
                              "eur-lex.europa.eu/legal-content/": (202, b""),
                              "webapi/rdf/sparql": (200, ISLE_OF_MAN)})
    with pytest.raises(ConversionError) as fout:
        from_link("32004D0411", "NL")
    melding = str(fout.value)
    assert "(status 202)" in melding
    assert "In het Nederlands heeft de Cellar 32004D0411 alleen als pdf en print;" in melding


def test_een_document_van_de_portal_blijft_een_document(monkeypatch):
    nep_netwerk(monkeypatch, {"publications.europa.eu/resource/celex/": (404, b""),
                              "eur-lex.europa.eu/legal-content/": (200, DOCUMENT.encode())})
    document = from_link("32004D0411", "NL")
    assert document.provenance.format == "eurlex-html"
    assert "Juridische tekst van de beschikking." in document.markdown


def test_de_cellar_html_route_vraagt_de_metadata_niets(monkeypatch):
    # Het tegenvoorbeeld (32003D0821, 32001R0045): geen Formex, wel Cellar-HTML. Die route
    # verandert niet en kost geen extra verzoek.
    aanroepen = []

    def get(url, headers=None, timeout=None, allow_redirects=None, params=None):
        aanroepen.append(url)
        if "fmx4" in (headers or {}).get("Accept", ""):
            return Antwoord(404, b"", url)
        return Antwoord(200, DOCUMENT.encode(), url)

    monkeypatch.setattr(eurlex.net, "documents", lambda: type("S", (), {"get": staticmethod(get)})())
    monkeypatch.setattr(eurlex.net, "decoded_text", lambda r: r.text)
    document = from_link("32003D0821", "NL")
    assert document.provenance.format == "eurlex-html"
    assert aanroepen == ["http://publications.europa.eu/resource/celex/32003D0821"] * 2
    assert "Formex niet beschikbaar (HTTP 404); HTML-route gebruikt." in document.provenance.waarschuwingen
    assert "Cellar-HTML-route gebruikt." in document.provenance.waarschuwingen


@pytest.mark.parametrize("html", [
    DOCUMENT,
    # Een document dat de woorden zelf citeert, zonder het blok van de foutpagina.
    "<html><body><p>The requested document does not exist.</p></body></html>",
])
def test_alleen_het_blok_van_de_foutpagina_maakt_een_foutpagina(html):
    assert eurlex._eurlex_foutpagina(html) is None
    assert eurlex._eurlex_foutpagina(FOUTPAGINA) == "The requested document does not exist."
