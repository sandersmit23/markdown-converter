# Hof van Justitie en Gerecht

Verplaatst uit `CLAUDE.md` (WP-60, 29 september 2026), tekst ongewijzigd. `CLAUDE.md` bevat de
architectuur en verwijst hiernaartoe.

- **Hof van Justitie en Gerecht** (sinds 21 september 2026 via Formex): `eurlex._fetch_hof` vraagt
  `application/zip;mtype=fmx4` met `Accept-Language: nld` op de ECLI-resource of het CELEX-nummer
  en geeft de zip aan `formex_hof.omzetten`. Een arrest zonder Nederlandse Formex levert 404 en
  wordt geweigerd, met de reden erbij; er is bewust geen terugval op de Curia-HTML of op een andere
  taal. Sinds kb WP-105 (6 oktober 2026) noemt die reden uit de Cellar-metadata in welke vorm en taal
  het arrest er wél is (Inteligo Media, 62023CJ0654: "In het Nederlands heeft de Cellar 62023CJ0654
  alleen als html; fmx4 is er in 22 van de 24 talen."), in plaats van "een arrest van de laatste dagen
  of weken", wat voor een arrest van elf maanden niet klopte. Een CELEX met een volgnummer tussen
  haakjes wordt gecodeerd (`62015CV0001%2801%29`); Advies 1/15 weigert daarna op zijn soort. Rechtspraak
  heeft een andere Formex-vorm dan wetgeving: geen `.doc.xml`, één XML met wortel `JUDGMENT` of
  `ORDER`. De raw-vorm is die van het profiel: kale sectieregels, `NO.P` plus één spatie voor een
  overweging, `NO.P` plus **drie harde spaties** voor een geciteerd punt (binnen `QUOT.S` of een
  lijst — zonder dat onderscheid krijgt een geciteerde bijlage `ro`-ankers), het dictum uit
  `JURISDICTION/INTRO` als alinea's, de procestaalnoot als `[^procestaal]` met een definitie. De
  zelfcontrole is dezelfde als bij `hudoc_docx`. Weigeringen: `CONCLUSION`, `OPINION`,
  `JUDGMENT.NP`, `CASE`, `REPORT.HEARING`, `SUMMARY.*`, een zip met meer dan één XML of met een
  bestand dat de uitspraak niet als afbeelding aanroept (een aangeroepen TIFF wordt weggelaten
  met een melding), een onbekende aanhalingscode en `DLIST`. Gemeten op 143 Cellar-zips: 73 arresten of
  beschikkingen in één XML, 71 omgezet.
