"""Besluit 2 en 3 van WP-77 (1 oktober 2026), overgenomen in de fork op 7 oktober 2026: wat de
kennisbankroute streng houdt waar de losse download mag terugvallen.

2. Een bron zonder herkomst is in `kb_fetch` een weigering met reden, geen crash.
3. De glyph-waarschuwing staat in de tekst bij een losse download en in de metadata bij een
   document met `document_id`.

Besluit 1 (één Kamerstukroute met de invoerherkenning van Floris ervoor) leeft alleen op de
branch `gelijktrekken-upstream`; de fork heeft zijn modules niet. Geen netwerk.
"""

from __future__ import annotations

import json

import pytest

from mdconv import kb_fetch
from mdconv.sources import Document


# ---------------------------------------------------------------------------
# Besluit 2
# ---------------------------------------------------------------------------

def _zonder_herkomst(monkeypatch, warnings=()):
    """Een bron die een document zonder herkomst levert, zoals een losse download."""
    monkeypatch.setattr(kb_fetch.sources, "from_link",
                        lambda v, lang="NL": Document("# Tekst\n", "Bron", warnings=tuple(warnings)))


def test_a_source_without_provenance_is_refused_by_kb_fetch_with_the_reason(tmp_path, monkeypatch):
    _zonder_herkomst(monkeypatch)
    uitkomst = kb_fetch.haal_op("iets", tmp_path, "NL")
    assert uitkomst["status"] == "geweigerd"
    assert "bronbewijs" in uitkomst["melding"] and "geen kennisbankbundel" in uitkomst["melding"]
    assert not (tmp_path / "raw").exists()


def test_the_warnings_of_the_source_say_why_there_is_no_bundle(tmp_path, monkeypatch):
    _zonder_herkomst(monkeypatch, ("De bron heeft geen officiële XML; de tekst is omgezet uit de PDF.",))
    assert kb_fetch.main(["--uit", str(tmp_path), "iets"]) == 1
    ophaal = json.loads((tmp_path / "ophaal.json").read_text(encoding="utf-8"))
    regel = ophaal["iets"]
    assert regel["status"] == "geweigerd" and "ValueError" not in regel["melding"]
    assert "bronbewijs" in regel["melding"] and "geen officiële XML" in regel["melding"]
    assert not (tmp_path / "raw").exists()


# ---------------------------------------------------------------------------
# Besluit 3
# ---------------------------------------------------------------------------

def _pdf_met_glyph(monkeypatch):
    from mdconv.sources import files, pdf_images

    monkeypatch.setattr(files, "convert", lambda data, name: ("Dit is o�en een probleem.\n", files.ENGINE_PDF_INSPECTOR))
    monkeypatch.setattr(pdf_images, "available", lambda: False)


def test_unmapped_glyphs_go_above_the_text_of_a_loose_download(monkeypatch):
    from mdconv.source_structure import sha256
    from mdconv.sources import from_file

    _pdf_met_glyph(monkeypatch)
    doc = from_file(b"%PDF", "rapport.pdf")
    assert doc.markdown.startswith("*Let op: dit document bevat een of meer onleesbare tekens")
    assert doc.markdown.endswith("Dit is o�en een probleem.\n")
    assert doc.warnings == ()
    # De herkomst van een losse download hasht de tekst mét de alinea: wat je downloadt is wat er staat.
    assert doc.provenance.extra["source_structure"]["markdown_sha256"] == sha256(doc.markdown)


def test_unmapped_glyphs_go_into_the_metadata_of_a_kb_document(monkeypatch):
    from mdconv.sources import files, from_file

    _pdf_met_glyph(monkeypatch)
    doc = from_file(b"%PDF", "rapport.pdf", document_id="edpb-guidelines-05-2020")
    assert doc.markdown == "Dit is o�en een probleem.\n"
    assert doc.warnings == (files.UNMAPPED_GLYPHS_WARNING,)
    assert doc.provenance.waarschuwingen == (files.UNMAPPED_GLYPHS_WARNING,)
    assert doc.provenance.as_json()["waarschuwingen"] == [files.UNMAPPED_GLYPHS_WARNING]


def test_a_clean_pdf_gets_neither(monkeypatch):
    from mdconv.sources import files, from_file, pdf_images

    monkeypatch.setattr(files, "convert", lambda data, name: ("Schone tekst.\n", files.ENGINE_PDF_INSPECTOR))
    monkeypatch.setattr(pdf_images, "available", lambda: False)
    for document_id in (None, "edpb-guidelines-05-2020"):
        doc = from_file(b"%PDF", "rapport.pdf", document_id=document_id)
        assert doc.markdown == "Schone tekst.\n" and doc.warnings == ()
