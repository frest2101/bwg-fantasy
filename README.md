# bwg-fantasy

Rechenwerk für die BWG Fantasy Liga (ESPN-Liga 1166555857): holt die Ligadaten nur lesend von ESPN, berechnet daraus Standings und Kennzahlen und zeigt sie später als statische Web-Seite.
Einrichten mit `python -m pip install --user -r requirements.txt`, Rohdaten holt der Wochenabruf (von Hand nur zum Testen: `python scripts/espn_fetch.py --weeks 1 2 3`, Kontrolle: `--summary`), Kennzahlen rechnen mit `python scripts/compute.py` und prüfen mit `python -m pytest`.
Regeln, Entscheidungen und Historie der Liga liegen in Notion, die Arbeitsregeln für dieses Repo in `CLAUDE.md`.

## Automatik (GitHub Actions)
- **Wochenabruf** (`.github/workflows/wochenabruf.yml`): dienstags 08:30 UTC, Nachläufe Di 16:30 und Mi 08:30 UTC.
  - Er holt jede vergangene Woche, die im Repo fehlt oder noch nicht final ist (`espn_fetch.py --due`), samt Spielerpool, ROS-Auszug und ESPN-Standings der Woche.
  - Dazu kommen der NFL-Spielplan und einmalig Draft und D/ST-Grundlage des Vorjahrs.
  - Danach rechnet er (`compute.py`), testet (`pytest`) und committet nur bei Änderung.
- **Liga-Historie 2015–2025:** einmaliger Export aus Notion in `data/history/` (siehe README dort).
- **Transaktions-Archiv** (`.github/workflows/transaktionen.yml`): täglich 05:17 UTC. Es sichert `mTransactions2` je Periode und `kona_league_communication` (ohne Chat) nach `data/raw/2026/transactions/` (`espn_fetch.py --transactions`).
- Beide lassen sich unter *Actions › Run workflow* oder mit `gh workflow run` von Hand starten. Schlägt ein Lauf fehl, schickt GitHub eine Mail.
- Die Actions committen auf `main`: **vor lokaler Arbeit `git pull`**.
- In der Offseason schaltet GitHub geplante Workflows nach 60 Tagen ohne Commit ab. Vor dem Saisonstart gilt die Checkliste „Saisonwechsel“ in `CLAUDE.md`.
