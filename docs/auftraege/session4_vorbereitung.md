# Vorbereitung Session 4 – Methodik, Daten, App (28.09.2026, Beschlüsse Stephan)

Diese Seite ist die Grundlage für den Auftrag `session4.md`.
- **Erhoben:** Notion (Methodik, Record Book, Historie, Regeln; nur lesend), das ESPN-Datenangebot (nur lesend) sowie GitHub Pages und die Netzwerk-Freigabe in claude.ai (aktuelle Quellen).
- **Bewertet** haben zwei unabhängige Prüfer. Einer schaute fachlich-statistisch, der andere auf Datenwege und Aufwand.
- **Die vollständigen Berichte** liegen nur lokal unter `.lokal/session4/`, weil sie ein Inventar persönlicher Sichten enthalten.

## 1 Befunde, die alles Weitere prägen
- **Rauschen:** Eine Teamleistung schwankt von Woche zu Woche um σ ≈ 27–37 Punkte. Die echten Stärkeunterschiede der Teams liegen dagegen nur bei τ ≈ 13–18 (aus den Saisondaten 2015–2025). Kennzahlen aus ein bis drei Wochen messen deshalb vor allem Zufall. Die Stabilisierungskonstante k = σ²/τ² ≈ 3–4 Wochen.
- **Korrelation:** PF, All-Play, Floor, Form und Kader-Potenzial korrelieren nach W2 mit r ≥ 0,88.
- **ESPN-Saisonprojektion:** `102026` (statSplitTypeId 0, Quelle 1) ist schon der Rest der Saison und enthält NFL-W18. Die bisherige ROS-Formel in CLAUDE.md zieht das Ist deshalb doppelt ab.
- **Ist-Einträge:** ESPN legt für jeden Spieler einen Wochen-Ist-Eintrag an, auch für Inaktive. „Gespielt“ heißt `stats["210"] == 1`.
- **D/ST:** „Off. zugelassen 2025“ lässt sich aus ESPN exakt nachrechnen (32/32, Ligaschnitt 15,09). Ein Notion-Export ist dafür nicht nötig. ESPNs `positionAgainstOpponent` für D/ST ist 32/32 aus den eigenen Daten ableitbar und dient nur als Test.
- **Liga-Vorjahre bei ESPN** gibt es nur mit Login-Cookies. Die Historie stammt deshalb aus Notion (`data/history/`).
- **Playoff-Seeding:** ESPN setzt bisher nach W, dann PF (10/10 nach W2). Der Divisionssieger-Bye der nfl.com-Tradition ist in ESPN nicht belegt.
- **Unentschieden:** ESPN hat keinen Tiebreaker (`matchupTieRule: NONE`), Unentschieden sind also möglich.

## 2 Beschlossene Methodik für Baustein 4
Beschluss Stephan: alle Empfehlungen übernehmen, **außer dass Floor im Stärke-Profil gewichtet bleibt**. Bis zur Umsetzung gilt CLAUDE.md in der alten Fassung.

