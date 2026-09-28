# Auftrag Session 3 – Automatisierung (Entwurf Claude, Rückfragen beantwortet Stephan 28.09.2026)

Grundlage: CLAUDE.md (Baustein 3, Variante C), Todoist-Aufgabe „Claude Code – Session 3“ und der Befund der lesenden ESPN-Abrufe vom 28.09. (unten). Erst die Rückfragen klären, dann bauen. Jeden Schritt in zwei, drei Sätzen erklären.

## Ziel
Am Ende der Session liegt das Repo öffentlich auf GitHub (`frest2101/bwg-fantasy`). Zwei GitHub Actions laufen ohne Rechner:
- **Wochenabruf dienstags:** abgeschlossene Wochen neu holen → `compute.py` → `pytest` → Commit.
- **Transaktions-Archiv:** `mTransactions2` und `kona_league_communication` sichern, Commit nur bei Änderung.

Dazu gehören Tests für die neue Logik, nachgezogene README und CLAUDE.md sowie Commits je Schritt.

## Befund 28.09. (nur lesend, Probe-Dateien im Scratchpad, nicht im Repo)
- **`mTransactions2`:**
  - Ohne Parameter liefert der View nur die laufende Periode (W3: 44 Einträge).
  - Mit `scoringPeriodId=p` kommt die ganze Periode: p0 = 17 (Vorsaison), p1 = 293 (davon 240 DRAFT und ein Trade), p2 = 55, p3 = 44.
  - Die „rund drei Tage“ sind also kein Löschfenster bei ESPN. Nach dem Wechsel der laufenden Periode fällt die Vorwoche nur aus dem Standardabruf heraus. Das Archiv holt deshalb bei jedem Lauf alle Perioden von 0 bis zur laufenden.
- **`kona_league_communication`** (ohne Filter):
  - höchstens 50 Themen: 48 × ACTIVITY_TRANSACTIONS, ein Chat-Thema, ein Einstellungs-Thema.
  - Die Nachrichten tragen Metadaten (Autor, Zeit, `messageTypeId`). Zwei Chat-Nachrichten haben Text in `content`, bisher nur ESPN-Systemtexte (korrigiert nach der Prüfung, siehe Nachtrag).
  - Der Endpunkt `/communication/` verlangt einen Login (401). Der Filter-Header der espn-api-Bibliothek liefert 400. Es bleibt daher beim ungefilterten Abruf.
- **`mTeam`:** enthält unter `members` Vor- und Nachnamen, ESPN-Anzeigenamen und Benachrichtigungseinstellungen aller zehn Manager. Das steht auch in den schon committeten Dateien w01–w03.
- **W3:** läuft noch, das MNF ist heute Nacht. Ein Neuabruf ist erst ab Dienstag früh sinnvoll.
- **Umgebung:**
  - In dieser Session gibt es keinen GitHub-Connector und keine `gh`-CLI.
  - Der Git Credential Manager ist installiert.
  - Alle bisherigen Commits laufen über die Noreply-Adresse von `frest2101`.
  - `.lokal/` und `.claude/settings.local.json` waren nie committet.

## Umfang
1. **`scripts/espn_fetch.py`**
   - **`--due`:** holt alle Wochen, die laut Kalender vorbei sind (Woche n läuft Di–Mo, W1 ab Di 08.09.) und lokal fehlen oder noch nicht final sind. Solche Wochen werden überschrieben. Finale Wochen bleiben unangetastet, damit wechselnde Werte wie Ownership keine Rausch-Commits erzeugen.
   - **`--transactions`:**
     - Die laufende Periode kommt aus `mStatus`.
     - `mTransactions2` wird je Periode 0 … laufend geholt und nach `data/raw/2026/transactions/mTransactions2_pNN.json` geschrieben, aber nur, wenn sich die Transaktionen geändert haben.
     - Fehlen archivierte IDs in einer neuen Antwort, bleibt die alte Datei stehen. Die neue Antwort kommt daneben, und es gibt eine Warnung.
     - `kona_league_communication` wird als Datei mit Zeitstempel gespeichert, nur wenn sich die Themen geändert haben.
   - Alle Antworten werden byte-genau gespeichert, auch `members` (Frage 2). Einzige Ausnahme ist `kona_league_communication`, das ohne Chat gespeichert wird (Nachtrag).
