"""De officiële BWB-XML-route en haar begrensde HTML-terugval."""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from mdconv.errors import ConversionError
from mdconv.sources import from_link, wetten


def manifest(*, begin="2020-01-01", eind="9999-12-31", sha512="0" * 128):
    return f"""<manifest><expression label="expr_1"><metadata>
<datum_inwerkingtreding>{begin}</datum_inwerkingtreding><einddatum>{eind}</einddatum>
</metadata><manifestation label="xml"><metadata><hashcode>{sha512}</hashcode></metadata>
<item label="BWBR0000001.xml"/></manifestation></expression></manifest>""".encode()


def toestand(*, bwb="BWBR0000001", begin="2020-01-01", status="goed",
             artikel_inwerking="2020-01-01"):
    return f"""<toestand bwb-id="{bwb}" inwerkingtreding="{begin}"><wetgeving>
<citeertitel>Testwet</citeertitel><wet-besluit><wettekst>
<artikel status="{status}" inwerking="{artikel_inwerking}"><kop><label>Artikel</label>
<nr>1</nr><titel>Reikwijdte</titel></kop><lid><lidnr>1</lidnr>
<al>Deze wet geldt.</al></lid></artikel></wettekst></wet-besluit>
</wetgeving></toestand>""".encode()


def response(data, url):
    return SimpleNamespace(status_code=200, content=data, url=url)


def test_bwb_xml_precedes_html_and_manifest_hash_is_only_a_note(monkeypatch):
    xml = toestand()
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        return response(manifest(sha512="f" * 128), url) if url.endswith("manifest.xml") else response(xml, url)

    monkeypatch.setattr(wetten.net, "documents", lambda: SimpleNamespace(get=get))
    document = from_link("BWBR0000001/2020-02-01")

    assert len(calls) == 2
    assert calls[0].endswith("/BWBR0000001/manifest.xml")
    assert "# Testwet" in document.markdown
    assert document.provenance.format == "bwb-xml"
    assert document.provenance.geldend_van == "2020-01-01"
    assert document.provenance.extra["xml_sha512_wijkt_af_van_manifest"] is True
    assert document.provenance.extra["xml_sha512_gemeten"] == hashlib.sha512(xml).hexdigest()
    assert any("SHA-512" in melding for melding in document.provenance.waarschuwingen)


def test_expired_article_is_rendered_and_recorded(monkeypatch):
    xml = toestand(status="vervallen", artikel_inwerking="2021-03-04")

    def get(url, **kwargs):
        return response(manifest(), url) if url.endswith("manifest.xml") else response(xml, url)

    monkeypatch.setattr(wetten.net, "documents", lambda: SimpleNamespace(get=get))
    document = from_link("BWBR0000001/2022-01-01")

    assert "[Vervallen per 04-03-2021]" in document.markdown
    assert document.provenance.expired == {"art-1": "2021-03-04"}


def test_not_yet_effective_paragraph_keeps_text_without_new_anchor_unit():
    xml = toestand(status="nogniet", artikel_inwerking="")
    markdown, eenheden, _, _ = wetten.bwb_xml.omzetten(xml)

    assert "1. Deze wet geldt." in markdown
    assert not markdown.split("1. Deze wet geldt.", 1)[0].endswith("- ")
    assert [e.anker for e in eenheden] == ["art-1"]


def test_not_yet_effective_article_is_marked_under_its_heading_and_keeps_its_text():
    """Tekst van een artikel dat nog niet geldt mag nooit als geldend recht lezen."""
    xml = toestand(status="nogniet", artikel_inwerking="")
    markdown = wetten.bwb_xml.omzetten(xml)[0]
    kop, rest = markdown.split("Reikwijdte", 1)[1].split("\n", 1)
    assert rest.lstrip("\n").startswith("[Nog niet in werking getreden.]\n\n1. Deze wet geldt.")


def test_a_goed_article_gets_no_not_yet_in_force_marker():
    assert "Nog niet in werking" not in wetten.bwb_xml.omzetten(toestand())[0]


def test_container_heading_without_label_and_number_is_only_its_title():
    """Een kop met alleen een `<titel>` is die titel, zonder leesteken ervoor.

    De Wet bescherming persoonsgegevens BES (BWBR0028067) heeft een hoofdstuk met
    enkel `<kop><titel>Slotbepalingen</titel></kop>`; `kopregel()` schreef daar
    `## . Slotbepalingen`, en de kennisbank struikelde over een kop die met een
    leesteken begint (kb WP-04, 23 september 2026)."""
    xml = toestand().replace(
        b"<artikel ",
        b'<hoofdstuk status="goed" inwerking="2020-01-01"><kop><titel>Slotbepalingen</titel></kop><artikel ', 1
    ).replace(b"</artikel>", b"</artikel></hoofdstuk>", 1)
    markdown = wetten.bwb_xml.omzetten(xml)[0]
    assert "\n## Slotbepalingen\n" in markdown
    assert ". Slotbepalingen" not in markdown
    # De gewone vorm blijft zoals ze was: label, nummer, punt, titel.
    assert "Artikel 1. Reikwijdte" in markdown


def _artikel(nr):
    return (f'<artikel status="goed" inwerking="2020-01-01"><kop><label>Artikel</label>'
            f'<nr>{nr}</nr></kop><lid><lidnr>1</lidnr><al>Tekst van artikel {nr}.</al></lid></artikel>')


def _paragraaf_1(nr):
    return (f'<paragraaf><kop><label>§</label><nr>1</nr><titel>Eerste paragraaf</titel></kop>'
            f'{_artikel(nr)}</paragraaf>')


def test_a_heading_with_the_number_before_the_label_follows_the_source_order():
    """`<nr>Vierde</nr><label>titel</label>` wordt `Vierde titel`, zoals de bron het zet.

    Het Wetboek van Koophandel telt zijn paragrafen per titel opnieuw en zet het
    rangtelwoord vóór het label: `Eerste Boek`, `Vierde titel`, `Vijfde afdeeling`.
    `kopregel()` schreef altijd eerst het label (`titel Vierde.`), een vorm die het
    profiel van de kennisbank niet kent; titel en boek kregen daar geen anker, en de
    twee keer `§ 1` werd twee keer `par-1` (kb WP-09, klasse G). Een kop met het label
    vóór het nummer, zoals `<label>Vijfde titel</label><nr>A</nr>`, verandert niet."""
    xml = f"""<toestand bwb-id="BWBR0000001" inwerkingtreding="2020-01-01"><wetgeving>
<citeertitel>Testwetboek</citeertitel><wet-besluit><wettekst>
<boek><kop><nr>Tweede</nr><label>Boek</label><titel>Het tweede boek</titel></kop>
<titeldeel><kop><nr>Vierde</nr><label>titel</label><titel>De vierde titel</titel></kop>
{_paragraaf_1("341")}
<afdeling><kop><nr>Vijfde</nr><label>afdeeling</label><titel>De vijfde afdeling</titel></kop>
{_artikel("360")}</afdeling></titeldeel>
<titeldeel><kop><nr>Vijfde</nr><label>titel</label><titel>De vijfde titel</titel></kop>
{_paragraaf_1("378")}</titeldeel>
<titeldeel><kop><label>Vijfde titel</label><nr>A</nr><titel>De ingevoegde titel</titel></kop>
{_artikel("400")}</titeldeel>
</boek></wettekst></wet-besluit></wetgeving></toestand>""".encode()

    markdown, eenheden, onbekend, extra = wetten.bwb_xml.omzetten(xml)

    assert onbekend == {}
    assert "\n## Tweede Boek. Het tweede boek\n" in markdown
    assert "\n### Vierde titel. De vierde titel\n" in markdown
    assert "\n#### Vijfde afdeeling. De vijfde afdeling\n" in markdown
    assert "\n### Vijfde titel. De vijfde titel\n" in markdown
    assert markdown.count("\n#### § 1. Eerste paragraaf\n") == 2
    for omgedraaid in ("Boek Tweede", "titel Vierde", "titel Vijfde", "afdeeling Vijfde"):
        assert omgedraaid not in markdown
    # Label vóór nummer blijft label vóór nummer.
    assert "\n### Vijfde titel A. De ingevoegde titel\n" in markdown
    # De eenheden dragen dezelfde kopregel; de ankers komen uit het nummer en veranderen niet.
    teksten = {e.anker: e.tekst for e in eenheden}
    assert teksten["tit-vierde"] == "Vierde titel. De vierde titel"
    assert teksten["tit-a"] == "Vijfde titel A. De ingevoegde titel"
    # Gevolgd, en gemeld.
    assert extra["omgedraaide_koppen"] == 4
    assert extra["waarschuwingen"] == [
        "De BWB-XML zet 4 keer het nummer vóór het label in een kop ('Tweede Boek', "
        "'Vierde titel', 'Vijfde afdeeling', 'Vijfde titel'); de omzetter volgt die volgorde."]


