# BWB-fixture

Een vast testbestand is wat converter en kennisbank mogen delen; code niet. Elk paar hier is byte voor byte
een fixture van de kennisbank, die de raw-vorm eerst met haar eigen lezers las (regel 3 van haar `AGENTS.md`);
de convertertest legt de uitvoer van `bwb_xml.omzetten()` ernaast.

- `considerans-nogniet.xml` en `considerans-nogniet.md` zijn
  `md-clean-core/tests/fixtures/bwb-considerans-nogniet/regeling.{xml,md}` (kb WP-103, 6 oktober 2026): eigen
  tekst naar de vorm van de getuigen van de grote test van oktober 2026. De XML heeft een `<considerans.lijst>`
  (H7, het Besluit elektronisch procederen) en een nog niet geldend hoofdstuk, paragraaf en afdeling (besluit
  12, M1: het Besluit digitale overheid, de Wft, de Vreemdelingenwet 2000, de Wet digitale overheid en de
  Jeugdwet); de Markdown is de raw-vorm die de omzetter daarvoor schrijft.
- `deze-plaatje-dossierref.xml` en `deze-plaatje-dossierref.md` zijn
  `md-clean-core/tests/fixtures/bwb-deze-plaatje-dossierref/regeling.{xml,md}` (kb WP-114, 9 oktober 2026): eigen
  tekst naar de vorm van de weigeringen `inline:deze`, `inline:dossierref`, `li:plaatje` en `blok:plaatje` uit
  twee bevestigingstests van de kennisbank (T7-F1, T11-F1, T11-F2, besluit 11 van haar plan 7). Twee
  mandaatondertekeningen (de laatste zonder witruimte), een `<dossierref>` in een alinea (ook zonder witruimte
  ervoor), een lijst met een plaatje achter de tekst van een item, een plaatje dat een item opent en een
  plaatje zonder bijschrift, en een plaatje direct in een hoofdstuk tussen twee artikelen.
- `noten-artikel-zonder-nummer.xml` en `noten-artikel-zonder-nummer.md` zijn
  `md-clean-core/tests/fixtures/bwb-noten-artikel-zonder-nummer/regeling.{xml,md}` (kb WP-123, 8 november 2026):
  eigen tekst naar de vorm van getuigen buiten de gemeten sets van de kennisbank (besluit 8.5 van haar plan 8). Een
  artikel zonder nummer vóór hoofdstuk 1 (`Algemene bepaling`, de Grondwet) en een `(Gereserveerd)` in een afdeling
  (Boek 5 Sv); een noot met een `<noot.lijst>` tussen twee `noot.al`'s; een `<structuurtekst>` met `[Vervallen]`
  onder een hoofdstuk en onder een afdeling met artikelen (de wetten-BES); een bijlage met twee tabellen waarvan de
  `sup`-noten elk bij 1 beginnen (de VIRBI 2013) en daarna een `<noot>` 1 (het Kavelbesluit V), zodat de reeks drie
  keer telt: `annex-1-1`, `annex-1-n2-1`, `annex-1-n3-1`.

