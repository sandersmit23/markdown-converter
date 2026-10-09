# Formex-fixture

Een vast testbestand is wat converter en kennisbank mogen delen; code niet. Elk paar hier is byte voor byte
een fixture van de kennisbank, die de raw-vorm eerst met haar eigen lezers las (regel 3 van haar `AGENTS.md`);
de convertertest legt de uitvoer van `formex_xml.omzetten()` ernaast. De XML is één onderdeel van een
Cellar-zip; de test zet er een documentmanifest bij (`L_202609115NL.doc.fmx.xml`) en een leeg bestand voor
elke TIFF die het onderdeel in `BIB.INSTANCE/INCLUSIONS` declareert.

- `blok-in-alinea.xml` en `blok-in-alinea.md` zijn `md-clean-core/tests/fixtures/formex-blok-in-alinea/bron.xml`
  en `raw.md` (kb WP-115, 9 oktober 2026): eigen tekst (een verzonnen besluit 2026/9115) naar de vorm van de
  weigeringen `inline:GR.SEQ` en `inline:DLIST` en van de woordcontrole op een vaste `LINK` uit twee
  bevestigingstests van de kennisbank (T9-F5, T10-F3, T10-F5, besluit 12 van haar plan 7). Een figuur in de `P`
  van een overweging en een tabel als groep in de `TXT` van een overweging, een groep in de `ALINEA` van een lid,
  een definitielijst zonder `PREFIX` in de `TXT` van een onderdeel en in de eerste `P` van een streepjesitem, een
  figuur in een `P` van een bijlage naast een gewone groep; als negatief een omhulsel-`P` met een definitielijst
  met ankers en een groep en definitielijst in een citaat; en een noot met een `LINK` zonder witruimte achter een
  woord, naast een noot in de gewone vorm `ELI: <LINK>`.