def test_a_heading_with_the_label_first_is_not_reported():
    markdown, _, _, extra = wetten.bwb_xml.omzetten(toestand())
    assert "Artikel 1. Reikwijdte" in markdown
    assert extra["omgedraaide_koppen"] == 0
    assert extra["waarschuwingen"] == []


def test_the_reversed_heading_warning_travels_with_the_provenance(monkeypatch):
    """De melding van de omzetter komt in `herkomst.waarschuwingen`, en zo in `ophaal.json`."""
    xml = toestand().replace(
        b"<artikel ",
        b'<titeldeel><kop><nr>Vierde</nr><label>titel</label><titel>De vierde titel</titel></kop><artikel ', 1
    ).replace(b"</artikel>", b"</artikel></titeldeel>", 1)

    def get(url, **kwargs):
        return response(manifest(), url) if url.endswith("manifest.xml") else response(xml, url)

    monkeypatch.setattr(wetten.net, "documents", lambda: SimpleNamespace(get=get))
    document = from_link("BWBR0000001/2020-02-01")

    assert "Vierde titel. De vierde titel" in document.markdown
    assert ("De BWB-XML zet 1 keer het nummer vóór het label in een kop ('Vierde titel'); "
            "de omzetter volgt die volgorde.") in document.provenance.waarschuwingen


def in_container(xml: bytes, tag: str, status: str, nr: str = "1", binnen: bytes = b"") -> bytes:
    """Zet het artikel van `toestand()` in een `<tag status=…>` met kop (en eventueel iets ervóór)."""
    kop = f'<{tag} status="{status}"><kop><label>{tag.capitalize()}</label><nr>{nr}</nr><titel>Eerste</titel></kop>'
    return xml.replace(b"<artikel ", kop.encode() + binnen + b"<artikel ", 1).replace(
        b"</artikel>", f"</artikel></{tag}>".encode(), 1)


FIXTURE_BWB = Path(__file__).parent / "fixtures" / "bwb"


def test_considerans_lijst_en_nog_niet_geldende_structuur_geven_de_raw_vorm_van_de_kennisbank():
    """De fixture van kb WP-103 (`tests/fixtures/bwb/README.md`): de kennisbank las deze raw-vorm eerst met
    haar eigen planner, poort en bronlezing (0 bevindingen); de omzetter moet haar byte voor byte schrijven."""
    markdown, eenheden, onbekend, _ = wetten.bwb_xml.omzetten((FIXTURE_BWB / "considerans-nogniet.xml").read_bytes())
    assert markdown == (FIXTURE_BWB / "considerans-nogniet.md").read_text(encoding="utf-8")
    assert not onbekend
    # De koppen van het nog niet geldende deel houden hun eenheid; de leden van een artikel erin niet.
    assert [e.anker for e in eenheden] == [
        "hfd-1", "art-1", "art-1-1", "art-1-1-a", "art-1-1-b", "art-1-2", "hfd-2", "hfd-3", "par-3-1",
        "art-3-1-1", "par-3-2", "art-3-2-1", "art-3-2-2", "hfd-4", "afd-4-4-1", "art-4a", "art-4b",
        "art-4b-a", "art-4b-b", "hfd-5", "art-5"]


def test_deze_plaatje_en_dossierref_geven_de_raw_vorm_van_de_kennisbank():
    """De fixture van kb WP-114 (`tests/fixtures/bwb/README.md`, besluit 11 van haar plan 7): de kennisbank las
    deze raw-vorm eerst met haar eigen planner, poort en bronlezing (0 bevindingen); de omzetter schrijft haar byte
    voor byte, en zijn eenheden zijn precies de ankers die haar planner zet."""
    markdown, eenheden, onbekend, extra = wetten.bwb_xml.omzetten(
        (FIXTURE_BWB / "deze-plaatje-dossierref.xml").read_bytes())
    assert markdown == (FIXTURE_BWB / "deze-plaatje-dossierref.md").read_text(encoding="utf-8")
    assert not onbekend
    assert [e.anker for e in eenheden] == [
        "hfd-1", "art-1", "art-1-a", "art-1-b", "art-1-c", "art-2", "art-2-1", "art-2-2", "art-3", "hfd-2",
        "art-4", "art-4-1", "art-4-2", "art-5"]
    # Elk beeld vastgelegd, ook het plaatje zonder bijschrift; de kennisbank zet daarop `image-omitted`.
    assert [b["naam"] for b in extra["afbeeldingen_weggelaten"]] == ["9001.png", "9002.png", "9003.png", "9004.png"]


def test_considerans_lijst_houdt_haar_nummering_zonder_eenheid():
    """Het Besluit elektronisch procederen (BWBR0044275): `plat()` sloeg `<li.nr>` over, en de vier
    grondslagen onder `Gelet op:` stonden er zonder `a.`–`d.` (kb G8 R1, H7). Nu een lijst zoals elke
    BWB-lijst, zonder eenheid: de aanhef heeft geen artikel."""
    xml = toestand().replace(b"<wettekst>", (
        "<aanhef><considerans><considerans.al>Gelet op:</considerans.al>"
        '<considerans.lijst bevat="grondslag" type="expliciet">'
        "<li><li.nr>a.</li.nr><al>artikel 33 van het Wetboek;</al><meta-data/></li>"
        "<li><li.nr>b.</li.nr><al>artikel 46 van de Uitvoeringswet;</al></li>"
        "</considerans.lijst></considerans></aanhef><wettekst>").encode(), 1)
    markdown, eenheden, _, _ = wetten.bwb_xml.omzetten(xml)
    assert "Gelet op:\n\n- a. artikel 33 van het Wetboek;\n- b. artikel 46 van de Uitvoeringswet;\n\n" in markdown
    assert [e.anker for e in eenheden] == ["art-1", "art-1-1"]


