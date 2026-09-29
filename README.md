# bwg-fantasy

Rechenwerk für die BWG Fantasy Liga (ESPN-Liga 1166555857): holt die Ligadaten nur lesend von ESPN, berechnet daraus Standings und Kennzahlen und zeigt sie als statische Web-Seite: **https://frest2101.github.io/bwg-fantasy/**
Einrichten mit `python -m pip install --user -r requirements.txt`, Rohdaten holt der Wochenabruf (von Hand nur zum Testen: `python scripts/espn_fetch.py --weeks 1 2 3`, Kontrolle: `--summary`), Kennzahlen und App-Daten rechnen mit `python scripts/compute.py` und prüfen mit `python -m pytest`.
Regeln, Entscheidungen und Historie der Liga liegen in Notion, die Arbeitsregeln und Rechenregeln für dieses Repo in `CLAUDE.md`.

## App
- Die Seite besteht aus `app/` (HTML, CSS, JavaScript ohne Framework) und den App-Daten `app/data/*.json`, die `compute.py` schreibt. Aufbau der Daten: `docs/app_daten.md`.
- Tabelle › All-Play, Punkte und Coaching gibt es auch je Einzelwoche (Chips „Saison · W1 · W2 …“, z. B. `#tabelle/allplay/w3`); dort steht je Team das Matchup-Glück der Woche mit Begründung (Sieg unter dem Wochenmedian = Glück, Niederlage über dem Median = Pech).
- Lokale Vorschau: `python -m http.server 8000 --directory app`, dann http://localhost:8000 öffnen.
- Für Claude-Sessions unterwegs gibt es die kompakte Datei `app/data/claude.json` (unter 50 KB), abrufbar unter https://raw.githubusercontent.com/frest2101/bwg-fantasy/main/app/data/claude.json.
- Öffentlich sind nur Ligadaten: `scripts/check_public.py` prüft vor jedem Commit und vor jeder Veröffentlichung, dass keine Manager-Namen, ESPN-Texte oder Chat in der App stehen.

## Automatik (GitHub Actions)
- **Wochenabruf** (`.github/workflows/wochenabruf.yml`): dienstags 08:30 UTC, Nachläufe Di 16:30 und Mi 08:30 UTC.
  - Er holt jede vergangene Woche, die im Repo fehlt oder noch nicht final ist (`espn_fetch.py --due`), samt Spielerpool, ROS-Auszug und ESPN-Standings der Woche.
  - Dazu kommen der NFL-Spielplan und einmalig Draft und D/ST-Grundlage des Vorjahrs.
  - Danach rechnet er (`compute.py`), testet (`pytest`) und committet nur bei Änderung. Rohdaten kommen immer ins Repo, die abgeleiteten Dateien nur bei grünem Rechenwerk und grünen Tests.
- **Liga-Historie 2015–2025:** einmaliger Export aus Notion in `data/history/` (siehe README dort).
- **Tageslauf** (`.github/workflows/tageslauf.yml`): stündlich 06:45–11:45 UTC (trifft die Waiver-Ergebnisse, die in der ESPN-App erst gegen 10:30–11:00 Uhr sichtbar werden) und 15:40–21:40 UTC (News-Zeit, sonntags die Inactives). Jeder Lauf (`espn_fetch.py --transactions --pool --wetter`) sichert `mTransactions2` je Periode und `kona_league_communication` (ohne Chat) nach `data/raw/2026/transactions/`, den Pool-Auszug `pool/latest.json` (Status, Besitz, Verletzung, Waiver-Frist, Projektion je Spieler) und das Wetter je Spiel aus Open-Meteo (`wetter/prognose/` für die laufende Woche, `wetter/ist_2026.json` dauerhaft; Spielorte aus `nfl/stadien.json`) und rechnet danach die App-Daten neu. News je Spieler (`--news`) ist vorbereitet, aber aus.
- **Probe** (`.github/workflows/probe.yml`): nur von Hand, ohne Commit – fragt Open-Meteo und die ESPN-Site-API ab und zeigt die Antworten im Log (`scripts/probe.py`).
- **Pages** (`.github/workflows/pages.yml`): veröffentlicht `app/` nach jedem erfolgreichen Datenlauf und bei Änderungen an der App.
- Alle lassen sich unter *Actions › Run workflow* oder mit `gh workflow run` von Hand starten. Schlägt ein Lauf fehl, schickt GitHub eine Mail.
- Die Actions sind per Commit-SHA gepinnt; Dependabot schlägt monatlich Updates vor.
- Die Actions committen auf `main`: **vor lokaler Arbeit `git pull`**.
- In der Offseason schaltet GitHub geplante Workflows nach 60 Tagen ohne Commit ab. Vor dem Saisonstart gilt die Checkliste „Saisonwechsel“ in `CLAUDE.md`.