2. **`.github/workflows/wochenabruf.yml`**
   - Zeitplan nach Frage 4, zusätzlich von Hand startbar.
   - Ablauf: Checkout → Python 3.13 → `requirements.txt` → `espn_fetch.py --due` → `compute.py` → `pytest` → Commit und Push nur bei Änderung.
3. **`.github/workflows/transaktionen.yml`**
   - Takt nach Frage 3.
   - Ablauf: `espn_fetch.py --transactions` → Commit und Push nur bei Änderung.
   - Das Archiv geht vor, deshalb stoppt ein roter Test es nicht.
   - Für beide Workflows gilt:
     - nur `contents: write`
     - eine gemeinsame `concurrency`-Gruppe
     - Commit als `github-actions[bot]`
     - vor dem Push `git pull --rebase`
     - Bei einem Fehler schickt GitHub eine Mail an das Konto.
4. **Tests** (`tests/test_fetch.py`): Wochenkalender, Auswahl fälliger Wochen, Änderungs- und Schrumpf-Erkennung im Archiv. Alle Tests laufen offline mit Temp-Kopien.
5. **`requirements.txt`:** Versionen auf den lokalen Stand festlegen, damit Action und Rechner gleich rechnen.
6. **Doku:**
   - README: Automatik und „vor lokaler Arbeit `git pull`“, weil die Action auf `main` committet.
   - CLAUDE.md: Struktur, Takt, Befund Transaktionen, „Gelernt“.
   - Nachtrag in diesem Auftrag.

## Schritte
1. Rückfragen klären (unten).
2. GitHub CLI: Stephan installiert sie und meldet sich an (Frage 1).
3. Code und Tests (Umfang 1, 4, 5), `pytest` grün. Erster Archiv-Lauf lokal, damit das Archiv vor dem Periodenwechsel am Dienstag beginnt.
4. Workflows und Doku (Umfang 2, 3, 6).
5. Unabhängige Prüfung durch getrennte Prüf-Agenten: Workflow-Sicherheit, Logik, Inhalt des öffentlichen Repos.
6. Repo mit `gh` öffentlich anlegen und pushen, erster Lauf beider Actions von Hand, Ergebnis prüfen.
7. Abschluss:
   - Todoist-Aufgaben mit Kommentar abhaken.
   - Haken Baustein 3 und Sessionvermerk im Umbau-Plan (nach Freigabe).
   - Korrekturen unter „Gelernt“ eintragen.

## Rückfragen vor dem Bauen (Vorschlag in Klammern)
1. **Repo anlegen ohne Connector:** (Du legst unter github.com/new das leere öffentliche Repo `bwg-fantasy` an, ohne README, .gitignore und Lizenz. Ich setze den Remote und pushe. Beim ersten Push öffnet der Git Credential Manager ein Browserfenster für deinen Login.)
2. **Klarnamen der Manager:** (Nicht veröffentlichen. Der Filter greift ab sofort. Die zehn lokalen Commits werden vor dem ersten Push bereinigt, geändert wird nur `members` in den mTeam-Dateien. Commit-Texte, Autor und Datum bleiben. Eine Sicherung bleibt als lokaler Branch `vor-bereinigung` erhalten und wird nie gepusht.)
3. **Takt Transaktions-Archiv:** (täglich 05:17 UTC statt alle zwei Tage, Commit nur bei Änderung. Das kostet im öffentlichen Repo nichts und fängt ausgefallene GitHub-Zeitpläne ab.)
4. **Wochenabruf-Zeitpunkt:** (Di 08:30 UTC = 10:30 MESZ. Nachläufe Di 16:30 und Mi 08:30 UTC arbeiten nur, wenn die Woche im Repo noch nicht final ist.)
5. **Parallelbetrieb:** (Die Routine „Transaktions-Sync“ läuft eine Woche weiter. Nach drei erfolgreichen Archiv-Läufen vergleiche ich lesend mit den Notion-Roster-Ereignissen, danach pausierst du sie.)
6. **W3:** (Steht das Repo heute, holt die Action W3 am Di 29.09. automatisch, und die Todoist-Aufgabe „W3 nach MNF neu holen“ wird mit Kommentar abgehakt. Sonst wird W3 morgen lokal geholt.)

