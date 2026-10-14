# Kernsätze Power Ranking – Ablauf der Routine

Stand 14.10.2026. Gilt für die Routine „BWG Fantasy – Kernsätze Power Ranking (Di/Mi)“ (claude.ai, frische Cloud-Sitzung, dienstags und mittwochs 12:47 Uhr deutscher Zeit) und für jede Sitzung, die die Kernsätze von Hand schreibt. Grundlage: Dauerfreigabe Stephan vom 13.10.2026 (CLAUDE.md, Gelernt „Kernsätze mit Dauerfreigabe“). Vorbild ist W5 ([PR #79](https://github.com/frest2101/bwg-fantasy/pull/79)).

Der Lauf ist unbeaufsichtigt: keine Rückfragen. Was sich nicht sicher klären lässt, wird weggelassen (die App zeigt dann „folgt“) und in der Zusammenfassung genannt. Nie: Manager-Namen schreiben oder ausgeben (auch nicht in Logs, Prüfberichten oder der Zusammenfassung), nach Notion oder ESPN schreiben, Rohdaten abrufen oder committen, Pakete installieren, force-push, andere Dateien als die unten genannten ändern.

## 1. Ist etwas zu tun?

1. `git fetch origin main`, Arbeitszweig von `origin/main` (den Branch, den die Sitzung vorgibt, sonst `claude/kernsaetze-wNN`).
2. `N = through_week` aus `data/season_2026.json` (bei einer neuen Saison die Datei der Saison). Kernsätze gibt es für W3 bis W14; das Power Ranking bleibt in den Playoffs bei W14.
3. Wochenabruf grün? Der letzte Lauf von `wochenabruf.yml` auf `main` muss `success` sein, und `app/data/manifest.json › through_week` muss N sein. Ist er rot oder läuft er noch: nichts schreiben, melden.
4. Fehlen in `data/redaktion/power_ranking_<Saison>.csv` Zeilen der Woche N (Slots 1–10, Slot = Team-ID): weiter mit 2.
5. Stat-Korrekturen: Hat sich seit dem letzten Commit an der CSV eine `data/raw/<Saison>/wNN/statkorrektur.json` geändert (`git log <letzter CSV-Commit>..origin/main -- 'data/raw/<Saison>/w*/statkorrektur.json'`), dann alle Kernsätze ab der ältesten betroffenen Woche gegen die neuen Zahlen prüfen (Schritt 4) und nachziehen: nur die Zahl, wenn die Aussage hält, sonst den Satz umschreiben (Dauerfreigabe gilt auch dafür).
6. Sonst ist nichts zu tun: Ende ohne Commit, eine Zeile Ergebnis. Ist `manifest.json › datenstand.playoff_woche` 17 (Saison vorbei), dazu: „Saison vorbei – die Routine kann pausiert werden.“

## 2. Faktenzettel

Alle Zahlen kommen aus dem Rechenwerk (ungerundet, `Decimal`) und den Rohdaten mit Stat-Korrektur, nie aus Erinnerung oder Vorwochen-Sätzen. Hilfsskripte liegen außerhalb des Repos (Scratchpad).

```python
import sys; sys.path.insert(0, "scripts")
import compute, rawdata
sN, sV = compute.compute_season(through=N), compute.compute_season(through=N - 1)
# je Team: sN["teams"] (rang = Tabellenplatz), sN["team_weeks"] (pf, pa, opponent_id, result, wochenrang,
#   optimal, verschenkt, median_win, matchup_glueck, allplay_w/l/t), sN["weeks"] (high, low, median, top_team_id),
#   sN["power_ranking"]["teams"][t] (mu, rang, rang_vorwoche, trend, p = Projektion Kader, e, verlauf),
#   sN["power_ranking"]["sim"]["liga"][t] (playoff, division, bye, restsiege); Vorwoche genauso aus sV
ssn = rawdata.Season(2026, N)
# Spieler der Woche: ssn.roster(N) (team_id, slot, name, actual); Starter = slot nicht 20 (Bank) und nicht 21 (IR)
# Spieler-Wochenwerte aller Wochen für Superlative: ssn.pool(w) und ssn.roster(w), w = 1 … N
```

Superlative („höchster“, „einziges Team“, „erstmals“, „in Folge“, „größter Anstieg“) immer über alle zehn Teams und alle Wochen W1–N rechnen. Stärke und Projektion Kader erst als Differenz der ungerundeten Werte runden; weicht die Differenz der angezeigten Werte ab, beide Werte nennen („von 215,0 auf 220,8“) statt der Differenz.

## 3. Entwurf

Zehn Sätze, je Team einer (Slot = Team-ID: 1 Asse's Cowboys · 2 Hugh Jass · 3 4th Down Syndrom · 4 cool runnings · 5 TeamTy · 6 SaschaM · 7 Rotzleffe · 8 gloane saubande · 9 Dynamo · 10 SaureGurken – genau diese Schreibweisen).

- Nur Teamnamen und NFL-Spielernamen (wie in den Daten). Keine Manager-Namen, keine Absichten oder Pläne („will“, „muss jetzt“), keine Empfehlungen, kein Start/Sit, keine Urteile über Personen oder ihr Coaching; neutral für alle zehn Teams.
- Jede Aussage aus dem Faktenzettel belegbar. Nichts über die Zukunft außer den Zahlen der Simulation (Playoff-Chance, Division, Bye).
- Jeder Satz verbindet das Wochenergebnis mit der Lage im Power Ranking (Stärke, Rang und Trend, Projektion Kader oder Playoff-Chance); kein Widerspruch zu Rang und Trend des Teams; nicht zehnmal dasselbe Muster; Inhalte der Vorwoche nur als bewusster Vergleich.
- Ein bis zwei Sätze, etwa 110–195 Zeichen.
- Zahlenformat der App: Dezimalkomma; Teampunkte (PF, PA, verschenkt, Abstände) zwei Stellen (202,24 · 5,00); Spielerpunkte exakt ohne nachgestellte Null (46,2 · 36,55); Stärke und Projektion Kader eine Stelle; Playoff-Chance ganze Prozent mit schmalem geschütztem Leerzeichen (U+202F) vor „%“; round half up erst bei der Ausgabe.
- Begriffe der App: „Stärke“ (μ), „Projektion Kader“, „Playoff-Chance“, „Wochenrang“, „Wochenbestwert“, „Wochenletzter“, „verschenkt“, „beste Aufstellung“, „Wochenmedian“, „Matchup-Glück“, „All-Play“, „Tabelle“ bzw. „Platz“ im Power Ranking. „Saisonbestwert“ meint Teampunkte, für Spieler „höchste Einzelleistung der Saison“.

## 4. Prüfung

Entwurf und Prüfung bleiben getrennt, weil niemand mehr gegenliest.

1. Drei Prüfer parallel (Agent-Werkzeug), jeder mit eigener Linse und ohne die Belege des Entwurfs; sie rechnen selbst mit python3 aus den Dateien nach:
   - **Zahlen:** jede Zahl, Rundung, Format, Zuordnung (Team, Woche, Gegner, Starter oder Bank), „von … auf …“ gegen die Vorwoche.
   - **Superlative und Vergleiche:** über alle Teams und W1–N, dazu Widersprüche zwischen den zehn Sätzen und zu Rang und Trend.
   - **Regeln und Stil:** Abschnitt 3, Länge, Begriffe, Rechtschreibung; Manager-Namen nur per Abgleich mit `data/raw/<Saison>/wNN/mTeam.json › members` (`firstName`, `lastName`, `displayName`) und nur als „Slot n: Treffer“ melden, nie den Namen.
2. Jeden Befund selbst nachrechnen (Prüfer können irren), dann einarbeiten.
3. Eigene Gegenprüfung: ein Skript, das jede Aussage der Endfassung als eine Prüfung ausdrückt (W5: 47 Prüfungen, alle grün), dazu der Manager-Abgleich ohne Ausgabe der Namen. Was nicht grün wird, umschreiben oder den Slot weglassen.

## 5. Schreiben, prüfen, mergen

1. Zeilen `N,<slot>,"<Satz>"` an die CSV anhängen (UTF-8, Zeilenende `\n`, Text in doppelten Anführungszeichen, kein `"` im Text).
2. `python3 scripts/compute.py`, dann `pytest` (hat das System-Python kein pytest: `PYTHONPATH=$(ls -d /root/.local/share/uv/tools/pytest/lib/python3*/site-packages) python3 -m pytest -q`; gibt es keins, nichts installieren, sondern abbrechen und melden), dann `python3 scripts/check_public.py`. Alles muss grün sein.
3. Diff prüfen: `app/data/teams.json` ändert sich nur in `kernsatz`-Feldern, `app/data/manifest.json` nur in der Zeile von `teams.json`. Sonst nichts committen und melden.
4. Nur diese drei Dateien stagen (`git add <datei>`), `git diff --cached --stat` prüfen, Commit-Text Deutsch in einem Satz („Power Ranking WN: Kernsätze …“).
5. `main` nachziehen (`git fetch origin main && git merge origin/main`); ändert sich dabei etwas, `compute.py` und `pytest` wiederholen.
6. Pushen, Pull Request anlegen (Titel „Power Ranking WN: Kernsätze“) und sofort mergen (Merge-Commit, mit vollem Head-SHA). Fehlt das Recht oder Werkzeug zum Mergen: Branch gepusht lassen und melden.
7. Pages: Der Lauf von `pages.yml` zum Merge-Commit muss grün werden, und `https://frest2101.github.io/bwg-fantasy/data/manifest.json` muss die neue Version von `teams.json` tragen. Hängt Pages (CLAUDE.md, Gelernt „Pages-Hänger“), nichts abbrechen, sondern melden.

## 6. Zusammenfassung

Deutsch, kurz, ohne Manager-Namen: Woche, die zehn Sätze in der Reihenfolge des Power Rankings, Link zum Pull Request, Zahl der Prüfungen, weggelassene Slots mit Grund, nachgezogene Sätze nach Stat-Korrekturen und Auffälligkeiten (rote Läufe, Pages). War nichts zu tun: eine Zeile mit dem Grund.

## Anhang: Routine

Anlegen in claude.ai (Routinen) macht Stephan, weil der Auto-Modus `create_trigger` am 14.10.2026 ablehnte. Name „BWG Fantasy – Kernsätze Power Ranking (Di/Mi)“, Zeitplan dienstags und mittwochs 12:47 Uhr Europe/Berlin (cron `47 12 * * 2,3`), bei jedem Lauf eine neue Sitzung in der Cloud-Umgebung dieses Repos, keine Connectors, Push-Benachrichtigung an. Dienstag ist der Normalfall (Wochenabruf 08:30 UTC), Mittwoch fängt Wochen auf, die erst mit einem Nachlauf (Di 16:30 oder Mi 08:30 UTC) final werden. Prompt:

```text
Wöchentliche Power-Ranking-Kernsätze für die BWG-Fantasy-App – unbeaufsichtigter Lauf, keine Rückfragen.

Auftrag (Stephan Freundl, Dauerfreigabe vom 13.10.2026): Schreibe die Power-Ranking-Kernsätze der zuletzt gerechneten Woche in das öffentliche Repo frest2101/bwg-fantasy, prüfe sie gegen die Daten, lege einen Pull Request an und merge ihn selbst nach main. Eine Einzelfreigabe ist nicht nötig. Ist nichts zu tun, endet der Lauf ohne Commit.

1. Repo: Liegt frest2101/bwg-fantasy nicht im Container, hänge es mit add_repo an (owner frest2101, repo bwg-fantasy, access push), klone es wie angegeben und melde es mit register_repo_root an. Arbeite auf dem Branch, den diese Sitzung vorgibt; gibt sie keinen vor, auf claude/kernsaetze-wNN.
2. Lies CLAUDE.md im Repo (verbindlich, besonders die Gelernt-Zeile „Kernsätze mit Dauerfreigabe“) und arbeite dann Schritt für Schritt docs/auftraege/kernsaetze_routine.md vom aktuellen Stand von origin/main ab.
3. Grenzen: nur die Kernsätze (CSV und die daraus gerechneten App-Daten), nichts anderes im Repo ändern; nie Manager-Namen schreiben oder ausgeben, keine Absichten, kein Start/Sit; nichts nach Notion oder ESPN schreiben; keine Rohdaten abrufen oder committen; keine Pakete installieren; kein force-push. Was du nicht sicher klären kannst, lässt du weg und nennst es in der Zusammenfassung.
4. Am Ende eine kurze Zusammenfassung auf Deutsch, wie in der Ablaufdatei beschrieben (Woche, die zehn Sätze, Link zum Pull Request, Prüfergebnis, Auffälligkeiten) – oder eine Zeile, warum nichts zu tun war.
```