| Thema | Beschluss |
|---|---|
| Unentschieden | Win % = (W + 0,5·T)/G; All-Play-Gleichstand zählt 0,5; Luck = (W + 0,5·T) − All-Play-Anteil × G |
| Normierung | Standard z-Score, angezeigt als 50 + 10·z; Min–Max und Rangpunkte bleiben als Details; Hinweis zur Redundanz der Kennzahlen im Tooltip |
| Stärke-Profil | Win auf 0, **Floor bleibt**. Kader-Potenzial wird durch die Kader-Projektion ROS ersetzt, sobald sie vorliegt. **Offen:** wohin die frei werdenden 15 Punkte gehen (Session 4 fragt) |
| Power Ranking | Stärke μᵢ = (n·PF̄ᵢ + 4·Pᵢ)/(n + 4). Pᵢ = 0,98 × projektionsoptimale Aufstellung je Woche; ohne Projektion Pᵢ = L̄ + 0,6·(PF/Spiel Vorjahr − L̄ Vorjahr). Rang nach μ, dazu die erwartete All-Play-Quote Eᵢ = 1/9·Σⱼ Φ((μᵢ − μⱼ)/(σ√2)), σ gepoolt (≈ 35). **Rang, Trend und freigegebene Kernsätze sind öffentlich** |
| Form/Trend | Pfeil nur, wenn \|Form − Ø\| > max(1 Pkt., 15 % Ø, s·√(1/3 − 1/n)); bei n < 6 wird s als Positions-CV × Ø angesetzt. Form Δ im Team mit ±-Band |
| Spiele | Nur Einträge mit `stats["210"] == 1` zählen |
| ROS | Restwochen und Byes immer aus `nfl/proTeamSchedules_wl.json` bestimmen, Bye-Wochen = 0: ESPN projiziert D/ST auch in ihrer Bye-Woche Punkte (31 von 32, Prüfung 28.09.). ROS = Σ Wochenprojektionen n+1…14; ROS Playoffs = Σ W15–17; Restspiele ohne Bye; ROS/Spiel = ROS/Restspiele; W18 ignorieren. Ersatzniveau: Pool = WAIVERS + FREEAGENT ohne OUT/IR, Ø der drei besten nach ROS/Spiel. ROS über Ersatz gesamt = (ROS/Spiel − Ersatz) × Restspiele |
| Kader-Projektion | je Restwoche die projektionsoptimale Aufstellung (Byes, Verletzte) × Ligafaktor Σ PF/Σ Starter-Projektion (≈ 0,98); **nicht** × Coaching-Effizienz |
| Playoff-Simulation | k = 4 behalten. Je Lauf zuerst μ̃ᵢ ~ N(μᵢ, σ²/(n+k)), dann PF je Woche ~ N(μ̃ᵢ + (Pᵢ,w − P̄ᵢ), σ²) mit gepooltem σ. Seeding als Schalter (ESPN: W, dann PF; oder Divisionssieger auf 1–2). Ausgabe Playoff-, Division-, Bye-% und erwartete Restsiege, 10 000 Läufe; `mStandings` nur zum Vergleich. Der Restspielplan wird durch die erwarteten Restsiege ersetzt |
| D/ST-Faktor | F = (n·r₂₆ + 5·r₂₅ + 5·1,00)/(n + 10). Restspielplan und SoS W15–17 aus F; „nächste 3“ nach Kalenderwochen. Auslöser 2 an die Streuung koppeln (\|Δ\| ≥ 2·0,55·√(1/3 − 1/n) oder die drei größten z); Auslöser 1 (Δ ≥ 0,10) bleibt. Test gegen `docs/referenz_dst.md` (alte Formel) |
| Record Book | Luck als Zahl statt Etikett; Coaching sortiert nach Effizienz, Verschenkt als Nebenspalte; Positions-Breakdown nach `defaultPositionId`, Slot als Umschalter; RS und Playoffs getrennt; H2H nur W-L und PF-Differenz. All-Time zusätzlich mit W % und Ø PF+ (= 100 × PF/Ligaschnitt der Saison), Ära kennzeichnen; die Doppelwerte 313,33 (verifiziert) und 338,43 (unverifiziert) kennzeichnen |
| Bewusst nicht | Optimal-Algorithmus, All-Play, Median-Sieg und Standings-Tiebreak bleiben; ESPN `appliedTotal` gilt als Wahrheit. Kein Elo, keine SRS-Bereinigung in v1, keine eigenen Spielerprojektionen |

**Nicht aus Notion übernehmen:**
- die Divisionstabelle in Regelwerk §2 (Dynamo und gloane vertauscht): die Divisionen immer aus mTeam lesen
- „1/15 Passing-Yards“: seit 18.09. gilt 0,07 Punkte pro Yard

## 3 Daten (seit 28.09.2026 im Wochenabruf)
`espn_fetch.py --due` holt jetzt zusätzlich die folgenden Dateien. Rückwirkend geht nur, was ESPN liefert; alles andere erst ab jetzt.

