"""Öffentlichkeits-Check (Baustein 4): prüft die App, bevor sie committet bzw. auf GitHub Pages veröffentlicht wird.

Geprüft wird ein Ordner (app/ oder der Build-Ordner _site/ in pages.yml):
1. nur erlaubte Dateitypen, keine versteckten Dateien, keine .lokal-Pfade
2. in JSON keine verbotenen Schlüssel (Manager, ESPN-Redaktionstexte, Chat-Metadaten)
3. in allen Textdateien keine vollen Namen, Nachnamen, Anzeigenamen oder Member-IDs der Manager;
   die Namen kommen zur Laufzeit aus data/raw/<Saison>/wNN/mTeam.json – hier steht kein Name
4. kein JSON-Text länger als MAX_TEXT Zeichen (fängt kopierte ESPN-Texte oder Chat ab)

Vornamen allein werden bewusst nicht geprüft: mehrere Manager-Vornamen kommen als Wort in NFL-Spielernamen vor.
Meldungen nennen nur Datei und Fundart, nie den gefundenen Namen, denn die Logs der Actions sind öffentlich.
Nur Standardbibliothek, lauffähig mit dem System-Python des Runners (3.12).

Aufruf: python scripts/check_public.py <ordner> [<repo-wurzel>]; Exit-Code 1 bei einem Fund.
"""

import json
import re
import sys
from pathlib import Path

ALLOWED = {".html", ".css", ".js", ".mjs", ".json", ".svg", ".png", ".ico", ".webmanifest", ".txt"}
TEXT = {".html", ".css", ".js", ".mjs", ".json", ".svg", ".webmanifest", ".txt"}
FORBIDDEN_KEYS = {
    # mTeam.members und Verweise darauf
    "members", "firstName", "lastName", "displayName", "notificationSettings", "owners", "primaryOwner",
    # ESPN-Redaktionstexte (mRoster, kona_player_info)
    "seasonOutlook", "outlooks", "outlooksByWeek",
    # kona_league_communication: Autor, Geräte, Chat
    "author", "creationInfo", "lastUpdateInfo", "clientAddress", "messages", "content",
    # mTransactions2: wer ausgeführt hat (teamId genügt)
    "memberId", "isLeagueManager", "isActingAsTeamOwner",
    # Draft-Vorbereitung einzelner Teams
    "excludedPlayerIds",
}
MAX_TEXT = 400


def manager_patterns(repo: Path) -> list[tuple[str, re.Pattern]]:
    """Suchmuster aus allen mTeam.json der Rohdaten: voller Name, Nachname, Anzeigename, Member-ID."""
    patterns, seen = [], set()
    for path in sorted(repo.glob("data/raw/*/w*/mTeam.json")):
        for m in json.loads(path.read_text(encoding="utf-8")).get("members", []):
            parts = [("voller Name", f"{m.get('firstName', '')} {m.get('lastName', '')}".strip()),
                     ("Nachname", m.get("lastName", "")),
                     ("Anzeigename", m.get("displayName", "")),
                     ("Member-ID", m.get("id", "").strip("{}"))]
            for kind, value in parts:
                if len(value) >= 3 and (kind, value.lower()) not in seen:
                    seen.add((kind, value.lower()))
                    patterns.append((kind, re.compile(r"(?<!\w)" + re.escape(value) + r"(?!\w)", re.IGNORECASE)))
    if not patterns:
        raise SystemExit("Keine mTeam.json gefunden – der Check kann die Namen nicht prüfen.")
    return patterns


def check_json(obj, path: str, findings: list[str], name: str) -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in FORBIDDEN_KEYS:
                findings.append(f"{name}: verbotener Schlüssel '{key}' bei {path or '/'}")
            check_json(value, f"{path}.{key}", findings, name)
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            check_json(value, f"{path}[{i}]", findings, name)
    elif isinstance(obj, str) and len(obj) > MAX_TEXT:
        findings.append(f"{name}: Text mit {len(obj)} Zeichen bei {path} (Grenze {MAX_TEXT})")


def check(folder: Path, repo: Path) -> list[str]:
    """Alle Funde im Ordner; leere Liste = in Ordnung."""
    findings: list[str] = []
    patterns = manager_patterns(repo)
    for path in sorted(p for p in folder.rglob("*") if p.is_file()):
        name = path.relative_to(folder).as_posix()
        if any(part.startswith(".") for part in name.split("/")) or ".lokal" in name:
            findings.append(f"{name}: versteckte oder lokale Datei")
            continue
        if path.suffix.lower() not in ALLOWED:
            findings.append(f"{name}: Dateityp {path.suffix or '(ohne)'} nicht erlaubt")
            continue
        if path.suffix.lower() not in TEXT:
            continue
        text = path.read_text(encoding="utf-8")
        for kind, rx in patterns:
            if rx.search(text):
                findings.append(f"{name}: enthält einen Manager-{kind}")
        if path.suffix.lower() == ".json":
            check_json(json.loads(text), "", findings, name)
    return findings


def main(argv: list[str]) -> int:
    folder = Path(argv[0]) if argv else Path("app")
    repo = Path(argv[1]) if len(argv) > 1 else Path(__file__).resolve().parent.parent
    findings = check(folder, repo)
    for f in findings:
        print("FUND:", f)
    print(f"{len(findings)} Fund(e) in {folder}")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
