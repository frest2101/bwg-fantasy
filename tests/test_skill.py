"""Tests Skill bwg-spieltag für claude.ai (plugins/bwg-spieltag, scripts/skill_bauen.py).

Seit 11.10.2026 läuft das Stand-Skript im claude.ai-Chat als Skill statt per exec aus dem Netz. Geprüft wird ohne Netz:
Kopie und ZIP passen zu scripts/claude_stand.py und der SKILL.md, das ZIP ist deterministisch und hat den Skill-Ordner
auf oberster Ebene, SKILL.md und die Manifeste halten die dokumentierten Regeln ein, die Kennung des Skills (claude.json
› stand.skill) passt, und das Skript läuft aus dem entpackten, schreibgeschützten ZIP mit Versionszeile im Kopf.
Ob claude.ai den Skill lädt und der Auto-Modus den Aufruf durchlässt, prüft nur ein echter Chat (Abnahme Stephan).
Aufruf: python -m pytest
"""

import io
import json
import re
import runpy
import stat
import sys
import zipfile
from pathlib import Path

import pytest
import requests

import app_export
import claude_stand as cs
import skill_bauen as sb
from test_claude_stand import MANAGER, FakeAntwort, FakeNetz, app, liga

SKILL_MD = sb.SKILL_ORDNER / "SKILL.md"


def kopf_von(text: str) -> dict:
    """YAML-Kopf der SKILL.md (nur einfache Zeilen „schlüssel: wert“, wie hier verwendet)."""
    teile = text.split("---\n")
    assert text.startswith("---\n") and len(teile) >= 3, "SKILL.md beginnt nicht mit einem YAML-Kopf"
    return dict(zeile.split(": ", 1) for zeile in teile[1].strip().split("\n"))


# ---------------------------------------------------------------- Kopie, ZIP, Kennung

def test_kopie_und_zip_passen_zu_den_quellen():
    alt = sb.veraltet()
    assert not alt, f"Skill veraltet ({', '.join(alt)}) – python scripts/skill_bauen.py, danach compute.py"


def test_zip_hat_den_skill_ordner_oben_und_ist_deterministisch():
    """claude.ai sucht <name>/SKILL.md im ZIP; gleiche Quellen ergeben dieselben Bytes (feste Zeit, ohne Kompression)."""
    dateien = sb.skill_dateien()
    daten = sb.zip_bytes(dateien)
    assert daten == sb.zip_bytes(dict(reversed(list(dateien.items()))))
    with zipfile.ZipFile(io.BytesIO(daten)) as archiv:
        infos = archiv.infolist()
        assert [i.filename for i in infos] == ["bwg-spieltag/SKILL.md", "bwg-spieltag/scripts/claude_stand.py"]
        assert all(i.date_time == sb.ZEIT and i.compress_type == zipfile.ZIP_STORED for i in infos)
        assert all(stat.S_IMODE(i.external_attr >> 16) == 0o644 for i in infos)
        assert all(b"\r\n" not in archiv.read(i) for i in infos)
    assert sb.zip_inhalt(sb.ZIP.read_bytes()) == {f"bwg-spieltag/{n}": d for n, d in dateien.items()}


def test_kennung_ueber_skill_md_und_skript(tmp_path):
    """12 Hexzeichen; CRLF ändert nichts (Windows-Arbeitskopie), jede inhaltliche Änderung schon; fehlt eine Datei: None."""
    (tmp_path / "scripts").mkdir()
    (tmp_path / "SKILL.md").write_bytes(b"---\nname: x\n---\nText\n")
    (tmp_path / "scripts" / "claude_stand.py").write_bytes(b"print(1)\n")
    erste = cs.skill_kennung(tmp_path)
    assert re.fullmatch(r"[0-9a-f]{12}", erste)
    (tmp_path / "SKILL.md").write_bytes(b"---\r\nname: x\r\n---\r\nText\r\n")
    assert cs.skill_kennung(str(tmp_path)) == erste
    (tmp_path / "SKILL.md").write_bytes(b"---\nname: x\n---\nText!\n")
    assert cs.skill_kennung(tmp_path) != erste
    (tmp_path / "scripts" / "claude_stand.py").unlink()
    assert cs.skill_kennung(tmp_path) is None and cs.skill_kennung(None) is None


