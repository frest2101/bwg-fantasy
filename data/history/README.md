# Liga-Historie 2015–2025 (einmaliger Export aus Notion, 28.09.2026)

Die ESPN-Saisons vor 2026 sind ohne Login nicht abrufbar. Quelle ist deshalb das Notion-Ligaarchiv (DBs Saisondaten, Saisons, Franchises, Matchups). Die Daten wurden nur lesend per SQL geholt und gegen Summen je Franchise aus Notion geprüft (`tests/test_history.py`). Schlüssel ist immer der Franchise-Slot 1–10, der der mTeam-ID bei ESPN entspricht.

| Datei | Inhalt |
|---|---|
| `team_seasons.csv` | 108 Zeilen: je Saison und Franchise Teamname, Division, Platz in der Division, W, L, PF, PA (nur Regular Season), Endplatz (1–6 aus dem Bracket, danach aus der Trostrunde), Playoff-Teilnahme, Scoring-Titel (meiste PF der Regular Season) |
| `seasons.csv` | Format je Saison: Plattform, Teams, Spiele der Regular Season, Scoring-Ära, QB-Format, Keeper-Modus, Divisionen, Playoff-Format, Draft-Termin (UTC) |
| `franchises.csv` | Namenskette je Slot |
| `matchups_hist.csv` | Die 8 belegten Einzelspiele vor 2026 (Screenshots). Status `live` bzw. `partial` bedeutet: Der Sieger ist belegt, die Punkte sind aber nicht endgültig. Solche Spiele zählen nie für Rekorde. |

**Hinweise:**
- Alt-Scoring 2015–2017 ergibt deutlich weniger Punkte als das BWG-Scoring ab 2018. Die Regular Season hatte 2016–2020 13 Spiele, sonst 14. Rekorde über Saisons hinweg deshalb nach Ära trennen oder relativ zum Ligaschnitt rechnen.
- 2015 lief mit 8 Teams, die Slots 1 und 10 kamen 2016 dazu.
- Titel, Finals, Divisionssiege und Letzte rechnet der Code aus Endplatz und Division.

**Bewusst nicht exportiert** (Entscheidung Stephan 28.09.2026: Historie ohne Manager): Manager-Namen und -Zeiträume, Manager-Kontext, Autopick-Neigung, der Rohtext der Regeländerungen (enthält Namen, Abstimmungsverhalten und Chat-Bezüge), Quellenangaben mit Chat-Bezug, Screenshot-Dateinamen, Trades samt Notizen. Die Rekorde-DB folgt nach redaktioneller Durchsicht.