**Antwort Stephan 28.09.2026:**
1. GitHub CLI: Stephan installiert sie (`winget install --id GitHub.cli`) und meldet sich an (`gh auth login`). Danach legt Claude das Repo mit `gh` an und bedient damit auch die Action-Läufe.
2. So veröffentlichen: kein Filter, keine Bereinigung der Historie. Die Liga ist bei ESPN ohnehin öffentlich lesbar. `members` gilt als Ligadaten.
3. Täglich um 05:17 UTC.
4. und 6. wie vorgeschlagen.
5. Nach einer Woche Parallelbetrieb.

## Nachtrag 28.09.2026: unabhängige Prüfung und weitere Entscheidungen
Fünf Prüf-Agenten (Logik, Workflows, Tests, öffentlicher Inhalt, Betrieb) haben 13 Befunde gemeldet. Jeden Befund hat ein zweiter Agent zu widerlegen versucht: 9 bestätigt, 2 unklar, 2 widerlegt, keiner mit hoher Schwere. Eingebaut:
- **Laufende Periode:** Das Archiv holt nur bis `latestScoringPeriod` und speichert keine Periode, die nach der laufenden der Antwort liegt. ESPN liefert eine Zukunftsperiode mit dem Inhalt der laufenden.
- **Abruf je Woche:** alles oder nichts, `mMatchupScore` als letzte Datei. Ein Teilfehler kann keine halb aktualisierte Woche als „final“ hinterlassen.
- **Bye-Einträge:** Sie zählen bei „final“ nicht mit, damit eine Playoff-Woche nicht endlos neu geholt wird.
- **Saisonende:** Ab 01.08. des Folgejahres schlagen beide Actions fehl („Saison umstellen“). Dazu kommt die Checkliste „Saisonwechsel“ in CLAUDE.md mit der 60-Tage-Regel von GitHub.
- **Abhängigkeiten:** Alle Pakete haben feste Versionen, auch die mitgezogenen.
- **Tests:** Abrufpfad mit Fake-Session, Playoff-Wochen, wechselnder Status-Block im Archiv-Fake. Acht gezielt eingebaute Fehler werden alle erkannt.

**Entscheidungen Stephan 28.09.2026:**
- **Chat-Themen:** Aus `kona_league_communication` kommen nur ACTIVITY_*-Themen ins Archiv, Chat-Texte bleiben draußen.
- **Redaktionstexte:** Die ESPN-Texte in mRoster (Spieler-Outlooks) bleiben in den öffentlichen Rohdaten. Das Restrisiko wegen der ESPN-Nutzungsbedingungen ist bewusst getragen.

## Nicht in dieser Session
- App und GitHub Pages (Baustein 4)
- Spielerpool `kona_player_info`, NFL-Spielplan, D/ST-Faktoren
- Auswertung der Transaktionen (hier nur Archiv)
- Stat-Korrekturen nach Dienstag: nach W4 prüfen, ob sich finale Wochen noch ändern
- Pausieren der Cloud-Routinen (macht Stephan)
- Keine Notion-Writes außer Haken und Sessionvermerk, keine lokalen Paket-Installationen

## Danach
Session 4 = App (Baustein 4) auf GitHub Pages aus `data/season_2026.json`, dazu die Domain-Freigabe für Cloud-Sessions.