def test_nog_niet_geldend_hoofdstuk_krijgt_kop_melding_en_artikelen_zoals_een_nog_niet_geldend_artikel():
    """Besluit 12 (kb WP-103, M1): tot dan weigerde een `<hoofdstuk status="nogniet">` de hele regeling.
    Nu de kop met eenheid en de melding eronder, en het artikel erin (zonder eigen status) zoals een nog
    niet geldend artikel: melding onder de kop, het lid als platte alinea, geen lideenheid."""
    markdown, eenheden, _, _ = wetten.bwb_xml.omzetten(in_container(toestand(), "hoofdstuk", "nogniet"))
    assert ("## Hoofdstuk 1. Eerste\n\n[Nog niet in werking getreden.]\n\n### Artikel 1. Reikwijdte\n\n"
            "[Nog niet in werking getreden.]\n\n1. Deze wet geldt.") in markdown
    assert [e.anker for e in eenheden] == ["hfd-1", "art-1"]


@pytest.mark.parametrize("tag", ["afdeling", "paragraaf"])
def test_nog_niet_geldende_afdeling_en_paragraaf_volgen_dezelfde_vorm(tag):
    markdown, eenheden, _, _ = wetten.bwb_xml.omzetten(in_container(toestand(), tag, "nogniet"))
    assert "Eerste\n\n[Nog niet in werking getreden.]\n\n### Artikel 1. Reikwijdte\n\n[Nog niet in werking getreden.]" in markdown
    assert [e.anker for e in eenheden][1:] == ["art-1"]


def test_een_geldend_hoofdstuk_geeft_niets_door():
    markdown, eenheden, _, _ = wetten.bwb_xml.omzetten(in_container(toestand(), "hoofdstuk", "goed"))
    assert "Nog niet in werking" not in markdown
    assert [e.anker for e in eenheden] == ["hfd-1", "art-1", "art-1-1"]


def test_structuurtekst_met_redactie_staat_onder_de_kop_in_plaats_van_de_melding():
    """Het Besluit digitale overheid (BWBR0037987), Hoofdstuk 5: geen artikel, alleen de redactieregel."""
    binnen = (b'<structuurtekst><al><redactie type="vervanging">Dit onderdeel is nog niet inwerking getreden'
              b"</redactie></al></structuurtekst>")
    markdown, _, _, _ = wetten.bwb_xml.omzetten(in_container(toestand(), "hoofdstuk", "nogniet", binnen=binnen))
    assert ("## Hoofdstuk 1. Eerste\n\n[Red: Dit onderdeel is nog niet inwerking getreden]\n\n"
            "### Artikel 1. Reikwijdte\n\n[Nog niet in werking getreden.]") in markdown


def test_structuurtekst_buiten_een_nog_niet_geldend_element_is_een_weigering():
    """Niet gemeten: in de 125 BWB-bronnen van de kennisbank alleen onder een nog niet geldend hoofdstuk."""
    binnen = b"<structuurtekst><al>Tekst.</al></structuurtekst>"
    with pytest.raises(ConversionError, match="structuurtekst"):
        wetten.bwb_xml.omzetten(in_container(toestand(), "hoofdstuk", "goed", binnen=binnen))


@pytest.mark.parametrize("tag", ["deel", "titeldeel", "boek"])
def test_status_nogniet_op_een_ander_structuurelement_blijft_een_weigering(tag):
    """Besluit 12 is gemeten op een hoofdstuk, afdeling en paragraaf; elders weigeren we liever dan te raden."""
    with pytest.raises(ConversionError, match="nogniet"):
        wetten.bwb_xml.omzetten(in_container(toestand(), tag, "nogniet"))


def test_status_nogniet_op_een_lid_blijft_een_weigering():
    xml = toestand().replace(b"<lid>", b'<lid status="nogniet">', 1)
    with pytest.raises(ConversionError, match="nogniet"):
        wetten.bwb_xml.omzetten(xml)


def test_een_vervallen_artikel_in_een_nog_niet_geldend_onderdeel_wordt_geweigerd():
    xml = in_container(toestand(status="vervallen", artikel_inwerking="2021-03-04"), "hoofdstuk", "nogniet")
    with pytest.raises(ConversionError, match="nog niet geldt"):
        wetten.bwb_xml.omzetten(xml)


def test_withdrawn_regulation_uses_last_version(monkeypatch):
    xml = toestand()

    def get(url, **kwargs):
        return response(manifest(eind="2021-12-31"), url) if url.endswith("manifest.xml") else response(xml, url)

    monkeypatch.setattr(wetten.net, "documents", lambda: SimpleNamespace(get=get))
    document = from_link("BWBR0000001/2022-01-01")

    assert document.provenance.ingetrokken_op == "2021-12-31"
    assert "ingetrokken per 2021-12-31" in document.source


def test_identity_and_selected_start_date_are_hard_requirements(monkeypatch):
    verkeerd = toestand(bwb="BWBR9999999")

    def get(url, **kwargs):
        return response(manifest(), url) if url.endswith("manifest.xml") else response(verkeerd, url)

    monkeypatch.setattr(wetten.net, "documents", lambda: SimpleNamespace(get=get))
    with pytest.raises(ConversionError, match="BWBR9999999"):
        from_link("BWBR0000001/2020-02-01")


def regeling(*, bwb="BWBR0000001", begin="2020-01-01"):
    """Een ministeriële regeling: <regeling> met <regeling-tekst>/<regeling-sluiting>
    in plaats van de <wet-besluit>-vorm met <wettekst>/<wetsluiting>."""
    return f"""<toestand bwb-id="{bwb}" inwerkingtreding="{begin}"><wetgeving>
<citeertitel>Testregeling</citeertitel><regeling><aanhef><al>Gelet op artikel 1.</al></aanhef>
<regeling-tekst><artikel status="goed" inwerking="{begin}"><kop><label>Artikel</label>
<nr>1</nr><titel>Reikwijdte</titel></kop><lid><lidnr>1</lidnr>
<al>Deze regeling geldt.</al></lid></artikel></regeling-tekst>
<regeling-sluiting><al>Aldus vastgesteld.</al></regeling-sluiting>
</regeling></wetgeving></toestand>""".encode()


def test_regeling_route_is_converted_like_wet_besluit(monkeypatch):
    xml = regeling()

    def get(url, **kwargs):
        return response(manifest(), url) if url.endswith("manifest.xml") else response(xml, url)

    monkeypatch.setattr(wetten.net, "documents", lambda: SimpleNamespace(get=get))
    document = from_link("BWBR0000001/2020-02-01")

    assert "# Testregeling" in document.markdown
    assert "Reikwijdte" in document.markdown
    assert "Deze regeling geldt." in document.markdown
    assert "Aldus vastgesteld." in document.markdown
    assert document.provenance.koppen_bron == 1


def test_unknown_top_level_element_under_wetgeving_is_refused_not_flattened():
    """Vroeger viel <regeling> hier stil in plat(); nu geldt dat voor elk
    onbekend hoofdelement direct onder <wetgeving>, niet alleen <regeling>.

    Tot 25 september 2026 stond hier <circulaire> als voorbeeld; dat is sinds de
    nadere regel NR/REG-1829 (BWBR0041321) een bekend hoofdelement. Een verzonnen
    naam houdt de grendel zelf vast."""
    xml = toestand().replace(b"<wet-besluit>", b"<verdragstekst>").replace(b"</wet-besluit>", b"</verdragstekst>")

    with pytest.raises(ConversionError, match="verdragstekst"):
        wetten.bwb_xml.omzetten(xml)