| Datei | Inhalt | Takt |
|---|---|---|
| `wNN/kona_player_info.json` | ganzer Pool: Ist und Projektion der Woche, PPR-Ränge der Woche, Besitz, Verletzung, Status | beim Abschluss der Woche; nachgeholte Wochen (W1–W2, Catch-up) mit Besitz vom Nachholtag |
| `wNN/ros.json` | **Auszug:** Projektion je Restwoche und Spieler (Beschluss Stephan) | nur für die jüngste vergangene Woche, nicht rückwirkend |
| `wNN/mStandings.json` | ESPN-Simulation (Playoff-%, Division-%); ESPN ignoriert die angefragte Woche | nur für die jüngste vergangene Woche |
| `nfl/proTeamSchedules_wl.json` | NFL-Spielplan 2026 mit Byes und Gegnern | jeder Lauf, nur bei Änderung |
| `draft/mDraftDetail.json` | 240 Picks inklusive Keeper | einmalig |
| `basis/kona_dst_2025.json`, `basis/proTeamSchedules_wl_2025.json` | D/ST-Grundlage des Vorjahrs | einmalig |
| `data/history/*.csv` | Liga-Historie 2015–2025 ohne Manager (Beschluss Stephan) | einmalig |

**Noch nicht umgesetzt:**
- **mBoxscore statt mRoster:** −2,8 MB je Woche; `compute.py` muss dafür umgebaut werden.
- **Kuratierte Rekorde:** erst nach redaktioneller Durchsicht.
- **Trades vor 2026.**

## 4 App und Hosting
- **Deploy:** eigener `pages.yml` mit `actions/upload-pages-artifact@v5` und `actions/deploy-pages@v5`.
  - Auslöser: `push` (Pfade `app/**`, `data/*.json`), `workflow_run` nach Wochenabruf und Transaktions-Archiv (nur bei Erfolg) sowie `workflow_dispatch`.
  - „Deploy from a branch“ scheidet aus: Commits mit `GITHUB_TOKEN` lösen keinen Pages-Build aus, und erlaubt sind nur Root oder `/docs`.
  - Hochgeladen werden nur `app/` und die App-JSON, keine Rohdaten.
  - Pages lässt sich per `gh api` mit `build_type=workflow` einschalten (Freigabe Stephan).
- **Cache:** Pages liefert mit `max-age=600` aus. Die App lädt deshalb über `manifest.json` mit Hash bzw. Commit-SHA.
- **App-Daten:** `app/data/manifest.json`, `teams.json` (normierte Werte, damit die Regler im Browser rechnen), `schedule.json`, `players.json` (lädt erst beim Öffnen des Tabs), `dst.json`, `history.json`, `transactions.json`. Der erste Aufruf soll unter 20 KB gzip laden. Dazu kommt eine kompakte Datei unter 50 KB für Claude-Sessions unterwegs.
- **Sichtbarkeit:**
  - Die Pages-Seite ist öffentlich.
  - Ein Umstellen auf privat holt Veröffentlichtes nicht zurück (Forks, Archive). Auf GitHub Free geht die Seite dann offline.
  - Persönliche Sichten später nur in einem eigenen privaten Repo mit Zugriffsschutz, z. B. Cloudflare Workers + Access. **Nie** in dieses Repo.

## 5 Offen für Session 4
1. Verteilung der 15 frei werdenden Gewichtspunkte im Stärke-Profil.
2. Stat-Korrekturen: nach W4 lesend prüfen, ob sich W3-Punkte nach Dienstag geändert haben (Abgleich am 06.10.).
3. Bye-Markierung in Playoff-Wochen an echten Daten prüfen (Dezember).
4. Kuratierte Rekorde aus Notion (Details redigieren) und ggf. Trades vor 2026.
5. Netzwerk-Freigabe für Claude unterwegs (Stephan, Owner): `raw.githubusercontent.com` und `frest2101.github.io`.
6. Ältere Spielerdaten und D/ST (Frage Stephan 28.09.): ab 2018 über `leaguedefaults` mit Rohstats je Woche verfügbar, Punkte mit Liga-Scoring neu rechnen (siehe CLAUDE.md, ESPN-API). Nutzen z. B. mehrjährige D/ST-Grundlage, Spielerhistorie, Kalibrierung von k. Eigenes Arbeitspaket.
