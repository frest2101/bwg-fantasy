"""Einmaliger Import der DSGVO-Auskunft von Disney nach data/history: Wochen von Hugh Jass 2015–2017 und 2023–2025.

Quelle ist die eigene Auskunft bei Disney/ESPN (Lieferung 18.11.2026), ein ZIP lokal außerhalb des Repos. NFL Fantasy
ist zu ESPN gewechselt; unter nfl/ enthält die Auskunft deshalb die Wochen des eigenen Teams aus der nfl.com-Zeit
2015–2025. Das Repo ist öffentlich: Das Skript öffnet nur nfl/weekly_scores.csv (direkt aus dem ZIP, ohne zu
entpacken, oder aus dem entpackten Ordner), nimmt nur Zeilen der Liga „BWG Fantasy“ und des Teams „Hugh Jass“
(FILTER) und daraus nur die Spalten der Positivliste SPALTEN. Konto, Trades, Draft, Keeper, Waiver, Transaktionen,
Commissioner-Protokoll, Zugriffsprotokolle, andere Ligen und der Ordner espn/ werden nicht gelesen; Rohdateien kommen
nie ins Repo, auch nicht der Name des ZIP.

- Regular Season (Wochen 1 … rs_games laut seasons.csv): Punkte, Bank, PA = Differenz der kumulierten „Season points
  against“ zur Vorwoche, Ergebnis aus der Änderung der Bilanz „Record W-L-T“ (muss zur Spalte Result und zu den
  Punkten passen), Gegner nur, wo die Auskunft ihn nennt (2016), über den Teamnamen der Saison in team_seasons.csv.
- Playoff-Wochen (die drei Wochen danach, Phase PO wie in team_weeks.csv): nur Punkte und Bank – die Auskunft nennt
  weder Gegner noch Ergebnis, ein Bye in Runde 1 hat ebenfalls Punkte. Eine leere Woche dahinter (2016 W17 in einer
  Saison mit 16 Fantasy-Wochen) fällt weg.
- Prüfungen, Abbruch bei jeder Abweichung: je Saison Σ PF und letzte kumulierte PA = pf/pa und W-L = w/l in
  team_seasons.csv; 2018–2022 jede Woche wie team_weeks.csv (Punkte, Bank, Phase, Ergebnis) und die PA wie games.csv;
  2023–2025 die Regular Season wie hugh_jass_2023_2025.csv (PF, PA, Ergebnis); jedes Screenshot-Spiel von Hugh Jass in
  matchups_hist.csv mit den Punkten der Auskunft (in der Regular Season auch die PA).
- hugh_jass_2023_2025.csv schreibt seit dem 18.11.2026 dieses Skript (vorher nfl_export.py aus Snapshots ohne Bank
  und Playoffs); nfl_export.py --check prüft die Regular Season darin gegen die nfl.com-Snapshots – so prüfen sich
  beide Auskünfte gegenseitig. 2018–2022 stehen schon in team_weeks.csv und werden nur verglichen.

Aufruf: python scripts/disney_export.py <zip-oder-ordner> [--check]
  --check schreibt nichts und prüft nur, ob die Dateien in data/history der Auskunft entsprechen (Exit-Code 1 sonst).
"""

import argparse
import csv
import io
import sys
import zipfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

import espn_fetch as ef

MITGLIED = ("nfl", "weekly_scores.csv")          # einzige Datei, die das Skript öffnet
FILTER = {"League": "BWG Fantasy", "Team": "Hugh Jass"}
SPALTEN = ("Season", "Week", "Points", "Bench points", "Result", "Opponent", "Record W-L-T", "Season points against")
SAISONS = range(2015, 2026)                      # die nfl.com-Zeit der Liga; 2026 läuft bei ESPN (data/raw)
ALT = range(2015, 2018)                          # Alt-Scoring → hugh_jass_2015_2017.csv
NFL_EXPORT = range(2018, 2023)                   # stehen in team_weeks.csv (nfl.com-Auskunft), nur Vergleich
NEU = range(2023, 2026)                          # → hugh_jass_2023_2025.csv
SLOT = 2
PO_WOCHEN = 3
OHNE_GEGNER = "not in export"
KEIN_SPIEL = "no regular-season game"
AUS_BILANZ = " (from record)"                    # Disney hat das Ergebnis 2015/2016 selbst aus der Bilanz abgeleitet
ERGEBNIS = {"win": "W", "loss": "L", "tie": "T"}
CENT = Decimal("0.01")
RS, PO = "RS", "PO"
REGULAR = "Regular Season"