def test_zero_headings_with_source_articles_is_refused(monkeypatch):
    """Goedkope grendel: als de XML <artikel>-elementen bevat maar de omzetting
    nul structuurkoppen geeft, is dat een teken dat er ergens stil is platgeslagen."""
    xml = toestand()
    echte_omzetten = wetten.bwb_xml.omzetten

    def lege_omzetting(data):
        markdown, eenheden, onbekend, extra = echte_omzetten(data)
        return markdown, [], onbekend, extra

    monkeypatch.setattr(wetten.bwb_xml, "omzetten", lege_omzetting)

    def get(url, **kwargs):
        return response(manifest(), url) if url.endswith("manifest.xml") else response(xml, url)

    monkeypatch.setattr(wetten.net, "documents", lambda: SimpleNamespace(get=get))
    with pytest.raises(ConversionError, match="structuurkop"):
        from_link("BWBR0000001/2020-02-01")


def test_bijlage_divisie_preserves_its_title_table_and_footnote():
    xml = b"""<toestand bwb-id="BWBR0000001" inwerkingtreding="2020-01-01"><wetgeving>
<citeertitel>Testwet</citeertitel><bijlage><kop><label>Bijlage</label><nr>1</nr></kop>
<divisie><kop><titel>Bijlage bij artikel 1</titel></kop>
<table><tgroup cols="1"><colspec colname="c1"/><tbody><row><entry colname="c1">
<al>Waarde<sup>1</sup></al></entry></row></tbody></tgroup></table>
<al><sup>1</sup>De tabelnoot.</al></divisie></bijlage></wetgeving></toestand>"""

    markdown, _, onbekend, _ = wetten.bwb_xml.omzetten(xml)

    assert "Bijlage bij artikel 1" in markdown
    assert "Waarde[^annex-1-1]" in markdown
    assert "[^annex-1-1]: De tabelnoot." in markdown
    assert onbekend == {}


def test_tussenkop_between_two_variants_of_an_article_stays_an_italic_paragraph():
    """Artikel 8:36c Awb staat twee keer in de toestand (digitaal procederen en op papier);
    een `<tussenkop kopopmaak="cur">` scheidt ze. Geen kop en geen eenheid: dat zou een
    tweede `art-8-36c` geven."""
    xml = b"""<toestand bwb-id="BWBR0000001" inwerkingtreding="2020-01-01"><wetgeving>
<citeertitel>Testwet</citeertitel><wet-besluit><wettekst>
<artikel><kop><label>Artikel</label><nr>8:36c</nr></kop>
<lid><lidnr>1</lidnr><al>Digitale variant.</al></lid>
<al><redactie type="extra">Voor overige gevallen luidt het artikel als volgt:</redactie></al>
<tussenkop kopopmaak="cur">Artikel 8:36c.</tussenkop>
<lid><lidnr>1</lidnr><al>Papieren variant.</al></lid>
</artikel></wettekst></wet-besluit></wetgeving></toestand>"""

    markdown, eenheden, onbekend, _ = wetten.bwb_xml.omzetten(xml)

    assert onbekend == {}
    assert "\n\n*Artikel 8:36c.*\n\n" in markdown
    assert markdown.index("Digitale variant.") < markdown.index("*Artikel 8:36c.*") < markdown.index("Papieren variant.")
    assert sum("Artikel 8:36c" in regel for regel in markdown.splitlines() if regel.startswith("#")) == 1
    assert [e.anker for e in eenheden if e.soort == "artikel"] == ["art-8-36c"]


def test_articles_inside_a_divisie_of_a_bijlage_get_headings_and_anchors():
    """Bijlage 2 Awb (Bevoegdheidsregeling) deelt twaalf artikelen in vier divisies in;
    de divisiekop blijft een alinea, het artikel krijgt kop en citeeranker."""
    xml = b"""<toestand bwb-id="BWBR0000001" inwerkingtreding="2020-01-01"><wetgeving>
<citeertitel>Testwet</citeertitel><bijlage><kop><label>Bijlage</label><nr>2</nr>
<titel>Bevoegdheidsregeling</titel></kop>
<divisie><kop><label>Hoofdstuk</label><nr>1</nr><titel>Van beroep uitgezonderde besluiten</titel></kop>
<artikel><kop><label>Artikel</label><nr>1</nr><titel>Geen beroep</titel></kop>
<al>Tegen een besluit kan geen beroep worden ingesteld.</al>
<lijst><li><li.nr>a.</li.nr><al>artikel 38;</al></li></lijst></artikel></divisie>
</bijlage></wetgeving></toestand>"""

    markdown, eenheden, onbekend, _ = wetten.bwb_xml.omzetten(xml)

    assert onbekend == {}
    assert "\n\nHoofdstuk 1. Van beroep uitgezonderde besluiten\n\n" in markdown
    assert "### Artikel 1. Geen beroep" in markdown
    ankers = [e.anker for e in eenheden]
    assert "annex-2-art-1" in ankers
    assert "annex-2-art-1-a" in ankers


def test_html_fallback_labels_a_resolved_url_without_a_version_date(monkeypatch):
    html = """<html><head><meta name="dcterms:title" content="Testwet"></head><body>
<div id="regeling"><h1>Testwet</h1><div class="wetgeving"><p>""" + (
        "Juridische tekst. " * 10
    ) + "</p></div></div></body></html>"

    def get(url, **kwargs):
        if url.endswith("manifest.xml"):
            return SimpleNamespace(status_code=404, content=b"", url=url)
        return SimpleNamespace(status_code=200, text=html, url="https://wetten.overheid.nl/BWBR0000001")

    monkeypatch.setattr(wetten.net, "documents", lambda: SimpleNamespace(get=get))
    monkeypatch.setattr(wetten.net, "decoded_text", lambda r: r.text)

    document = from_link("BWBR0000001")

    assert "BWBR0000001" in document.source


def test_unavailable_xml_falls_back_to_html_with_warning(monkeypatch):
    html = """<html><head><meta name="dcterms:title" content="Testwet"></head><body>
<div id="regeling"><h1>Testwet</h1><div class="wetgeving"><p>""" + (
        "Juridische tekst. " * 10
    ) + "</p></div></div></body></html>"
    calls = []

    def get(url, **kwargs):
        calls.append(url)
        if url.endswith("manifest.xml"):
            return SimpleNamespace(status_code=404, content=b"", url=url)
        return SimpleNamespace(status_code=200, text=html, url="https://wetten.overheid.nl/BWBR0000001/2020-01-01")

    monkeypatch.setattr(wetten.net, "documents", lambda: SimpleNamespace(get=get))
    monkeypatch.setattr(wetten.net, "decoded_text", lambda r: r.text)
    document = from_link("BWBR0000001")

    assert len(calls) == 2
    assert document.provenance.format == "wetten-nl"
    assert any("HTML-route" in melding for melding in document.provenance.waarschuwingen)


# ---------- <noot> binnen een alinea (kb WP-13, klasse 1) ----------

def noot_toestand(artikeltekst: str, bijlage: str = "") -> bytes:
    """Artikel 1.3 van de Regeling ggz en fz 2026 (BWBR0051654), ingekort."""
    return f"""<toestand bwb-id="BWBR0051654" inwerkingtreding="2026-01-01"><wetgeving>
<citeertitel>Regeling ggz en fz</citeertitel><regeling><regeling-tekst>
<artikel><kop><label>Artikel</label><nr>1.3</nr><titel>Reikwijdte</titel></kop>
{artikeltekst}</artikel></regeling-tekst>{bijlage}</regeling>
</wetgeving></toestand>""".encode()


