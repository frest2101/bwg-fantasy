"""Skill bwg-spieltag für claude.ai bauen: Kopie des Stand-Skripts im Plugin-Ordner und ZIP zum Hochladen.

Seit 11.10.2026 läuft das Stand-Skript im claude.ai-Chat als Skill statt per exec aus dem Netz (Auto-Modus, Regel
„Code from External“; CLAUDE.md, Abschnitt „Stand-Skript für den Chat“). Der Skill liegt zweimal vor:
- plugins/bwg-spieltag/ ist ein Plugin des Marketplaces .claude-plugin/marketplace.json (claude.ai holt es aus dem
  öffentlichen Repo); darin skills/bwg-spieltag/ mit SKILL.md und scripts/claude_stand.py, einer Kopie von
  scripts/claude_stand.py (die Kopie, weil ein Plugin nur seinen eigenen Ordner mitnimmt).
- plugins/bwg-spieltag.zip enthält denselben Skill-Ordner zum Hochladen von Hand (Customize › Skills), falls der
  Marketplace-Weg nicht geht.
Beides schreibt dieses Skript aus scripts/claude_stand.py und der SKILL.md, Zeilenende LF, das ZIP deterministisch
(feste Reihenfolge und Zeitstempel, ohne Kompression). tests/test_skill.py prüft, dass Kopie und ZIP zu den Quellen
passen; die Kennung des Skills (claude_stand.skill_kennung) schreibt app_export nach claude.json › stand.skill.

Aufruf: python scripts/skill_bauen.py            schreibt Kopie und ZIP, nur bei Änderung
        python scripts/skill_bauen.py --pruefen  schreibt nichts; Exit-Code 1, wenn Kopie oder ZIP veraltet sind
Danach python scripts/compute.py (neue Kennung in claude.json) und pytest.
"""

import io
import sys
import zipfile
from pathlib import Path

import claude_stand as cs

REPO = Path(__file__).resolve().parent.parent
QUELLE = REPO / "scripts" / "claude_stand.py"
PLUGIN = REPO / "plugins" / cs.SKILL
SKILL_ORDNER = PLUGIN / "skills" / cs.SKILL
KOPIE = SKILL_ORDNER / "scripts" / "claude_stand.py"
ZIP = REPO / "plugins" / f"{cs.SKILL}.zip"
ZEIT = (1980, 1, 1, 0, 0, 0)            # fester Zeitstempel im ZIP (frühester, den das Format kennt)


def lf(daten: bytes) -> bytes:
    """Zeilenende LF (eine Windows-Arbeitskopie kann CRLF haben)."""
    return daten.replace(b"\r\n", b"\n")


def skill_dateien() -> dict[str, bytes]:
    """Inhalt des Skills je Pfad im Skill-Ordner (cs.SKILL_DATEIEN): SKILL.md aus dem Plugin, das Skript aus scripts/."""
    return {name: lf(QUELLE.read_bytes() if name == "scripts/claude_stand.py" else (SKILL_ORDNER / name).read_bytes())
            for name in cs.SKILL_DATEIEN}


def zip_bytes(dateien: dict[str, bytes]) -> bytes:
    """ZIP mit dem Skill-Ordner bwg-spieltag/ auf oberster Ebene, wie claude.ai es beim Hochladen verlangt."""
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_STORED) as archiv:
        for name in sorted(dateien):
            info = zipfile.ZipInfo(f"{cs.SKILL}/{name}", date_time=ZEIT)
            info.create_system = 3                  # Unix, auch unter Windows gebaut
            info.external_attr = 0o100644 << 16     # normale Datei, rw-r--r--
            archiv.writestr(info, dateien[name])
    return puffer.getvalue()


def zip_inhalt(daten: bytes) -> dict[str, bytes]:
    """Dateien eines ZIPs je Pfad (zum Vergleich ohne Rücksicht auf Byte-Details einer anderen Python-Version)."""
    with zipfile.ZipFile(io.BytesIO(daten)) as archiv:
        return {info.filename: archiv.read(info) for info in archiv.infolist() if not info.is_dir()}


def veraltet() -> list[str]:
    """Was nicht zu den Quellen passt: die Kopie im Plugin, das ZIP (verglichen wird der Inhalt, nicht die Bytes)."""
    dateien, aus = skill_dateien(), []
    if not KOPIE.exists() or lf(KOPIE.read_bytes()) != dateien["scripts/claude_stand.py"]:
        aus.append(str(KOPIE.relative_to(REPO)))
    soll = {f"{cs.SKILL}/{name}": inhalt for name, inhalt in dateien.items()}
    if not ZIP.exists() or zip_inhalt(ZIP.read_bytes()) != soll:
        aus.append(str(ZIP.relative_to(REPO)))
    return aus


def kennung():
    """Kennung des Skills im Plugin-Ordner (claude.json › stand.skill); None, wenn der Ordner fehlt."""
    return cs.skill_kennung(SKILL_ORDNER)


def bauen() -> list[str]:
    """Schreibt Kopie und ZIP, wenn sie veraltet sind; gibt die geschriebenen Pfade zurück."""
    alt, dateien = veraltet(), skill_dateien()
    if str(KOPIE.relative_to(REPO)) in alt:
        KOPIE.parent.mkdir(parents=True, exist_ok=True)
        KOPIE.write_bytes(dateien["scripts/claude_stand.py"])
    if str(ZIP.relative_to(REPO)) in alt:
        ZIP.write_bytes(zip_bytes(dateien))
    return alt


def main(argv: list[str]) -> int:
    if "--pruefen" in argv[1:]:
        alt = veraltet()
        print("Skill veraltet: " + ", ".join(alt) + " – python scripts/skill_bauen.py" if alt else "Skill aktuell")
        return 1 if alt else 0
    geschrieben = bauen()
    print(("geschrieben: " + ", ".join(geschrieben)) if geschrieben else "Skill unverändert")
    print(f"Kennung {kennung()} – danach python scripts/compute.py (claude.json › stand.skill) und pytest")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