DATEI_ALT, DATEI_NEU = "hugh_jass_2015_2017.csv", "hugh_jass_2023_2025.csv"
SPALTEN_ALT = ("season", "week", "phase", "slot", "pts", "bench_pts", "pts_against", "opponent_slot", "result")
SPALTEN_NEU = ("season", "week", "phase", "slot", "pts", "bench_pts", "pts_against", "result")
QUELLE = (
    "# Quelle: DSGVO-Auskunft Disney (Lieferung 18.11.2026), nfl/weekly_scores.csv: Punkte und Bank je Woche, PA als",
    "# Differenz der kumulierten Season points against, Ergebnis aus der Bilanzänderung.",
)
KOPF_ALT = (
    "# Umfang: nur Hugh Jass (Slot 2) 2015–2017; Regular Season (Phase RS, 2015 W1–14, 2016/2017 W1–13) mit PA und",
    "# Ergebnis, Gegner (opponent_slot über den Teamnamen der Saison) nur 2016; Playoff-Wochen (Phase PO, je drei) nur",
    "# mit Punkten und Bank, ohne Gegner und Ergebnis. Ohne All-Play.",
    *QUELLE,
    "# Alt-Scoring 2015–2017: nie mit den Werten ab 2018 (BWG-Scoring) oder ab 2026 (ESPN) mischen.",
)
KOPF_NEU = (
    "# Umfang: nur Hugh Jass (Slot 2) 2023–2025; Regular Season (Phase RS, je 14 Wochen) mit PA und Ergebnis, ohne",
    "# Gegner; Playoff-Wochen 15–17 (Phase PO) nur mit Punkten und Bank, ohne Gegner und Ergebnis. Ohne All-Play.",
    *QUELLE,
    "# Gegenprobe: Die Snapshots der nfl.com-Auskunft (Export 24.09.2026) ergeben in allen 42 Wochen der Regular Season",
    "# dieselben PF, PA und Ergebnisse (scripts/nfl_export.py --check).",
)


class ImportFehler(Exception):
    """Die Auskunft passt nicht zu den Annahmen oder zu data/history; nichts wird geschrieben."""


# ---------------------------------------------------------------- Lesen

def _ist_mitglied(name: str) -> bool:
    """nfl/weekly_scores.csv auf oberster Ebene oder eine Ordnerebene tiefer (der Ordner, den Disney ins ZIP legt)."""
    parts = name.replace("\\", "/").split("/")
    return tuple(parts[-2:]) == MITGLIED and len(parts) <= 3


def quelltext(path: Path) -> str:
    """Inhalt von nfl/weekly_scores.csv aus dem ZIP (nur dieses Mitglied wird gelesen) oder aus dem entpackten Ordner."""
    if path.is_file() and zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            hits = [n for n in z.namelist() if _ist_mitglied(n)]
            if len(hits) != 1:
                raise ImportFehler(f"{'/'.join(MITGLIED)}: {len(hits)} Treffer im ZIP")
            data = z.read(hits[0])
    elif path.is_dir():
        hits = [p for p in (path.joinpath(*MITGLIED), *path.glob("*/" + "/".join(MITGLIED))) if p.is_file()]
        if len(hits) != 1:
            raise ImportFehler(f"{'/'.join(MITGLIED)}: {len(hits)} Treffer im Ordner")
        data = hits[0].read_bytes()
    else:
        raise ImportFehler(f"weder ZIP noch Ordner: {path}")
    return data.decode("utf-8-sig")