NOOT_AL = ("<al>voor zover voornoemde categorieën personen handelingen"
           '<noot id="n1" type="voet"><noot.nr>1</noot.nr><noot.al>Het betreft hier de handelingen '
           'bedoeld in <extref doc="x">artikel 1</extref> van de Wmg.</noot.al></noot> of werkzaamheden'
           '<noot id="n2" type="voet"><noot.nr>2</noot.nr><noot.al>Het betreft hier de werkzaamheden.'
           "</noot.al></noot> op het terrein van geneeskunst verrichten.</al>")


def test_noot_in_een_alinea_wordt_een_native_noot_onder_haar_blok():
    """De marker staat waar de noot staat; de definitie direct onder dat blok, niet
    aan het eind van het document (daar las ze als tekst van de laatste bijlage)."""
    bijlage = "<bijlage><kop><label>Bijlage</label><nr>1</nr><titel>Zorglabels</titel></kop><al>Lijst.</al></bijlage>"
    markdown, _, onbekend, extra = wetten.bwb_xml.omzetten(noot_toestand(NOOT_AL, bijlage))

    assert onbekend == {}
    assert extra["noten"] == 2
    assert ("voor zover voornoemde categorieën personen handelingen[^1] of werkzaamheden[^2] "
            "op het terrein van geneeskunst verrichten.") in markdown
    blokken = markdown.split("\n\n")
    alinea = next(i for i, b in enumerate(blokken) if "handelingen[^1]" in b)
    assert blokken[alinea + 1] == ("[^1]: Het betreft hier de handelingen bedoeld in artikel 1 van de Wmg.\n"
                                   "[^2]: Het betreft hier de werkzaamheden.")
    assert markdown.rstrip().endswith("Lijst.")


def test_noot_in_een_lijst_komt_onder_de_hele_lijst():
    """NR/REG-1829 (BWBR0041321) zet een noot in een onderdeel; midden in de lijst
    zou de definitie de lijst breken."""
    lijst = ('<lijst type="expliciet"><li><li.nr>a.</li.nr><al>DSM diagnose'
             '<noot id="n2" type="voet"><noot.nr>2</noot.nr><noot.al>Veertien hoofdgroepen.</noot.al></noot>'
             ' aantal minuten</al></li><li><li.nr>b.</li.nr><al>afspraaknummer</al></li></lijst>')
    markdown, _, _, _ = wetten.bwb_xml.omzetten(noot_toestand(f"<al>Aanhef:</al>{lijst}"))

    assert "- a. DSM diagnose[^2] aantal minuten\n- b. afspraaknummer\n\n[^2]: Veertien hoofdgroepen." in markdown


def test_noot_in_een_bijlage_draagt_de_reeks_van_die_bijlage():
    bijlage = ('<bijlage><kop><label>Bijlage</label><nr>2</nr><titel>Types</titel></kop>'
               '<al>Zie het instrument<noot id="n9" type="voet"><noot.nr>1</noot.nr>'
               "<noot.al>Versie 2026.</noot.al></noot>.</al></bijlage>")
    markdown, _, _, _ = wetten.bwb_xml.omzetten(noot_toestand("<al>Tekst.</al>", bijlage))

    assert "Zie het instrument[^annex-2-1]." in markdown
    assert "[^annex-2-1]: Versie 2026." in markdown


@pytest.mark.parametrize("noot, melding", [
    ('<noot type="eind"><noot.nr>1</noot.nr><noot.al>x</noot.al></noot>', "type 'eind'"),
    ('<noot type="voet"><noot.al>x</noot.al></noot>', "nummer of zijn tekst"),
    ('<noot type="voet"><noot.nr>1</noot.nr><noot.al> </noot.al></noot>', "nummer of zijn tekst"),
    ('<noot type="voet"><noot.nr>1*</noot.nr><noot.al>x</noot.al></noot>', "geen label"),
    ('<noot type="voet"><noot.nr>1</noot.nr><noot.al>x</noot.al><tabel/></noot>', "tabel"),
    ('<noot type="voet"><noot.nr>1</noot.nr><noot.al>x</noot.al></noot>'
     '<noot type="voet"><noot.nr>1</noot.nr><noot.al>y</noot.al></noot>', "hetzelfde label"),
])
def test_noot_die_niet_de_gemeten_vorm_heeft_wordt_geweigerd(noot, melding):
    with pytest.raises(ConversionError, match=melding):
        wetten.bwb_xml.omzetten(noot_toestand(f"<al>Tekst{noot} verder.</al>"))


@pytest.mark.parametrize("plek", ["lidnr", "nr"])
def test_noot_in_een_nummer_wordt_geweigerd(plek):
    """Een noot in een lidnummer werd `- 1[^1]`, en het lidanker stil `art-1-3-11`."""
    noot = '<noot type="voet"><noot.nr>1</noot.nr><noot.al>x</noot.al></noot>'
    if plek == "lidnr":
        xml = noot_toestand(f"<lid><lidnr>1{noot}</lidnr><al>Tekst.</al></lid>")
    else:
        xml = noot_toestand("<al>Tekst.</al>").replace(b"<nr>1.3</nr>", f"<nr>1.3{noot}</nr>".encode())
    with pytest.raises(ConversionError, match=f"<{plek}>"):
        wetten.bwb_xml.omzetten(xml)


# ---------- <circulaire> als hoofdelement (kb WP-13, klasse 2) ----------

def circulaire(inhoud: str) -> bytes:
    """De vorm van NR/REG-1829 (BWBR0041321), ingekort."""
    return f"""<toestand bwb-id="BWBR0041321" inwerkingtreding="2019-04-15"><wetgeving>
<intitule>Nadere regel</intitule><citeertitel>Nadere regel NR/REG-1829</citeertitel>
<circulaire><circulaire-tekst>
<tekst status="goed"><al>Ingevolge artikel 62 van de Wmg stelt de NZa vast:</al></tekst>
{inhoud}
</circulaire-tekst><circulaire-sluiting status="goed"><ondertekening>
<organisatie>de Nederlandse Zorgautoriteit,</organisatie><functie>voorzitter</functie>
</ondertekening></circulaire-sluiting></circulaire>
</wetgeving></toestand>""".encode()


DIVISIE = """<circulaire.divisie status="goed"><kop><nr status="officieel">2</nr>
<titel status="officieel">Doel</titel></kop><tekst status="goed"><al>De gegevens dienen:</al>
<lijst type="expliciet" nr-sluiting="."><li><li.nr>a.</li.nr><al>de taken van de NZa;</al></li>
<li><li.nr>b.</li.nr><al>de informatie aan VWS.</al></li></lijst>
<tussenkop>Behandeling:</tussenkop><al>Slot.</al></tekst></circulaire.divisie>"""


def test_circulaire_heeft_de_vorm_van_een_regeling_met_divisies_als_kop_zonder_eenheid():
    """De divisie heet in de bron geen artikel; de omzetter maakt er dus ook geen
    artikelanker van, en ook de onderdelen a. en b. krijgen er geen."""
    markdown, eenheden, onbekend, _ = wetten.bwb_xml.omzetten(circulaire(DIVISIE))

    assert onbekend == {}
    assert eenheden == []
    assert markdown.rstrip("\n").split("\n\n") == [
        "# Nadere regel NR/REG-1829",
        "Nadere regel",
        "Ingevolge artikel 62 van de Wmg stelt de NZa vast:",
        "## 2. Doel",
        "De gegevens dienen:",
        "- a. de taken van de NZa;\n- b. de informatie aan VWS.",
        "Behandeling:",
        "Slot.",
        # Een ondertekening is één regel (kb WP-43); tot dan stond elk kind op een eigen regel.
        "de Nederlandse Zorgautoriteit, voorzitter",
    ]


