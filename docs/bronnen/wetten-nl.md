# wetten.overheid.nl (BWB-XML)

Verplaatst uit `CLAUDE.md` (WP-60, 29 september 2026), tekst ongewijzigd. `CLAUDE.md` bevat de
architectuur en verwijst hiernaartoe.

- **wetten.overheid.nl**: eerst de officiële **BWB-XML** van KOOP (`repository.officiele-
  overheidspublicaties.nl/bwb/{BWB}/manifest.xml` → de toestand op de peildatum, `bwb_xml.py`);
  alleen als die route er niet is (`_BwbXmlNietBeschikbaar`) de **portal-HTML**, server-rendered met
  de volledige tekst in `#regeling` (h1 titel, h3 hoofdstuk, h4 artikel): `wetten.py` pakt die
  container, strip't werkbalk-ruis (`[class*=action--]`, `.visually-hidden`) en markdownify't.
  Een weigering van de XML-omzetter valt bewust **niet** terug op de HTML: met een BWB-identiteit
  is de weigering het antwoord. URL wordt herbouwd uit BWB-id + optionele versiedatum
  (`/{jjjj-mm-dd}`). Gemeten op de Awb (`BWBR0005537`): een `<tussenkop kopopmaak="cur">` scheidt
  de digitale en de papieren variant van artikel 8:36c en wordt een cursieve alinea, geen kop en
  geen eenheid (als kop gaf het een tweede `art-8-36c`); Bijlage 2 deelt haar artikelen in
  `divisie`s in, en `divisie()` krijgt daarvoor van `bijlage()` het kopniveau en het ankerpad mee
  (`annex-2-art-7`). De leden van de tweede variant van 8:36c dragen dezelfde ankers als de eerste:
  dat zegt de bron, en de BWB-route controleert ankers niet op dubbelen.
  Sinds kb WP-13 (25 september 2026) twee vormen erbij. Een **`<noot type="voet">` midden in
  een alinea** (Regeling ggz en fz 2026, BWBR0051654) wordt native: `[^n]` op zijn plek, de
  definitie direct onder het blok van de marker (aan het eind van het document las ze als tekst
  van de laatste bijlage), in een bijlage met de reeks van die bijlage (`[^annex-2-1]`); een noot
  in een nummer weigert, want `nummer_anker()` maakte van `1[^1]` stil het lidanker `-11`. En een
  **`<circulaire>`** (nadere regel NR/REG-1829, BWBR0041321) heeft de vorm van `<regeling>`; haar
  `circulaire.divisie`s worden koppen (`## 1. Reikwijdte`) zonder eenheid, omdat de bron ze geen
  artikel noemt.
  Sinds kb WP-43 (29 september 2026) is een **`<sup>` met cijfers alleen een noot als dezelfde bijlage
  er een definitie voor heeft**, anders een macht `^n^` (Archiefregeling: `kg/m<sup>3</sup>`); een
  ondertekening is één regel met de losse tekst ertussen; `<table><title>` en `<kop><subtitel>` worden
  een alinea boven de tabel en onder de kop, en een ander kind van `<table>` of `<kop>` weigert.
  Sinds kb WP-103 (6 oktober 2026) twee vormen erbij. Een **`<considerans.lijst>`** (de grondslagen onder
  `Gelet op:`) wordt een lijst zoals elke BWB-lijst, `- a. …`, zonder eenheid (de aanhef heeft geen artikel);
  tot dan viel het nummer weg en stonden de vier grondslagen van het Besluit elektronisch procederen er
  zonder `a.`–`d.`. En een **hoofdstuk, afdeling of paragraaf met `status="nogniet"`** weigert niet meer:
  de kop houdt zijn eenheid, eronder staat de `<redactie>`-regel uit de `<structuurtekst>` van de bron
  (`[Red: Dit onderdeel is nog niet inwerking getreden]`) of anders `[Nog niet in werking getreden.]`, en
  de artikelen erin worden geschreven zoals een nog niet geldend artikel (melding onder de kop, leden als
  platte alinea zonder eenheid), ook zonder eigen status. Op elk ander element blijft `nogniet` een
  weigering, net als `<structuurtekst>` buiten zo'n element en een vervallen artikel erin. Gemeten op de
  vijf regelingen die de kennisbank daardoor miste (Besluit digitale overheid, Vreemdelingenwet 2000, Wet
  digitale overheid, Jeugdwet, Wft); de raw-vorm is de fixture `tests/fixtures/bwb/`.
  Sinds kb WP-114 (9 oktober 2026) drie vormen erbij (besluit 11 van haar plan 7). **`<deze>`** (`namens deze,`
  in een mandaatondertekening) en **`<dossierref>`** in een alinea (`Kamerstukken II 2025/26, 36 800, nr. 3`) zijn
  gewone tekst, zoals `<functie>` en `<extref>`; in een ondertekening staat `namens deze,` op de ene regel, met een
  spatie tussen de delen, en het attribuut `dossier` is geen tekst. Een **`<plaatje>` in een lijstitem** wordt een
  vervolgregel met het bijschrift (opent het het item, dan eerst `- b.` met alleen het nummer, zoals bij een item dat
  met een sublijst begint), en een **`<plaatje>` direct in een structuurelement** een eigen alinea met het bijschrift,
  zoals al in een lid of bijlage; het beeld zelf wordt vastgelegd in `afbeeldingen_weggelaten`, niet overgenomen, en
  zonder bijschrift laat een plaatje niets achter. Een plaatje met eigen tekst naast `illustratie` en `bijschrift`
  weigert nu in elke context, want die tekst zou stil wegvallen. Tot dan weigerden `inline:deze`, `inline:dossierref`,
  `li:plaatje` en `blok:plaatje` negen regelingen in twee bevestigingstests van de kennisbank; de raw-vorm is de
  fixture `tests/fixtures/bwb/deze-plaatje-dossierref.{xml,md}`.