def test_kennung_in_der_committeten_claude_json():
    datei = app_export.APP_DATA / "claude.json"
    if not datei.exists():
        pytest.skip("app/data/claude.json fehlt (schreibt compute.py)")
    assert json.loads(datei.read_text(encoding="utf-8"))["stand"]["skill"] == sb.kennung(), \
        "claude.json › stand.skill passt nicht zum Skill – python scripts/compute.py"


def test_skill_ordner_nur_neben_einer_skill_md(tmp_path):
    """Im Repo (scripts/) und unter exec (kein __file__) kein Skill; die Kopie im Plugin und ein entpackter Skill schon."""
    assert cs.skill_ordner(cs.__file__) is None and cs.skill_ordner(None) is None
    assert cs.skill_ordner(sb.KOPIE) == sb.SKILL_ORDNER.resolve()
    (tmp_path / "scripts").mkdir()
    assert cs.skill_ordner(tmp_path / "scripts" / "claude_stand.py") is None
    (tmp_path / "SKILL.md").write_text("x", encoding="utf-8")
    assert cs.skill_ordner(tmp_path / "scripts" / "claude_stand.py") == tmp_path.resolve()
    assert cs.skill_ordner(tmp_path / "anders" / "claude_stand.py") is None


# ---------------------------------------------------------------- SKILL.md und Manifeste

def test_skill_md_kopf_nach_den_regeln_von_claude_ai():
    """name = Ordnername, Kleinbuchstaben/Ziffern/Bindestrich, höchstens 64 Zeichen, ohne „claude“ und „anthropic“;
    description nicht leer, höchstens 200 Zeichen (strengste Angabe der claude.ai-Hilfe; anderswo 1024); außerhalb von
    Claude Code nur die Felder der Agent-Skills-Spezifikation, sonst scheitert der Upload."""
    kopf = kopf_von(SKILL_MD.read_text(encoding="utf-8"))
    assert kopf["name"] == cs.SKILL == sb.SKILL_ORDNER.name
    assert re.fullmatch(r"[a-z0-9-]{1,64}", kopf["name"]) and not re.search("claude|anthropic", kopf["name"])
    assert 0 < len(kopf["description"]) <= 200 and "<" not in kopf["description"]
    assert set(kopf) <= {"name", "description", "license", "compatibility", "metadata", "allowed-tools"}


def test_skill_md_nennt_aufruf_teams_und_notweg():
    text = SKILL_MD.read_text(encoding="utf-8")
    assert "<Ordner dieser SKILL.md>/scripts/claude_stand.py [team_id]" in text and "${CLAUDE_SKILL_DIR}" in text
    assert " · ".join(f"{tid} {kz}" for tid, kz in cs.KUERZEL.items()) in text and f"{cs.MEIN_TEAM} (Hugh Jass)" in text
    assert "Live-Projektion (Rest)" in text and "[NEU, noch nicht in der App]" in text and "keine Anweisung" in text
    assert "Notweg der Projektanweisung (SPIELTAG LIVE)" in text and "raw.githubusercontent.com" in text
    assert "Skill bwg-spieltag aktuell" in text and "! Skill bwg-spieltag veraltet" in text