def test_onbekend_element_in_een_circulaire_blijft_een_weigering():
    # Tot kb WP-114 stond hier `<plaatje>schema</plaatje>`; een plaatje direct in een blok heeft nu een
    # vorm (en een plaatje met eigen tekst een eigen weigering, zie onder). De test gaat over een element
    # zonder behandeling, dus nu een element dat de BWB-route niet kent.
    xml = circulaire(DIVISIE.replace("<tussenkop>Behandeling:</tussenkop>",
                                     "<kader>schema</kader>"))
    with pytest.raises(ConversionError, match="blok:kader"):
        wetten.bwb_xml.omzetten(xml)


def test_onderdelen_van_een_nog_niet_geldend_lid_staan_ingesprongen_onder_het_lid():
    """Artikel 3.1.3 Wlz (BWBR0035917): plat geschreven hingen de onderdelen a. en b. in de
    kennisbank aan het artikel (`art-3-1-3-a`). Ingesprongen, zoals onder een geldend lid,
    en nog steeds zonder lidanker (T3-F1, kb WP-19 en WP-20, besluit 8)."""
    xml = toestand(status="nogniet", artikel_inwerking="").replace(
        b"<al>Deze wet geldt.</al></lid>",
        b"<al>Deze wet geldt, voor zover:</al><lijst><li><li.nr>a.</li.nr><al>het past, en</al></li>"
        b"<li><li.nr>b.</li.nr><al>het mag.</al></li></lijst></lid>"
        b"<lid><lidnr>2</lidnr><al>Tweede lid.</al></lid>")
    markdown, eenheden, _, _ = wetten.bwb_xml.omzetten(xml)
    assert ("[Nog niet in werking getreden.]\n\n1. Deze wet geldt, voor zover:\n\n"
            "  - a. het past, en\n  - b. het mag.\n\n2. Tweede lid.") in markdown
    assert [e.anker for e in eenheden] == ["art-1"]


def test_een_artikelnummer_in_het_label_zonder_nr_is_het_nummer():
    """De Wet RO (BWBR0001830) schrijft `<label>Artikel 11a</label>` zonder `<nr>`; de
    omzetter gaf twee keer het lege anker `art-` uit en de kennisbank weigerde het
    zijbestand (T3-F3, kb WP-20)."""
    xml = toestand().replace(b"<label>Artikel</label>\n<nr>1</nr>", b"<label>Artikel 11a</label>")
    markdown, eenheden, _, _ = wetten.bwb_xml.omzetten(xml)
    assert "\n## Artikel 11a. Reikwijdte\n" in markdown
    assert [e.anker for e in eenheden] == ["art-11a", "art-11a-1"]


def test_een_artikel_zonder_nummer_in_nr_of_label_is_een_weigering():
    xml = toestand().replace(b"<label>Artikel</label>\n<nr>1</nr>", b"<label>Artikel</label>")
    with pytest.raises(ConversionError, match="zonder nummer in het label"):
        wetten.bwb_xml.omzetten(xml)


def test_een_leeg_ankersegment_van_een_artikel_is_een_weigering_van_de_omzetter_zelf():
    """Gemeten over de 55 BWB-bronnen van de kennisbank: alleen de twee `art-` van de Wet
    RO. Een hoofdstuk met alleen een titel (`hfd-`, Wbp BES) blijft zoals het in clean/ staat."""
    u = wetten.bwb_xml._BwbUitvoer()
    u.eenheid("hfd-", "hoofdstuk", "Slotbepalingen")
    with pytest.raises(ConversionError, match="leeg ankersegment"):
        u.eenheid("art-", "artikel", "Artikel")
    with pytest.raises(ConversionError, match="leeg ankersegment"):
        u.eenheid("art-1-", "lid", "1")


def test_een_plaatje_wordt_weggelaten_met_melding_en_het_bijschrift_blijft():
    """Wet BIG (BWBR0006251, één plaatje in een bijlage) en Opiumwet (BWBR0001941, elf: in
    een divisie en in een tabelcel) weigerden op `inhoud:plaatje` (T3-F16, kb WP-20)."""
    xml = toestand().replace(
        b"</artikel></wettekst>",
        b"</artikel></wettekst></wet-besluit><bijlage><kop><label>Bijlage</label><nr>1</nr></kop>"
        b"<al>Figuur 1 geeft de opbouw weer.</al>"
        b'<plaatje><illustratie id="272866" alt="Figuur 1" breedte="740" hoogte="436" formaat="png" naam="272866.png"/>'
        b'<bijschrift locatie="boven">Figuur 1</bijschrift></plaatje>'
        b'<table><tgroup cols="2"><colspec colname="c1"/><colspec colname="c2"/><tbody><row>'
        b'<entry colname="c1"><plaatje><illustratie id="1" naam="1.png" breedte="10" hoogte="10" formaat="png"/></plaatje></entry>'
        b'<entry colname="c2"><al>Stof</al></entry></row></tbody></tgroup></table>'
        b"</bijlage><wet-besluit><wettekst></wettekst>")
    markdown, eenheden, onbekend, extra = wetten.bwb_xml.omzetten(xml)
    assert "Figuur 1 geeft de opbouw weer.\n\nFiguur 1\n\n" in markdown
    assert "|  | Stof |" in markdown
    assert "272866" not in markdown and "![" not in markdown
    assert [b["naam"] for b in extra["afbeeldingen_weggelaten"]] == ["272866.png", "1.png"]
    assert extra["waarschuwingen"] == [
        "2 afbeeldingen uit de BWB-XML niet overgenomen; de tekst eromheen en een bijschrift "
        "staan er wel: 272866.png, 1.png."]
    assert not onbekend


# ---------- BWB-constructies van kb WP-43 (T6-F3, T6-F4 en de vier klassen van kb WP-30) ----------

def wet(artikel: str = "<al>Tekst.</al>", bijlage: str = "", sluiting: str = "") -> bytes:
    return f"""<toestand bwb-id="BWBR0000001" inwerkingtreding="2020-01-01"><wetgeving>
<citeertitel>Testregeling</citeertitel><regeling><regeling-tekst>
<artikel><kop><label>Artikel</label><nr>1</nr></kop>{artikel}</artikel>
</regeling-tekst>{sluiting}{bijlage}</regeling></wetgeving></toestand>""".encode()


def test_afk_is_gewone_lopende_tekst():
    """Wet medische hulpmiddelen (BWBR0042755): een aangehaalde aanduiding in `<afk>`."""
    markdown, _, _, _ = wetten.bwb_xml.omzetten(wet(
        "<al>Wat in <afk>artikel 14 van de Wet op de medische hulpmiddelen</afk> voor «x» staat.</al>"))
    assert "Wat in artikel 14 van de Wet op de medische hulpmiddelen voor «x» staat." in markdown


