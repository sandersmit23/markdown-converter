# BWB-fixture

`considerans-nogniet.xml` en `considerans-nogniet.md` zijn byte voor byte de fixture
`md-clean-core/tests/fixtures/bwb-considerans-nogniet/regeling.{xml,md}` van de kennisbank (kb WP-103,
6 oktober 2026): eigen tekst naar de vorm van de getuigen van de grote test van oktober 2026. De XML
heeft een `<considerans.lijst>` (H7, het Besluit elektronisch procederen) en een nog niet geldend
hoofdstuk, paragraaf en afdeling (besluit 12, M1: het Besluit digitale overheid, de Wft, de
Vreemdelingenwet 2000, de Wet digitale overheid en de Jeugdwet); de Markdown is de raw-vorm die de
omzetter daarvoor schrijft. De kennisbank las die vorm eerst met haar eigen lezers (regel 3 van haar
`AGENTS.md`); de convertertest legt de uitvoer van `bwb_xml.omzetten()` ernaast. Een vast testbestand is
wat converter en kennisbank mogen delen; code niet.