def zeilen(text: str) -> list[dict]:
    """Zeilen der Liga BWG Fantasy und des Teams Hugh Jass, nur mit den Spalten der Positivliste."""
    reader = csv.DictReader(io.StringIO(text))
    missing = [c for c in (*FILTER, *SPALTEN) if c not in (reader.fieldnames or [])]
    if missing:
        raise ImportFehler(f"Spalten fehlen: {', '.join(missing)}")
    return [{c: r[c] for c in SPALTEN} for r in reader if all(r[k] == v for k, v in FILTER.items())]


def points(text: str) -> Decimal:
    """Punkte als Decimal; leer oder mehr als zwei Stellen bricht ab (keine stille Rundung)."""
    try:
        value = Decimal(text)
    except InvalidOperation:
        raise ImportFehler(f"kein Punktwert: „{text}“") from None
    if value != value.quantize(CENT):
        raise ImportFehler(f"Punktwert mit mehr als zwei Stellen: {text}")
    return value


def bilanz(text: str) -> tuple[int, int, int]:
    """„W-L-T“ als Zahlen."""
    parts = text.split("-")
    if len(parts) != 3 or not all(p.isdigit() for p in parts):
        raise ImportFehler(f"keine Bilanz: „{text}“")
    return int(parts[0]), int(parts[1]), int(parts[2])


def read_csv(path: Path) -> list[dict]:
    """CSV aus data/history; Kopfzeilen „# …“ (Umfang der Datei) fallen weg."""
    with open(path, encoding="utf-8", newline="") as f:
        return list(csv.DictReader(line for line in f if not line.startswith("#")))


# ---------------------------------------------------------------- Wochen

def gegner(text: str, season: int, names: dict[tuple[int, int], str]) -> int | None:
    """Slot des Gegners über den Teamnamen der Saison (team_seasons.csv); „not in export“ = unbekannt."""
    if text == OHNE_GEGNER:
        return None
    hits = [slot for (s, slot), name in names.items() if s == season and name == text]
    if len(hits) != 1 or hits[0] == SLOT:
        raise ImportFehler(f"Gegner {season} nicht eindeutig zuzuordnen ({len(hits)} Treffer)")
    return hits[0]


def saison_wochen(season: int, weeks: dict[int, dict], n_rs: int, names: dict) -> list[dict]:
    """Wochen einer Saison: Regular Season mit PA, Ergebnis und (wo genannt) Gegner, danach drei Playoff-Wochen."""
    last = n_rs + PO_WOCHEN
    missing = sorted(set(range(1, last + 1)) - set(weeks))
    if missing:
        raise ImportFehler(f"{season}: Wochen fehlen: {missing}")
    for week in sorted(set(weeks) - set(range(1, last + 1))):
        r = weeks[week]
        if r["Points"] or r["Bench points"] or r["Result"] != KEIN_SPIEL:
            raise ImportFehler(f"{season} W{week}: Punkte nach der letzten Playoff-Woche")
    result, rec_before, pa_before = [], (0, 0, 0), Decimal(0)
    for week in range(1, last + 1):
        r = weeks[week]
        row = {"season": season, "week": week, "slot": SLOT, "pts": points(r["Points"]),
               "bench_pts": points(r["Bench points"])}
        if week <= n_rs:
            rec, pa_cum = bilanz(r["Record W-L-T"]), points(r["Season points against"])
            step = tuple(now - before for now, before in zip(rec, rec_before))
            if sorted(step) != [0, 0, 1]:
                raise ImportFehler(f"{season} W{week}: Bilanz ändert sich nicht um genau ein Spiel")
            res = "WLT"[step.index(1)]
            if ERGEBNIS.get(r["Result"].removesuffix(AUS_BILANZ)) != res:
                raise ImportFehler(f"{season} W{week}: Result passt nicht zur Bilanz")
            pa = pa_cum - pa_before
            if res != ("W" if row["pts"] > pa else "L" if row["pts"] < pa else "T"):
                raise ImportFehler(f"{season} W{week}: Ergebnis passt nicht zu den Punkten")
            row.update(phase=RS, pts_against=pa, opponent_slot=gegner(r["Opponent"], season, names), result=res)
            rec_before, pa_before = rec, pa_cum
        else:
            if (r["Result"], r["Record W-L-T"], r["Season points against"], r["Opponent"]) != \
                    (KEIN_SPIEL, "--", "", OHNE_GEGNER):
                raise ImportFehler(f"{season} W{week}: Playoff-Woche mit Bilanz, PA, Ergebnis oder Gegner")
            row.update(phase=PO, pts_against=None, opponent_slot=None, result=None)
        result.append(row)
    return result