@pytest.mark.parametrize("teken", ["−", "○", "□"])
def test_lijsttekens_min_cirkel_en_vierkant_geven_geen_anker(teken):
    """Regeling register onderwijsdeelnemers (BWBR0043632) en Regeling Bibob-formulieren 2024
    (BWBR0049314): `nummer_anker()` maakte van deze tekens een leeg ankersegment."""
    bijlage = (f'<bijlage><kop><label>Bijlage</label><nr>1</nr></kop><lijst><li><li.nr>{teken}</li.nr>'
               f'<al>een gegeven</al></li><li><li.nr>{teken}</li.nr><al>nog een</al></li></lijst></bijlage>')
    markdown, eenheden, _, _ = wetten.bwb_xml.omzetten(wet(bijlage=bijlage))
    assert f"- {teken} een gegeven\n- {teken} nog een" in markdown
    assert [e.anker for e in eenheden] == ["art-1", "annex-1"]


def test_sup_zonder_definitie_in_de_bijlage_is_een_macht():
    """Archiefregeling (BWBR0027041): `kg/m<sup>3</sup>` zonder enige noot werd `[^3]`."""
    bijlage = ("<bijlage><kop><label>Bijlage</label><nr>2</nr></kop>"
               "<al>Minimaal 120 g/m<sup>2</sup> papier.</al></bijlage>")
    markdown, _, _, _ = wetten.bwb_xml.omzetten(wet("<al>Beton van 625 kg/m<sup>3</sup>.</al>", bijlage))
    assert "Beton van 625 kg/m^3^." in markdown
    assert "Minimaal 120 g/m^2^ papier." in markdown
    assert "[^" not in markdown


def test_sup_met_definitie_in_dezelfde_bijlage_blijft_een_noot_en_een_macht_ernaast_niet():
    """De marker staat vóór zijn definitie; een macht met een ander nummer is geen noot, en een
    definitie in een andere bijlage telt niet."""
    bijlage = ("<bijlage><kop><label>Bijlage</label><nr>1</nr></kop>"
               "<al>Waarde<sup>1</sup> per m<sup>2</sup>.</al><al><sup>1</sup>De noot.</al></bijlage>"
               "<bijlage><kop><label>Bijlage</label><nr>2</nr></kop><al>Ook m<sup>1</sup>.</al></bijlage>")
    markdown, _, _, _ = wetten.bwb_xml.omzetten(wet(bijlage=bijlage))
    assert "Waarde[^annex-1-1] per m^2^." in markdown
    assert "[^annex-1-1]: De noot." in markdown
    assert "Ook m^1^." in markdown


def test_tabeltitel_staat_als_alinea_boven_de_tabel():
    """Besluit verplichte politiegegevens (BWBR0032083): zes `<table><title>` vielen weg."""
    tabel = ('<table><title>Herleidbaarheidsinformatie</title><tgroup cols="1"><colspec colname="c1"/>'
             '<tbody><row><entry colname="c1"><al>Open bron</al></entry></row></tbody></tgroup></table>')
    markdown, _, _, _ = wetten.bwb_xml.omzetten(wet(bijlage=f"<bijlage><kop><label>Bijlage</label><nr>1</nr></kop>{tabel}</bijlage>"))
    blokken = markdown.split("\n\n")
    titel = blokken.index("Herleidbaarheidsinformatie")
    assert blokken[titel + 1].startswith("|")
    assert "Open bron" in blokken[titel + 1]


def test_ander_kind_van_een_tabel_is_een_weigering():
    tabel = ('<table><tfoot>x</tfoot><tgroup cols="1"><colspec colname="c1"/>'
             '<tbody><row><entry colname="c1"><al>a</al></entry></row></tbody></tgroup></table>')
    with pytest.raises(ConversionError, match="table:tfoot"):
        wetten.bwb_xml.omzetten(wet(tabel))


def test_subtitel_van_een_bijlage_staat_onder_de_kop():
    """Besluit burgerservicenummer (BWBR0022829) en Besluit bpg BES (BWBR0028622)."""
    bijlage = ("<bijlage><kop><label>Bijlage</label><nr>I</nr><titel>bij artikel 3</titel>"
               "<subtitel>Algemene gegevens</subtitel></kop><al>Lijst.</al></bijlage>")
    markdown, eenheden, _, _ = wetten.bwb_xml.omzetten(wet(bijlage=bijlage))
    assert "## Bijlage I. bij artikel 3\n\nAlgemene gegevens\n\nLijst." in markdown
    assert eenheden[-1].tekst == "Bijlage I. bij artikel 3"


def test_onbekend_kind_van_een_kop_is_een_weigering():
    xml = wet().replace(b"<nr>1</nr></kop>", b"<nr>1</nr><opschrift>x</opschrift></kop>")
    with pytest.raises(ConversionError, match="kop:opschrift"):
        wetten.bwb_xml.omzetten(xml)


def test_ondertekening_is_een_regel_met_de_losse_tekst_ertussen():
    """BWBR0015808, BWBR0022835, BWBR0024926: `De` en ` van ` vielen weg (kb WP-30)."""
    sluiting = ("<regeling-sluiting><ondertekening>De <functie>Minister</functie> van "
                '<organisatie afkorting="OCW">Onderwijs, Cultuur en Wetenschap</organisatie>, '
                "<naam><voornaam>R.H.A.</voornaam><achternaam>Plasterk</achternaam></naam>"
                "</ondertekening></regeling-sluiting>")
    markdown, _, _, _ = wetten.bwb_xml.omzetten(wet(sluiting=sluiting))
    assert "\n\nDe Minister van Onderwijs, Cultuur en Wetenschap, R.H.A. Plasterk\n" in markdown


def test_ondertekening_zonder_losse_tekst_houdt_de_delen_uit_elkaar():
    sluiting = ("<regeling-sluiting><ondertekening><functie>De Minister van Justitie</functie>"
                "<naam><achternaam>Donner</achternaam></naam></ondertekening></regeling-sluiting>")
    markdown, _, _, _ = wetten.bwb_xml.omzetten(wet(sluiting=sluiting))
    assert "De Minister van Justitie Donner" in markdown


def test_onbekend_kind_van_een_ondertekening_blijft_een_weigering():
    sluiting = "<regeling-sluiting><ondertekening><handtekening>x</handtekening></ondertekening></regeling-sluiting>"
    with pytest.raises(ConversionError, match="inline:handtekening"):
        wetten.bwb_xml.omzetten(wet(sluiting=sluiting))


@pytest.mark.parametrize("bron, verwacht", [
    ('AGB-code <nadruk type="cur">zorgverlener </nadruk>die', "AGB-code *zorgverlener* die"),
    ('de<nadruk type="vet"> kern</nadruk>zaak', "de **kern**zaak"),
    ('een<nadruk type="cur"> </nadruk>woord', "een woord"),
    ('<nadruk type="cur">cursief</nadruk>.', "*cursief*."),
])
def test_witruimte_aan_de_rand_van_een_nadruk_blijft_buiten_de_markering(bron, verwacht):
    """Regeling ggz en fz 2026 (BWBR0051654): `zorgverlener </nadruk>die` werd `zorgverlenerdie`."""
    markdown, _, _, _ = wetten.bwb_xml.omzetten(wet(f"<al>{bron}</al>"))
    assert verwacht in markdown


# ---------- `<deze>`, `<dossierref>` en `<plaatje>` in lijst en blok (kb WP-114, T7-F1, T11-F1, T11-F2) ----------

PLAATJE = ('<plaatje><illustratie id="{id}" naam="{id}.png" breedte="80" hoogte="80" formaat="png"/>'
           '{bijschrift}</plaatje>')


