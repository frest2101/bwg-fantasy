# bwg-fantasy

Rechenwerk für die BWG Fantasy Liga (ESPN-Liga 1166555857): holt die Ligadaten nur lesend von ESPN, berechnet daraus Standings und Kennzahlen und zeigt sie später als statische Web-Seite.
Einrichten mit `python -m pip install --user -r requirements.txt`, Rohdaten abrufen mit `python scripts/espn_fetch.py --weeks 1 2 3` und kontrollieren mit `python scripts/espn_fetch.py --summary`.
Regeln, Entscheidungen und Historie der Liga liegen in Notion, die Arbeitsregeln für dieses Repo in `CLAUDE.md`.