def alle_wochen(rows: list[dict], rs_games: dict[int, int], names: dict) -> dict[int, list[dict]]:
    """Je Saison 2015–2025 die Wochen von Hugh Jass; jede Woche genau einmal."""
    by_season = defaultdict(dict)
    for r in rows:
        season, week = int(r["Season"]), int(r["Week"])
        if week in by_season[season]:
            raise ImportFehler(f"{season} W{week} doppelt")
        by_season[season][week] = r
    if sorted(by_season) != list(SAISONS):
        raise ImportFehler(f"Saisons {sorted(by_season)} statt {SAISONS.start}–{SAISONS.stop - 1}")
    return {season: saison_wochen(season, by_season[season], rs_games[season], names) for season in SAISONS}


# ---------------------------------------------------------------- Prüfung gegen data/history

def check_saisons(wochen: dict[int, list[dict]], seasons_rows: list[dict]) -> None:
    """Je Saison: Σ PF und letzte kumulierte PA (= Σ PA der Wochen) wie pf/pa, W-L wie w/l in team_seasons.csv."""
    for season, mine in wochen.items():
        rs = [w for w in mine if w["phase"] == RS]
        t = next((r for r in seasons_rows if (int(r["season"]), int(r["slot"])) == (season, SLOT)), None)
        if t is None:
            raise ImportFehler(f"{season}: Hugh Jass fehlt in team_seasons.csv")
        got = (sum((w["pts"] for w in rs), Decimal(0)), sum((w["pts_against"] for w in rs), Decimal(0)),
               sum(w["result"] == "W" for w in rs), sum(w["result"] == "L" for w in rs), len(rs))
        if got != (Decimal(t["pf"]), Decimal(t["pa"]), int(t["w"]), int(t["l"]), int(t["w"]) + int(t["l"])):
            raise ImportFehler(f"{season}: PF/PA/Bilanz weichen von team_seasons.csv ab")


def check_team_weeks(wochen: dict[int, list[dict]], team_weeks: list[dict], games: list[dict]) -> None:
    """2018–2022: jede Woche wie team_weeks.csv (Slot 2: Phase, Punkte, Bank, Ergebnis), PA wie games.csv."""
    tw = {(int(r["season"]), int(r["week"])): r for r in team_weeks if int(r["slot"]) == SLOT}
    pa = {(int(g["season"]), int(g["week"])): Decimal(g["pts_b"] if int(g["slot_a"]) == SLOT else g["pts_a"])
          for g in games if g["round"] == REGULAR and SLOT in (int(g["slot_a"]), int(g["slot_b"]))}
    for season in NFL_EXPORT:
        mine = {(season, w["week"]): w for w in wochen[season]}
        if set(mine) != {k for k in tw if k[0] == season}:
            raise ImportFehler(f"{season}: andere Wochen als team_weeks.csv")
        for key, w in mine.items():
            r = tw[key]
            if (w["phase"], w["pts"], w["bench_pts"], w["result"] or "") != \
                    (r["phase"], Decimal(r["pts"]), Decimal(r["bench_pts"]), r["result"]):
                raise ImportFehler(f"{season} W{key[1]}: weicht von team_weeks.csv ab")
            if w["phase"] == RS and w["pts_against"] != pa.get(key):
                raise ImportFehler(f"{season} W{key[1]}: PA weicht von games.csv ab")