def plaatje(id_: str, bijschrift: str = "") -> str:
    return PLAATJE.format(id=id_, bijschrift=f"<bijschrift>{bijschrift}</bijschrift>" if bijschrift else "")


def test_deze_in_een_mandaatondertekening_is_tekst_op_een_regel():
    """`inline:deze` hield zes regelingen in twee bevestigingstests van de kennisbank buiten de deur (T7-F1),
    en de getuigen BWBR0051828, BWBR0052467 en BWBR0052557. Ook zonder witruimte tussen de delen een spatie."""
    for tussen in (" ", ""):
        sluiting = ("<regeling-sluiting><ondertekening>"
                    f"<functie>De Minister van Financiën,</functie>{tussen}<deze>namens deze,</deze>{tussen}"
                    f"<functie>de secretaris-generaal,</functie>{tussen}"
                    "<naam><voornaam>A.</voornaam><achternaam>Proef</achternaam></naam>"
                    "</ondertekening></regeling-sluiting>")
        markdown, eenheden, onbekend, _ = wetten.bwb_xml.omzetten(wet(sluiting=sluiting))
        assert markdown.endswith("\n\nDe Minister van Financiën, namens deze, de secretaris-generaal, A. Proef\n")
        assert [e.anker for e in eenheden] == ["art-1"] and not onbekend


def test_dossierref_in_een_alinea_is_alleen_haar_tekst():
    """`inline:dossierref` (T11-F2; getuigen BWBR0052884, BWBR0052900): de tekst zonder grens, zoals `<extref>`;
    het attribuut `dossier` is geen tekst."""
    markdown, _, onbekend, _ = wetten.bwb_xml.omzetten(wet(
        '<al>Zie de toelichting (<dossierref dossier="36800">Kamerstukken II 2025/26, 36 800, nr. 3</dossierref>)'
        ' en de nota<dossierref dossier="36800">bij 36 800</dossierref>.</al>'))
    assert "Zie de toelichting (Kamerstukken II 2025/26, 36 800, nr. 3) en de notabij 36 800." in markdown
    assert "dossier" not in markdown and not onbekend


def test_plaatje_in_een_lijstitem_is_een_vervolgregel_en_opent_zo_nodig_het_item():
    """`li:plaatje` (T11-F1): achter de tekst een vervolgregel; vóór de tekst eerst de regel met alleen het
    nummer, zoals bij een item dat met een sublijst begint; zonder bijschrift niets, en het item opent dan
    met zijn eerste `<al>`. Het anker hangt aan het nummer, zoals altijd."""
    lijst = ("<al>Borden:</al><lijst>"
             f"<li><li.nr>a.</li.nr><al>bord A1;</al>{plaatje('1', 'Figuur 1')}</li>"
             f"<li><li.nr>b.</li.nr>{plaatje('2', 'Figuur 2')}<al>bord A2;</al></li>"
             f"<li><li.nr>c.</li.nr>{plaatje('3')}<al>bord A3.</al></li>"
             f"<li><li.nr>d.</li.nr><al>bord A4 met</al><lijst><li><li.nr>1°.</li.nr><al>pijl;</al>"
             f"{plaatje('4', 'Figuur 4')}</li></lijst></li></lijst>")
    markdown, eenheden, onbekend, extra = wetten.bwb_xml.omzetten(wet(lijst))
    assert ("Borden:\n\n- a. bord A1;\n  Figuur 1\n- b.\n  Figuur 2\n  bord A2;\n- c. bord A3.\n"
            "- d. bord A4 met\n  - 1°. pijl;\n    Figuur 4\n") in markdown
    assert [(e.anker, e.tekst) for e in eenheden] == [
        ("art-1", "Artikel 1"), ("art-1-a", "a. bord A1;"), ("art-1-b", "b."), ("art-1-c", "c. bord A3."),
        ("art-1-d", "d. bord A4 met"), ("art-1-d-1", "1°. pijl;")]
    assert [b["naam"] for b in extra["afbeeldingen_weggelaten"]] == ["1.png", "2.png", "3.png", "4.png"]
    assert not onbekend


def test_plaatje_direct_in_een_structuurelement_is_een_eigen_alinea():
    """`blok:plaatje` (T11-F1; getuige BWBR0039112): een plaatje in een hoofdstuk tussen twee artikelen gaat zoals
    in een lid of bijlage (kb WP-20): het bijschrift als alinea, zonder eenheid; zonder bijschrift niets."""
    xml = wet().replace(b"<regeling-tekst>\n<artikel>", (
        "<regeling-tekst><hoofdstuk><kop><label>Hoofdstuk</label><nr>1</nr><titel>Kavel</titel></kop>"
        "<artikel>").encode()).replace(b"</artikel>\n</regeling-tekst>", (
        f"</artikel>{plaatje('5', 'Kaart 1. Ligging van de kavel')}{plaatje('6')}"
        "<artikel><kop><label>Artikel</label><nr>2</nr></kop><al>Slot.</al></artikel>"
        "</hoofdstuk></regeling-tekst>").encode())
    markdown, eenheden, onbekend, extra = wetten.bwb_xml.omzetten(xml)
    assert "### Artikel 1\n\nTekst.\n\nKaart 1. Ligging van de kavel\n\n### Artikel 2\n\nSlot.\n" in markdown
    assert [e.anker for e in eenheden] == ["hfd-1", "art-1", "art-2"] and not onbekend
    assert [b["naam"] for b in extra["afbeeldingen_weggelaten"]] == ["5.png", "6.png"]


@pytest.mark.parametrize("plek", ["lijst", "blok", "bijlage"])
def test_plaatje_met_eigen_tekst_blijft_een_weigering(plek):
    """`plaatje()` leest alleen `illustratie` en `bijschrift`; eigen tekst zou stil wegvallen, nu het plaatje in
    een lijstitem en een blok niet meer weigert. In de 58 plaatjes van de kennisbank (9 oktober 2026) staat er
    geen. Ook in een bijlage, waar het plaatje al sinds kb WP-20 een vorm had."""
    eigen = '<plaatje>schema<illustratie id="7" naam="7.png"/></plaatje>'
    if plek == "lijst":
        xml = wet(f"<lijst><li><li.nr>a.</li.nr><al>tekst</al>{eigen}</li></lijst>")
    elif plek == "blok":
        xml = wet().replace(b"</artikel>\n</regeling-tekst>", f"</artikel>{eigen}</regeling-tekst>".encode())
    else:
        xml = wet(bijlage=f"<bijlage><kop><label>Bijlage</label><nr>1</nr></kop>{eigen}</bijlage>")
    with pytest.raises(ConversionError, match="eigen tekst"):
        wetten.bwb_xml.omzetten(xml)


def test_plaatje_met_tekst_achter_een_kind_blijft_een_weigering():
    xml = wet('<lijst><li><li.nr>a.</li.nr><plaatje><illustratie id="8" naam="8.png"/>schema</plaatje></li></lijst>')
    with pytest.raises(ConversionError, match="eigen tekst"):
        wetten.bwb_xml.omzetten(xml)


def test_plaatje_met_een_onbekend_kind_in_een_lijstitem_blijft_een_weigering():
    xml = wet('<lijst><li><li.nr>a.</li.nr><plaatje><legenda>rood</legenda></plaatje></li></lijst>')
    with pytest.raises(ConversionError, match="plaatje:legenda"):
        wetten.bwb_xml.omzetten(xml)