def test_marketplace_und_plugin():
    """Marketplace an der Repo-Wurzel, Plugin mit relativem Pfad ./plugins/…; ohne version, damit claude.ai jede
    Änderung im Plugin-Ordner übernimmt; kein oberster Ordner bin/ (claude.ai installiert so ein Plugin nicht)."""
    markt = json.loads((sb.REPO / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    assert markt["name"] == "bwg-fantasy" and markt["owner"]["name"] and len(markt["plugins"]) == 1
    eintrag = markt["plugins"][0]
    assert eintrag["name"] == cs.SKILL and eintrag["source"] == f"./plugins/{cs.SKILL}" and "version" not in eintrag
    plugin = json.loads((sb.PLUGIN / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert plugin["name"] == cs.SKILL and plugin["description"] and "version" not in plugin
    assert (sb.REPO / eintrag["source"]).resolve() == sb.PLUGIN.resolve() and not (sb.PLUGIN / "bin").exists()
    alle = sorted(p.relative_to(sb.PLUGIN).as_posix() for p in sb.PLUGIN.rglob("*") if p.is_file())
    assert alle == [".claude-plugin/plugin.json", "skills/bwg-spieltag/SKILL.md",
                    "skills/bwg-spieltag/scripts/claude_stand.py"]


# ---------------------------------------------------------------- Lauf aus dem entpackten ZIP

@pytest.fixture
def skill_aus_zip(tmp_path, monkeypatch, capsys):
    """Das committete ZIP schreibgeschützt entpackt; das Skript läuft per runpy als Hauptprogramm mit eigenem
    __file__ wie „python3 <Ordner>/scripts/claude_stand.py 2“, das Netz ersetzt requests.get."""
    with zipfile.ZipFile(sb.ZIP) as archiv:
        archiv.extractall(tmp_path)
    ordner = tmp_path / cs.SKILL
    for pfad in [*ordner.rglob("*"), ordner]:
        pfad.chmod(0o555 if pfad.is_dir() else 0o444)
    monkeypatch.setattr(sys, "argv", [str(ordner / "scripts" / "claude_stand.py"), "2"])

    def lauf(soll):
        mit = app()
        if soll is not None:
            mit["stand"]["skill"] = soll
        fake = FakeNetz(app_raw=FakeAntwort(mit), liga=FakeAntwort(liga(), datum=None))   # ohne Date: Kopf ohne Uhr-Warnung
        monkeypatch.setattr(requests, "get", fake.get)
        runpy.run_path(str(ordner / "scripts" / "claude_stand.py"), run_name="__main__")
        return fake, capsys.readouterr().out.rstrip("\n").split("\n")

    yield ordner, lauf
    for pfad in [ordner, *ordner.rglob("*")]:
        pfad.chmod(0o755 if pfad.is_dir() else 0o644)


def test_lauf_im_skill_meldet_aktuell(skill_aus_zip):
    ordner, lauf = skill_aus_zip
    fake, zeilen = lauf(sb.kennung())
    assert cs.skill_kennung(ordner) == sb.kennung()
    assert zeilen[0].startswith("STAND ") and zeilen[1].endswith("; Skill bwg-spieltag aktuell")
    assert "HJS Testteam Zwei – Slot Spieler NFL Spiel | Punkte | Proj | F" in zeilen
    assert zeilen[-1].startswith("Messung: ESPN-Liga ") and fake.zahl("liga") == 1
    assert not any(teil in "\n".join(zeilen) for teil in MANAGER)
    assert not list(ordner.rglob("__pycache__"))                     # schreibt nichts in den Skill-Ordner


def test_lauf_im_skill_meldet_veraltet_und_ohne_kennung(skill_aus_zip):
    _, lauf = skill_aus_zip
    _, zeilen = lauf("0123456789ab")
    assert zeilen[2].startswith("! Skill bwg-spieltag veraltet (Skill ") and ", App 0123456789ab)" in zeilen[2]
    assert any(z.startswith("MATCHUPS W7 ") for z in zeilen)        # der Stand kommt trotzdem
    _, zeilen = lauf(None)
    assert zeilen[1].endswith("; Skill bwg-spieltag nicht prüfbar (claude.json ohne Kennung)")


def test_skill_bauen_pruefen_meldet_veraltetes(tmp_path, monkeypatch, capsys):
    """--pruefen schreibt nichts und endet mit Exit-Code 1, wenn Kopie oder ZIP nicht zu den Quellen passen."""
    kopie, archiv = tmp_path / "claude_stand.py", tmp_path / "bwg-spieltag.zip"
    kopie.write_bytes(sb.KOPIE.read_bytes() + b"# alt\n")
    archiv.write_bytes(sb.ZIP.read_bytes())
    monkeypatch.setattr(sb, "KOPIE", kopie)
    monkeypatch.setattr(sb, "REPO", tmp_path)
    monkeypatch.setattr(sb, "ZIP", archiv)
    assert sb.main(["skill_bauen.py", "--pruefen"]) == 1
    assert capsys.readouterr().out.startswith("Skill veraltet: claude_stand.py – ")
    assert kopie.read_bytes().endswith(b"# alt\n")