def check_hugh_jass_datei(wochen: dict[int, list[dict]], file_rows: list[dict]) -> None:
    """2023–2025: die Regular Season wie in hugh_jass_2023_2025.csv (PF, PA, Ergebnis). Eine Datei ohne Spalte phase
    (Stand vor dem 18.11.2026) führt nur die Regular Season."""
    got = {(w["season"], w["week"]): (w["pts"], w["pts_against"], w["result"])
           for season in NEU for w in wochen[season] if w["phase"] == RS}
    have = {(int(r["season"]), int(r["week"])): (Decimal(r["pts"]), Decimal(r["pts_against"]), r["result"])
            for r in file_rows if r.get("phase", RS) == RS and int(r["slot"]) == SLOT}
    if got != have:
        off = sorted(set(got) ^ set(have) | {k for k in got.keys() & have.keys() if got[k] != have[k]})
        raise ImportFehler(f"2023–2025: weicht von {DATEI_NEU} ab ({', '.join(f'{s} W{w}' for s, w in off)})")


def check_screenshots(wochen: dict[int, list[dict]], screenshots: list[dict]) -> None:
    """Jedes Screenshot-Spiel von Hugh Jass: dessen Punkte wie in der Auskunft, in der Regular Season auch die PA."""
    by_key = {(s, w["week"]): w for s, mine in wochen.items() for w in mine}
    for m in screenshots:
        slots = (int(m["slot_a"]), int(m["slot_b"]))
        if SLOT not in slots:
            continue
        season, week = int(m["season"]), int(m["week"])
        w = by_key.get((season, week))
        mine, other = (m["pts_a"], m["pts_b"]) if slots[0] == SLOT else (m["pts_b"], m["pts_a"])
        if w is None or Decimal(mine) != w["pts"] or (w["phase"] == RS and Decimal(other) != w["pts_against"]):
            raise ImportFehler(f"Screenshot-Spiel {season} W{week}: Punkte weichen von der Auskunft ab")


# ---------------------------------------------------------------- Schreiben

def cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    return str(value)


def to_csv(columns: tuple, rows: list[dict], head: tuple) -> str:
    out = io.StringIO()
    for line in head:
        out.write(line + "\n")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(columns)
    for r in rows:
        writer.writerow([cell(r[c]) for c in columns])
    return out.getvalue()


def build(source: Path) -> dict[str, str]:
    """Beide Ausgabedateien als Text (Dateiname → Inhalt); prüft vorher alles, was der Auftrag verlangt."""
    history = ef.REPO_DIR / "data" / "history"
    seasons_rows = read_csv(history / "team_seasons.csv")
    names = {(int(r["season"]), int(r["slot"])): r["team_name"] for r in seasons_rows}
    rs_games = {int(r["season"]): int(r["rs_games"]) for r in read_csv(history / "seasons.csv")}

    wochen = alle_wochen(zeilen(quelltext(source)), rs_games, names)
    check_saisons(wochen, seasons_rows)
    check_team_weeks(wochen, read_csv(history / "team_weeks.csv"), read_csv(history / "games.csv"))
    check_hugh_jass_datei(wochen, read_csv(history / DATEI_NEU))
    check_screenshots(wochen, read_csv(history / "matchups_hist.csv"))
    return {
        DATEI_ALT: to_csv(SPALTEN_ALT, [w for s in ALT for w in wochen[s]], KOPF_ALT),
        DATEI_NEU: to_csv(SPALTEN_NEU, [w for s in NEU for w in wochen[s]], KOPF_NEU),
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="DSGVO-Auskunft Disney → data/history (Hugh Jass 2015–2017, 2023–2025)")
    parser.add_argument("quelle", type=Path, help="ZIP der Auskunft oder entpackter Ordner (außerhalb des Repos)")
    parser.add_argument("--check", action="store_true", help="nichts schreiben, nur mit data/history vergleichen")
    args = parser.parse_args(argv)
    try:
        files = build(args.quelle)
    except ImportFehler as e:
        print(f"Abbruch: {e}", file=sys.stderr)
        return 1
    history = ef.REPO_DIR / "data" / "history"
    if args.check:
        stale = [name for name, text in files.items()
                 if not (history / name).exists() or (history / name).read_text(encoding="utf-8") != text]
        print("aktuell" if not stale else f"weicht ab: {', '.join(stale)}")
        return 1 if stale else 0
    for name, text in files.items():
        (history / name).write_text(text, encoding="utf-8", newline="\n")
        rows = sum(1 for line in text.splitlines() if not line.startswith("#")) - 1
        print(f"geschrieben: data/history/{name} ({rows} Zeilen)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
