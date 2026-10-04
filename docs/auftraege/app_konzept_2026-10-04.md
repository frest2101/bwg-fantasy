# App-Konzept: Aufbau, Menü und Benennung (Analyse 04.10.2026)

Auftrag Stephan: Die App redaktionell und inhaltlich so überarbeiten, dass sie auch jemand bedienen kann, der sie zum ersten Mal sieht. Welche Zwecke erfüllt sie, lässt sich daraus eine Menüführung ableiten, was ist unlogisch verortet, welche Spaltennamen sind unverständlich? Nichts muss bleiben, wie es ist.

Dieses Dokument ist die Analyse mit Vorschlägen – noch kein Umbau. Am Ende stehen die Entscheidungen, die ich von Stephan brauche, und ein Umsetzungsplan in Paketen.

## Kurzfassung

Die App ist in sieben Sessions entlang der Datenquellen gewachsen: Jede neue Kennzahl bekam eine Ansicht dort, wo ihre Daten herkamen. Dadurch heißen die Tabs nach Datenarten (Tabelle, Spieler, Waiver, Keeper), nicht nach den Fragen, die ein Ligamitglied hat. Fünf Ansichten (D/ST-Faktoren, Positions-Matchup, Wetter, Moves, Team-Seite) haben gar keinen Tab und sind nur über eine zweite Chip-Zeile unter „Spieler“ oder über Links zu finden. Die Frage „Wie gut sind die Teams wirklich?“ wird an drei Orten beantwortet (Tabelle › All-Play/Punkte/Coaching, Ranking › Power Ranking, Ranking › Score), die Frage „Was zählt diese Woche?“ an fünf.

Vorschlag: **fünf Bereiche nach Fragen** – Liga (Wo stehen wir?), Stärke (Wer ist wirklich wie gut?), Woche (Was zählt diese Woche?), Markt (Wen holen, wen abgeben?), Keeper (Wie ist der Kader langfristig aufgestellt?) – dazu eine **Startseite**, die die fünf Fragen in je einem Satz erklärt, eine **Spieler- und Team-Suche im Kopf**, **„Mein Team“ als roter Faden** durch alle Bereiche und eine **Umbenennung der Spaltenköpfe** nach festen Grundsätzen (keine Formelzeichen, keine „ü.“-Kürzel, Prozentspalten heißen nach dem, was sie messen). Dazu ein Schalter **Einfach / Ausführlich**, damit die Standardansicht fünf bis sechs Spalten hat und die Expertenspalten erhalten bleiben.

## 1. Bestandsaufnahme

Stand `main` 04.10.2026, gelesen aus `app/index.html`, `app/js/app.js` und den 15 Ansichtsmodulen.

| Größe | Wert |
|---|---|
| Tabs in der unteren Leiste | 7 (Tabelle, Ranking, Spielplan, Spieler, Waiver, Keeper, Rekorde) |
| Ansichten ohne Tab | 7 (Team, D/ST, Positions-Matchup, Wetter, Moves, Spieltag live, Lesart) |
| Unterschiedliche Bildschirme (Unteransichten, ohne Wochen- und Teamvarianten) | rund 40 |
| Glossarbegriffe in der Lesart | 155 in 15 Bereichen |
| Unterschiedliche Spaltenköpfe | über 200 |
| Begriffe mit Formelzeichen im Spaltenkopf | μ, σ, E, P, Z, r, F, Δ, Σ, PF+ |

### Heutige Struktur

```
Kopf:    [BWG Fantasy 2026]  [Live]  [nach W4 ▾ Datenstand]  [i Lesart]  [☾ Hell/Dunkel]
Tabs:    Tabelle | Ranking | Spielplan | Spieler | Waiver | Keeper | Rekorde

Tabelle   Gesamt · Division · All-Play · Punkte · Coaching · Ausblick       (All-Play, Punkte, Coaching auch je Woche)
Ranking   Power Ranking · Score (Profile, Regler, drei Normierungen)
Spielplan W1 … W17 (Paarungen, Wochentabelle, Top-Scorer, Saisonwochen)
Spieler   Liste (Sichten Saison · ROS · Besitz, Filter) · Spielerseite
          └ zweite Chip-Zeile: Spieler · D/ST-Faktoren · Positions-Matchup · Moves · Wetter
            D/ST        Streaming · Offenses
            Matchup     Übersicht · QB · RB · WR · TE · K
            Moves       Transaktionen · (Draft → Keeper)
            Wetter      Prognose Wn · Ist
Waiver    Beste verfügbare Spieler (Horizont Woche · Σ nächste 3 · ROS · Zukunft × Spalten Alle · Ausblick · Besitz × Position)
          · Bedarf je Team (Woche | ROS) · Reihenfolge · Claims der letzten 7 Tage
Keeper    Bilanz · Kader · Alter · Wert · Draft 2026 · Draft 2027
Rekorde   Saison · Positionen · H2H · All-Time · Champions
Team      (nur über Teamnamen) Kacheln, PF je Woche, Wochenliste, Kader, Positionen/Profil, H2H, Verläufe, Franchise
Live      (Chip im Kopf) Spieltag live: NFL-Spiele, Matchups, Aufstellungen, Bewegungen, Kadervergleich
Lesart    (i im Kopf) Glossar mit Suche
```

## 2. Befunde: Woran ein Neuling hängen bleibt

1. **Tabs heißen nach Daten, nicht nach Fragen.** „Waiver“, „Keeper“, „Ranking“ setzen voraus, dass man weiß, was man dort sucht. Die Frage „Wen soll ich diese Woche aufstellen?“ hat keinen Tab; ihre Antworten liegen in Spielplan (Siegchance), Spieler (Form, ROS), D/ST, Positions-Matchup, Wetter, Waiver (Bedarf Woche, Ausfälle, Byes) und Live.
2. **Versteckte zweite Ebene.** D/ST-Faktoren, Positions-Matchup, Wetter und Moves erreicht man nur über eine Chip-Zeile unter „Spieler“, die auf der Spielerseite selbst fehlt. Moves und Wetter haben mit „Spieler“ inhaltlich wenig zu tun. Die Team-Seite hat gar keinen Einstieg außer dem Teamnamen in Tabellen.
3. **Drei Antworten auf „Wer ist stark?“ ohne Wegweiser.** Tabelle › All-Play, Punkte, Coaching; Ranking › Power Ranking; Ranking › Score. Nirgends steht, wann man welche nimmt. Die Playoff-Simulation („Ausblick“) steht unter Tabelle, die Draft-Position 2027 aus derselben Simulation unter Keeper.
4. **Zwei Ansichten, eine Formel.** D/ST-Faktoren (je Offense) und Positions-Matchup (je Defense und Position) rechnen identisch, heißen aber verschieden, liegen nebeneinander und haben getrennte Spaltensätze (Z25, Z26 (n), r25, r26, F, ΔF, Rang). D/ST „Streaming“ ist inhaltlich ein Waiver-Filter auf D/ST, den der Waiver-Tab mit „Matchup Wn“ und „Ø nächste 3“ schon abdeckt.
5. **Die Standardtabelle ist schon eine Expertentabelle.** Tabelle › Gesamt zeigt zehn Spalten: #, Team, W-L, PF, PO %, AP %, PA, Diff, Eff. %, Streak. Drei davon (PO %, AP %, Eff. %) sind App-eigene Kennzahlen mit Kürzeln, die nur die Legende darunter erklärt.
6. **Kürzel und Formelzeichen in Spaltenköpfen.** AP %, Eff. %, PO %, Div %, Proj.-Δ, ROS ü. Ersatz, W5 ü. Ersatz, Kader-Pot., Kader-Proj., μ, E %, P, Z25, Z26 (n), r25, r26, ΔF, PF+, S, PO, Div/Pl., Sp., Ø Pick, ü. Linie, ab Linie, Trend 30 T., Σ nächste 3, Konstanz (kleiner ist besser, ohne dass man es sieht).
7. **Gleiche Kennzahl, verschiedene Namen.** „Coaching“ (Tab), „Coaching-Effizienz“ (Glossar), „Eff. %“ (Spalte), „Effizienz“ (Kachel), „Liga-Effizienz“ (Spielplan-Kachel). „Ausblick“ (Chip), „Playoff-Simulation“ (Tabellentitel), „Playoff-%“ (Kachel), „PO %“ (Spalte). „Lesart“ (Glossar) ist ein Wort, das außerhalb dieses Projekts niemand für „Erklärungen“ benutzt.
8. **„Mein Team“ gibt es, aber nur in drei Ecken.** Waiver, Keeper › Kader und Live kennen eine Team-Auswahl im Browser-Speicher. Tabelle, Spielplan, Spieler und Start wissen nichts davon; die Team-Seite ist kein Einstieg.
9. **Kein Einstieg.** Die App öffnet mit der Gesamttabelle. Wer sie zum ersten Mal sieht, bekommt keine Orientierung, was es sonst gibt, wie aktuell die Daten sind und wo seine eigenen Fragen beantwortet werden. Der Datenstand ist ein Chip mit „nach W4“, dessen Fenster sieben Zeilen Technik zeigt (Wertung, Playoffs, Projektionen ROS, Pool, Wetter, Letzter Move, Nächster Tageslauf, Nächster Wochenabruf).
10. **Rekorde mischt drei Zeiträume.** Saison 2026 (Rekorde, Positionen), H2H 2026, All-Time 2015–2025 und Champions. Die Wochenkennzahlen 2018–2022 aus der nfl.com-Auskunft (`history.json › wochen`) zeigt die App noch gar nicht.
11. **Waiver ist der dichteste Bildschirm.** 4 Horizonte × 3 Spaltensichten × 7 Positionsfilter, darunter Bedarf (2 Sichten), Reihenfolge und Claims. Die Horizonte heißen „Woche · Σ nächste 3 · ROS · Zukunft“; ohne Glossar ist nicht klar, dass „Zukunft“ Marktwert heißt und „ROS“ Rest der Saison.
12. **Spielplan ist zweierlei.** Vergangene Wochen (Ergebnisse, Wochentabelle, Top-Scorer) und die laufende Woche (Paarungen mit Siegchance) stehen in einer Ansicht mit 17 Wochen-Chips. Ersteres ist Archiv, Letzteres gehört zu „diese Woche“.

Was gut ist und bleiben soll: ein Datenvertrag, Python rechnet, die App zeigt nur an; Chips statt Menüs; Glossar ohne JavaScript lesbar; Erklärungen per i-Knopf; alles ohne Login und ohne Persönliches; Hash-Routen, die man teilen kann.

## 3. Zwecke der App

Aus Sicht eines Ligamitglieds (nicht nur Stephans) beantwortet die App sieben Fragen. Die Reihenfolge ist die Häufigkeit im Saisonalltag.

| Frage | Heute verteilt auf | Rhythmus |
|---|---|---|
| **A. Was zählt diese Woche?** Wer spielt gegen wen, Siegchance, Ausfälle, Byes, Wetter, günstige Matchups, Live-Punkte | Spielplan, Live, Wetter, Positions-Matchup, D/ST, Waiver › Bedarf Woche, Spielerseite | sonntags und davor |
| **B. Wen hole ich, wen gebe ich ab?** Beste freie Spieler, Lücken im Kader, Waiver-Reihenfolge, Fristen, was andere geholt haben | Waiver, Moves, Spieler › Besitz | Dienstag bis Mittwoch |
| **C. Wo stehen wir?** Tabelle, Division, Ergebnisse, Playoff-Chancen | Tabelle › Gesamt, Division, Ausblick; Spielplan | nach jeder Woche |
| **D. Wer ist wirklich wie gut?** Stärke jenseits von Siegen: All-Play, Punkte, Glück, Coaching-Effizienz, Power Ranking, eigener Score | Tabelle › All-Play, Punkte, Coaching; Ranking | nach jeder Woche, Diskussionsstoff |
| **E. Wie ist mein Kader langfristig aufgestellt?** Keeper, Herkunft, Alter, Marktwert, Draft-Kosten, Draft-Position nächstes Jahr | Keeper | selten, intensiv im Winter |
| **F. Wer ist dieser Spieler, was ist dieses Team?** Nachschlagen | Spieler, Team-Seite | jederzeit, aus allen anderen Fragen heraus |
| **G. Was war früher?** Rekorde, Duelle, Historie, Champions | Rekorde | selten |

Dazu die Hilfsfragen „Wie aktuell ist das?“ (Datenstand) und „Was heißt das?“ (Lesart).

A bis E sind die fünf Bereiche. F ist eine Suche, keine Rubrik: Man landet auf Spieler- und Teamseiten aus jedem Bereich heraus. G ist Archiv und gehört unter C.

## 4. Vorschlag Menüführung

### Fünf Bereiche

```
Kopf:    [BWG Fantasy]  [🔍 Spieler, Team]  [Mein Team ▾]  [Stand ▾]  [? Erklärungen]  [☾]
Tabs:    Liga | Stärke | Woche | Markt | Keeper

Start (Logo)   Diese Woche · Mein Team · fünf Karten mit je einem Satz und einer Zahl · Datenstand
Liga           Tabelle · Division · Ergebnisse · Playoff-Chancen · Duelle · Rekorde
Stärke         Power Ranking · All-Play & Glück · Punkte & Form · Coaching · Eigener Score
Woche          Spieltag live · Paarungen Wn · Matchups · Wetter
Markt          Freie Spieler · Bedarf je Team · Reihenfolge & Claims · Moves
Keeper         Bilanz · Herkunft · Alter · Marktwert · Draft 2026 · Draft 2027
```

Jeder Bereich bekommt unter der Überschrift eine Zeile, die seine Frage nennt, z. B. „Stärke – Wer ist wirklich wie gut? Rangfolgen nach Punkten statt nach Siegen.“ Das ist für den Neuling die wichtigste Zeile der App und kostet nichts.

### Zuordnung alt → neu

| Heute | Neu | Bemerkung |
|---|---|---|
| Tabelle › Gesamt, Division | Liga › Tabelle, Division | Gesamt in „Einfach“ mit #, Team, W-L, PF, PA, Playoff %; der Rest in „Ausführlich“ |
| Spielplan (vergangene Wochen) | Liga › Ergebnisse | Wochen-Chips, Wochentabelle, Top-Scorer wie heute |
| Tabelle › Ausblick | Liga › Playoff-Chancen | ohne die Spalten Waiver und Moves (gehören zu Markt); Seeding-Schalter bleibt |
| Rekorde › H2H | Liga › Duelle | Saison-Duelle aller Paare |
| Rekorde › Saison, Positionen, All-Time, Champions | Liga › Rekorde | zweite Ebene: 2026 · Positionen · Historie 2015–2025 · Champions; Platz für die Wochen 2018–2022 |
| Tabelle › All-Play | Stärke › All-Play & Glück | mit Wochensicht wie heute |
| Tabelle › Punkte | Stärke › Punkte & Form | mit Wochensicht |
| Tabelle › Coaching | Stärke › Coaching | Name bleibt (Entscheidung Stephan 04.10.2026), nur der Umzug in den Bereich Stärke |
| Ranking › Power Ranking | Stärke › Power Ranking | erste Ansicht des Bereichs, mit Kernsätzen |
| Ranking › Score | Stärke › Eigener Score | Regler und Profile; klar als „selbst gewichten“ ausgewiesen |
| Live (Chip) | Woche › Spieltag live | erste Ansicht von Woche, solange die Woche läuft; der Chip im Kopf kann bleiben, muss aber nicht |
| Spielplan (laufende Woche) | Woche › Paarungen | dieselbe Ansicht wie Ergebnisse, nur auf die laufende Woche gestellt; Siegchance, Anstoßzeiten |
| D/ST-Faktoren + Positions-Matchup | Woche › Matchups | eine Ansicht, Segment QB · RB · WR · TE · K · D/ST (D/ST = Offenses); „Streaming“ entfällt zugunsten von Markt › Freie Spieler › D/ST |
| Wetter | Woche › Wetter | unverändert |
| Waiver › Beste verfügbare Spieler | Markt › Freie Spieler | Horizonte umbenannt (Abschnitt 7) |
| Waiver › Bedarf je Team | Markt › Bedarf je Team | Sichten „Nächste Woche“ und „Rest der Saison“ |
| Waiver › Reihenfolge, Claims | Markt › Reihenfolge & Claims | |
| Moves | Markt › Moves | Transaktionen und Aufstellungswechsel; der Draft-Link führt zu Keeper › Draft 2026 |
| Keeper › Bilanz, Kader, Alter, Wert, Draft, Draft 2027 | Keeper › Bilanz, Herkunft, Alter, Marktwert, Draft 2026, Draft 2027 | „Kader“ heißt „Herkunft“, weil die Team-Seite schon einen Kader zeigt |
| Spieler (Tab) | 🔍 im Kopf → Spielerliste mit Filtern; Spielerseite unverändert | siehe Alternative unten |
| Team (versteckt) | Mein Team im Kopf → Team-Seite; Teamnamen bleiben Links | |
| Lesart | ? Erklärungen | gleiche Seite, neuer Name, nach den fünf Bereichen gegliedert |

### Alternative: sechs Tabs mit „Spieler“

Wenn die Suche im Kopf zu versteckt wirkt: Liga · Stärke · Woche · Markt · Spieler · Keeper. Sechs Tabs passen auf ein iPhone (heute sind es sieben), aber „Spieler“ wäre der einzige Tab, der eine Sache statt einer Frage benennt. Mein Vorschlag ist die Suche im Kopf, weil die Spielerliste in der Praxis aus einer Frage heraus geöffnet wird (Waiver-Kandidat, Kaderspieler, Gegner), selten als Rubrik.

### Namen der Bereiche – Alternativen

- **Stärke** oder **Ranking**: „Ranking“ ist vertraut, „Stärke“ sagt, worum es geht. Empfehlung Stärke; wenn Stephan „Ranking“ lieber mag, passt es ebenso.
- **Markt** oder **Waiver**: „Waiver“ kennt jedes Ligamitglied, meint aber nur einen Teil (nicht Free Agents, nicht Moves). Empfehlung Markt. Alternative „Transfers“.
- **Woche** oder **Spieltag**: „Spieltag“ klingt nach Sonntag, „Woche“ deckt Dienstag bis Montag. Empfehlung Woche.
- **Keeper** bleibt: In einer Keeper-Liga ist das der Begriff, unter dem alle Winterfragen laufen (Wert, Alter, Herkunft, Draft).

## 5. Startseite

Die App öffnet heute mit der Tabelle. Vorschlag: eine Startseite (Logo-Link, Route `#start` oder leerer Hash), die in einer Bildschirmhöhe sagt, was los ist und wohin man geht.

```
Woche 5 · Spiele laufen / Woche 4 gewertet · Stand heute 09:12
[Mein Team: Hugh Jass]  4-0 · Rang 1 · Playoff 92 %     → nächstes Spiel So gegen gloane, Siegchance 61 %
                        Lücken für W5: RB2 (Bye) · 1 Spieler fraglich                   → Markt › Bedarf

Liga      Wo stehen wir?            Tabelle: 1. Hugh Jass, 2. … · Playoff-Chancen        → Liga
Stärke    Wer ist wirklich stark?   Power Ranking: 1. … (↑2)                               → Stärke
Woche     Was zählt diese Woche?    7 Spiele So 19:00, 3 markierte Wetterspiele            → Woche
Markt     Wen holen?                Reihenfolge: HJS 7. · 3 Kandidaten für deine Lücken     → Markt
Keeper    Langfristig               Kern-Wert HJS 3. · Draft 2027: erwartet Pick 9          → Keeper

Erklärungen · Datenstand · Hell/Dunkel
```

Ohne gewähltes Team zeigt die Startseite dieselben Karten ohne Team-Zeile und eine Aufforderung „Mein Team wählen“ (Browser-Speicher wie heute im Waiver-Tab, kein Login, nichts wird gespeichert als die Team-Nummer). Alle Zahlen kommen aus `teams.json`, `schedule.json` und `waiver.json`; die Startseite rechnet nichts.

## 6. „Mein Team“ als roter Faden

Heute kennt der Browser-Speicher `bwg-team` das Team nur in Waiver, Keeper › Kader und Live. Vorschlag: einmal wählen (Kopf), überall wirksam:

- Liga › Tabelle, Division, Ergebnisse: eigene Zeile hervorgehoben (Klasse `me` gibt es schon in Rekorde › H2H).
- Stärke: eigene Zeile hervorgehoben, in den Diagrammen hervorgehoben (statt heute „Team 1“).
- Woche › Paarungen: eigenes Spiel zuerst; Spieltag live: eigene Aufstellung zuerst (heute schon).
- Markt: Spalte „Für mein Team“ und Bedarf vorausgewählt (heute schon).
- Keeper › Herkunft: eigenes Team vorausgewählt (heute schon).
- Team-Seite: ein Tipp im Kopf.

Das ist kein Persönliches im Sinne der Repo-Regel: Es ist eine Anzeige-Einstellung im Browser, wie Hell/Dunkel, und jedes Ligamitglied kann sein Team wählen.

## 7. Benennung

### Grundsätze

1. **Kein Formelzeichen im Spaltenkopf.** μ, σ, E, P, Z, r, F, Δ, Σ nur in „Ausführlich“ und im Glossar. Im Kopf steht das Wort: Stärke, Projektion, zugelassen, Faktor.
2. **Keine Kürzel, die es nur hier gibt.** AP %, Eff. %, PO %, ü., Pot., Proj. werden ausgeschrieben oder durch ein Wort ersetzt. Fantasy-Standardkürzel bleiben: PF, PA, W-L-T, QB … D/ST, FA, IR, Bye, ROS nur dort, wo kein Platz ist, sonst „Rest der Saison“.
3. **Prozent heißt nach dem, was es misst.** „Playoff %“ statt „PO %“, „All-Play %“ statt „AP %“, „Division %“ statt „Div %“.
4. **Eine Kennzahl, ein Name.** Wo heute Coaching, Coaching-Effizienz, Eff. %, Effizienz und Liga-Effizienz stehen, heißt die Ansicht „Coaching“, die Spalte und Kachel „Eff. %“ und das Glossar „Coaching-Effizienz“ (Entscheidung Stephan: Begriffe bleiben). Wo Ausblick, Playoff-Simulation, Playoff-% und PO % stehen, steht „Playoff-Chancen“ (Ansicht) und „Playoff %“ (Spalte).
5. **Richtung sichtbar.** Spalten, bei denen klein gut ist (Konstanz, Alter bereinigt, Verschenkt), zeigen das im Namen oder in der ersten Erklärungszeile: „Schwankung (klein = gleichmäßig)“.
6. **Zeitbezug im Namen.** „Rest der Saison“ statt ROS, „nächste Woche W5“ statt Wn, „Stand heute 09:12“ statt „Tagesstand“, „nach Woche 4“ statt „Wochenstand“.
7. **Jeder Spaltenkopf ist erklärbar.** Die Legende „Erklärungen:“ unter der Tabelle bleibt, zusätzlich öffnet ein langer Druck oder ein ⓘ im Kopf die Erklärung (die i-Knöpfe `data-g` gibt es schon).

### Bereiche und Ansichten

| Heute | Neu |
|---|---|
| Tabelle | Liga |
| Ranking | Stärke |
| Waiver | Markt |
| Spielplan | Liga › Ergebnisse und Woche › Paarungen |
| Rekorde | Liga › Rekorde |
| Ausblick | Playoff-Chancen |
| All-Play | All-Play & Glück |
| Punkte | Punkte & Form |
| Score | Eigener Score |
| D/ST-Faktoren, Positions-Matchup | Matchups |
| Streaming | entfällt (Markt › Freie Spieler › D/ST) |
| Offenses | Matchups › D/ST |
| Keeper › Kader | Keeper › Herkunft |
| Keeper › Wert | Keeper › Marktwert |
| Keeper › Draft | Keeper › Draft 2026 |
| Horizont „Woche“ | Nächste Woche (W5) |
| Horizont „Σ nächste 3“ | Nächste 3 Wochen |
| Horizont „ROS“ | Rest der Saison |
| Horizont „Zukunft“ | Langfristig (Marktwert) |
| Spalten-Sicht „Ausblick“ (Waiver) | Projektionen |
| Lesart | Erklärungen |
| Tagesstand hh:mm | Stand heute hh:mm (am Vortag: Stand gestern) |
| Datenstand „nach W4“ | „W4 gewertet“ |

### Spaltenköpfe (Auswahl der wichtigsten)

| Wo | Heute | Neu | Grund |
|---|---|---|---|
| Liga › Tabelle | PO % | Playoff % | Kürzel |
| | AP % | All-Play % | Kürzel |
| | Eff. % | bleibt (Entscheidung Stephan) | |
| | Streak | bleibt (Entscheidung Stephan) | |
| Liga › Playoff-Chancen | Div/Bye % | Division % | Bye steckt in der Liga-Regel schon drin, Erklärung sagt es |
| | Restsiege | Erwartete Siege Rest | „Restsiege“ liest sich wie eine Anzahl |
| | ESPN PO % | ESPN Playoff % | |
| | Waiver, Moves | entfallen hier | gehören zu Markt |
| Stärke › Power Ranking | μ | Stärke | Formelzeichen; „± 7,2“ bleibt als Unterzeile |
| | E % | Erwartete All-Play % | Formelzeichen |
| | AP % Ist | All-Play % bisher | |
| | P | Projektion Kader | Formelzeichen |
| | Vorwoche | Rang Vorwoche | |
| Stärke › Punkte & Form | Form Δ | Form zu Saison | Δ |
| | Proj.-Δ | Ist − Projektion | Kürzel, Richtung |
| | Floor | bleibt (Entscheidung Stephan) | |
| Stärke › Coaching | Optimal | Beste Aufstellung | |
| | Bank | Bankpunkte | |
| | Kader-Pot. | Beste Aufstellung Ø | Kürzel |
| | Kader-Proj. | Projektion Kader | Kürzel |
| | Ø/Woche, Max | Verschenkt Ø, Verschenkt max | Bezug fehlt im Kopf |
| Woche › Matchups | F | Faktor | Formelzeichen |
| | ΔF | zur Vorwoche | |
| | Z25, Z26 (n) | Zugelassen 2025, Zugelassen 2026 (Spiele) | nur Ausführlich |
| | r25, r26 | entfallen (Ausführlich: Verhältnis 2025, 2026) | Rechenweg, nicht Ergebnis |
| | Off. zugelassen | Punkte zugelassen | |
| | SoS W15–17 | Playoffs W15–17 | Kürzel |
| | Rest bis W14 | Rest Regular Season | |
| Spieler | Ø | Ø Punkte | |
| | Konstanz | Schwankung | Richtung |
| | Floor, Ceiling | bleiben (Entscheidung Stephan) | |
| | Bank-Pkt | Bankpunkte | |
| | ROS, ROS/Sp., ROS PO | Rest Saison, Rest je Spiel, Rest Playoffs | Kürzel |
| | ROS ü. Ersatz | Vorteil Rest Saison | Kürzel, Begriff |
| | ROS-Rang | Rang Rest Saison | |
| | Δ Tag | Besitz Δ heute | Bezug |
| | gestartet % | aufgestellt % | ESPN-Begriff eingedeutscht |
| Markt › Freie Spieler | Proj. W5 | Projektion W5 | |
| | W5 ü. Ersatz | Vorteil W5 | Kürzel; Erklärung „Projektion minus bester freier Ersatz“ |
| | Σ nächste 3 | Nächste 3 | |
| | Für HJS | Gewinn für HJS | sagt, was die Zahl ist |
| | Wert-Rang | Marktwert-Rang | |
| | Matchup W5 | Gegner W5 (Faktor) | |
| Markt › Bedarf | Lücken Wn → beste freie Spieler | Lücken W5 und Kandidaten | |
| | Über Ersatz je Position | Tiefe je Position | |
| Keeper › Bilanz | Keeper im Kader, Draft im Kader | Punkte von Keepern, Punkte aus dem Draft | die Spalte zeigt Punkte, nicht Spieler |
| Keeper › Marktwert | Kern-Wert | Wert Top 12 | sagt, was es ist |
| | ü. Linie | über Keeper-Linie | Kürzel |
| | ab Linie | Spieler ab Linie | |
| | Alter nach Wert | Ø Alter (nach Wert) | |
| | Trend 30 T. | Trend 30 Tage | |
| Keeper › Draft 2027 | Ø Pick | Erwarteter Pick | |
| | Pick 1–3 | Pick 1–3 % | fehlt die Einheit |
| Keeper › Draft 2026 | PF fürs Team | Punkte fürs Team | |
| | Verbleib | noch im Kader | |
| Liga › Rekorde | PF+ | PF+ (bleibt, mit ⓘ) | eingeführter Begriff, kurz |
| | S | Saisons | |
| | PO | Playoffs | |
| | Letzter | Letzter Platz | |
| | Div/Pl. | Division / Platz | |
| Team-Seite | Form Δ | Form zu Saison | |
| | Effizienz | Eff. % wie in den Tabellen | ein Name für eine Kennzahl |
| | AP | All-Play | |
| | W-Rang | Wochenrang | |

Die Umbenennung der Spaltenköpfe ist Fleißarbeit an rund 60 Stellen; die Glossar-IDs (`g-…`) bleiben, damit Links und `test_zeitplan` weiter funktionieren – nur der Anzeigetext ändert sich.

## 8. Einfach / Ausführlich

Ein Schalter im Kopf oder auf der Startseite (Browser-Speicher), Standard „Einfach“. Er wirkt auf die Tabellen mit mehr als sechs Spalten:

| Tabelle | Einfach | nur Ausführlich |
|---|---|---|
| Liga › Tabelle | #, Team, W-L, PF, PA, Playoff % | Diff, All-Play %, Eff. %, Streak |
| Stärke › Power Ranking | #, Team, Trend, Stärke | Erwartete All-Play %, All-Play % bisher, W-L, Projektion, Rang Vorwoche |
| Stärke › All-Play & Glück | Pl., Team, All-Play W-L, All-Play %, Matchup-Glück | W-L, Median-Bilanz, Spielplan Pkt |
| Stärke › Coaching | Pl., Team, Eff. %, Verschenkt | Verschenkt Ø, max, Beste Aufstellung, Bankpunkte, Beste Aufstellung Ø, Projektion Kader |
| Woche › Matchups | Defense, Faktor, Rang, Bye | zur Vorwoche, Zugelassen 2025/2026, Verhältnis |
| Markt › Freie Spieler | Spieler, Projektion W5, Vorteil W5, Gegner W5, Bye, Verletzung | Nächste 3, Rest Saison, Besitz, Frist, Marktwert-Rang (heute die drei Spaltensichten) |
| Spieler | Spieler, Ø Punkte, Form, Rest je Spiel | heute die Sichten Saison / ROS / Besitz |
| Keeper › Marktwert | Team, Wert Top 12, Spieler ab Linie | zum Schnitt, über Keeper-Linie, Ø Alter, mit Wert |

Die heutigen „Spalten“-Segmente im Waiver- und Spieler-Tab werden dadurch zu einem Schalter mit zwei Stellungen, der überall gleich heißt. Die Datenstand-Erklärung (sieben Zeilen) zeigt in „Einfach“ nur „W4 gewertet · Stand heute 09:12 · nächste Aktualisierung ab 10:00“.

## 9. Team- und Spielerseite nach denselben Bereichen

Die Team-Seite ist heute ein langer Stapel (Kacheln, PF je Woche, Wochenliste, Kader, Positionen, H2H, Verläufe, Franchise, „Weiter zu“). Vorschlag: dieselben fünf Abschnitte wie das Menü, in derselben Reihenfolge, als aufklappbare Karten (auf dem Desktop offen):

1. **Liga** – Rang, W-L, Playoff %, nächstes Spiel mit Siegchance, Wochenliste, Duelle.
2. **Stärke** – Power Ranking mit Kernsatz, All-Play, Matchup-Glück, Eff. %, PF je Woche, Verläufe.
3. **Woche** – Lücken für W5, Ausfälle und fraglich, Byes, Wetter der eigenen Spieler (aus `waiver.json › bedarf_woche` und `wetter.json`; heute nur im Waiver-Tab).
4. **Markt** – Bedarf Rest der Saison, Stärken und Schwächen, Tiefe je Position, die drei besten Kandidaten je Lücke, Moves des Teams.
5. **Keeper** – Kader mit Herkunft, Alter, Marktwert; Draft-Picks 2026 mit Ertrag; erwarteter Pick 2027.

Dann weiß jemand, der die Team-Seite kennt, auch das Menü – und umgekehrt. Die Spielerseite genauso in Kurzform: Kopf (Position, Team, Status, Verletzung), Woche (Gegner, Faktor, Wetter, Projektion), Saison (Formkurve, Ø, Hoch, Tief), Rest der Saison, Markt (Besitz, Frist, Vorteil), Keeper (Herkunft, Alter, Marktwert), Verweise.

## 10. Erklärungen (heute Lesart)

- Umbenennen in „Erklärungen“, Symbol „?“ statt „i“ (das „i“ steht in der App schon für die kleinen Info-Knöpfe).
- Gliederung nach den fünf Bereichen plus „Spieler“, „Allgemein“ und „Datenstand“ statt der heutigen 15 Bereiche nach Datenquelle.
- Jeder Eintrag beginnt mit einem Satz Alltagssprache, dann der Rechenweg. Beispiel heute: „Matchup-Glück: je Woche nur, wenn das Ergebnis der Punkteseite widerspricht …“. Neu zuerst: „Hat ein Team mehr gewonnen, als seine Punkte hergaben? Plus = Glück, minus = Pech, 0 = verdient.“
- Die rund 20 Begriffe, die nur in „Ausführlich“ vorkommen (μ, P, E, Z, r, Normierungen, Redundanz), stehen in einem eigenen Block „Rechenwerk“ am Ende.
- Die Lesart-Suche bleibt.

## 11. Was zusammengelegt werden oder wegfallen kann

- **D/ST › Streaming**: Der Waiver-Tab zeigt für freie D/ST dieselben Spalten (Gegner Wn mit Faktor, Ø nächste 3, Rest, Playoffs). Eine Ansicht reicht.
- **D/ST › Offenses und Positions-Matchup**: eine Ansicht „Matchups“ mit Positions-Segment; D/ST ist dort die sechste Position.
- **Rekorde › H2H und Team-Seite › H2H**: bleiben beide, aber unter einem Namen („Duelle“).
- **Spalten Waiver und Moves in der Playoff-Simulation**: entfallen dort.
- **Ranking › Score als eigene Ansicht**: bleibt, aber als „Eigener Score“ hinter dem Power Ranking, nicht gleichberechtigt davor.
- **Datenstand-Fenster**: sieben technische Zeilen werden zu drei; der Rest unter „Ausführlich“.
- **Spalten-Sichten „Alle · Ausblick · Besitz“ (Waiver) und „Saison · ROS · Besitz“ (Spieler)**: werden zum Schalter Einfach / Ausführlich.

Nichts an den Daten oder am Rechenwerk ändert sich; `app/data` und `docs/app_daten.md` bleiben unberührt. Es ist ein Umbau der Anzeige.

## 12. Umsetzung in Paketen

| Paket | Inhalt | Aufwand | Berührt |
|---|---|---|---|
| **P1 Menü und Routen** | Fünf Tabs, Kopf mit Suche und Mein Team, Bereichs-Zeile unter jeder Überschrift, Router mit Weiterleitungen alt → neu (`#tabelle/allplay` → `#staerke/allplay`, `#waiver` → `#markt`, `#dst` → `#woche/matchups/dst` …), damit alle Links in README, CLAUDE.md, `docs/` und im Claude-Projekt weiter gehen | mittel | `index.html`, `app.js`, alle `v_*.js` (h1, Chips), `style.css`; README, CLAUDE.md, `docs/app_daten.md` (Routen) |
| **P2 Startseite** | `v_start.js` mit den fünf Karten, Mein Team, Wochenstatus; Logo führt dorthin | mittel | neu `v_start.js`, `app.js`, `ui.js` (Mein Team im Kopf) |
| **P3 Umzüge und Zusammenlegung** | Matchups aus `v_dst.js` und `v_matchup.js` zu einer Ansicht; Moves und Wetter unter Markt bzw. Woche; Spielplan als Ergebnisse (Liga) und Paarungen (Woche); H2H als Duelle | mittel bis groß | `v_dst.js`, `v_matchup.js`, `v_spielplan.js`, `v_rekorde.js`, `v_waiver.js` (Bedarf-Sichten), `v_moves.js` |
| **P4 Benennung und Erklärungen** | Spaltenköpfe nach Abschnitt 7, Glossar nach Abschnitt 10 (IDs bleiben), Bereichs-Zeilen | mittel (viele kleine Stellen) | alle `v_*.js`, `index.html` (Glossar), `ui.js` (Legende) |
| **P5 Einfach / Ausführlich** | Schalter im Kopf, Spaltensätze je Tabelle nach Abschnitt 8, ersetzt die Spalten-Segmente | mittel | `ui.js` (`table`), `v_tabelle.js`, `v_ranking.js`, `v_waiver.js`, `v_spieler.js`, `v_dst.js`, `v_keeper.js` |
| **P6 Team- und Spielerseite** | Abschnitte nach den fünf Bereichen, Woche-Abschnitt aus `waiver.json` | mittel | `v_team.js`, `v_spieler.js` |

Reihenfolge-Empfehlung: P1 → P4 → P2 → P3 → P5 → P6. P1 und P4 bringen den größten Verständnisgewinn bei geringstem Risiko; P2 braucht P1; P3 ist der tiefste Eingriff und sollte eine eigene Session sein; P5 und P6 sind Feinschliff.

Risiken und Nebenwirkungen:
- **Alte Links.** Routen stehen in README, CLAUDE.md, `docs/app_daten.md`, den Session-Aufträgen und in der Projektanweisung des Claude-Projekts (fantasy-privat). Die Weiterleitungstabelle im Router hält alle alten Hashes dauerhaft am Leben; die Doku im Repo ziehe ich nach, die Projektanweisung ist ein Auftrag an die Sitzung fantasy-privat.
- **Tests.** `test_live_ansicht` liest `VIEWS` aus `app.js` und prüft `#spieltag`; `test_zeitplan` prüft Glossar-ID `g-aktualisierung` und `DAILY`; `test_oeffentlich` prüft `app/` auf Manager-Namen. Alle drei überstehen den Umbau, wenn `spieltag` eine Route bleibt (unter Woche) und die Glossar-IDs bleiben.
- **Live-Ansicht und `claude_stand.py`** sind nicht betroffen (Rechenkern bleibt, nur der Einstieg wandert unter Woche).
- **Öffentlichkeit.** Mein Team ist eine Browser-Einstellung, keine Veröffentlichung; `check_public.py` bleibt wie es ist.
- **Gewohnheit.** Stephan kennt die heutige Struktur auswendig; die ersten zwei Wochen nach dem Umbau wird er suchen. Die Weiterleitungen und die Bereichs-Zeilen fangen das ab.

## 13. Entscheidungen (Fragen 04.10.2026, Antworten Stephan im Chat derselben Session)

1. **Fünf Bereiche nach Fragen** (Liga, Stärke, Woche, Markt, Keeper) – ja, oder lieber die Alternative mit sechs Tabs und „Spieler“?
2. **Namen:** Stärke oder Ranking? Markt oder Waiver? Woche oder Spieltag?
3. **Spieler-Suche im Kopf** statt Tab – ja?
4. **Startseite** mit fünf Karten und Mein Team – ja? Soll das Logo dorthin führen oder soll die App weiter mit der Tabelle öffnen?
5. **Mein Team überall** (Browser-Speicher, Hervorhebung in allen Tabellen) – ja?
6. **Matchups zusammenlegen** und D/ST › Streaming aufgeben – ja?
7. **Einfach / Ausführlich** mit Standard Einfach – ja? Oder Standard Ausführlich für dich und Einfach als Wahl?
8. **Spaltennamen** aus Abschnitt 7 – freigeben, ändern oder einzelne streichen? Insbesondere: Aufstellung % für Coaching-Effizienz, Serie für Streak, Schwankung für Konstanz, Tief/Hoch für Floor/Ceiling, ein neuer Name für „ü. Ersatz“.
9. **Lesart → Erklärungen** – ja?
10. **Reihenfolge der Pakete** – wie vorgeschlagen (P1, P4, P2, P3, P5, P6), oder anders?

### Antworten Stephan (04.10.2026)

1. Fünf Bereiche nach Fragen: **ja** – Liga · Stärke · Woche · Markt · Keeper.
2. Namen: **Stärke**, **Markt**, **Woche**.
3. Spieler-Suche im Kopf (Lupe, Spieler und Teams) statt Tab: **ja**.
4. Startseite mit fünf Karten und Mein Team, die App öffnet damit, das Logo führt dorthin: **ja**.
5. Mein Team einmal im Kopf wählen, gilt überall: **ja** (Browser-Speicher, kein Login).
6. D/ST-Faktoren und Positions-Matchup zu einer Ansicht „Matchups“ zusammenlegen, D/ST › Streaming entfällt: **ja**.
7. Schalter Einfach / Ausführlich, Standard **Einfach**: **ja**.
8. Spaltennamen: freigegeben sind die unstrittigen Umbenennungen aus Abschnitt 7 (Playoff % statt PO %, All-Play % statt AP %, Stärke statt μ, Projektion statt P, Faktor statt F, ausgeschriebene ROS- und Proj.-Kürzel usw.) und **Schwankung statt Konstanz**. **Nicht** freigegeben: Aufstellung % (Eff. % und die Ansicht „Coaching“ bleiben), Serie (Streak bleibt), Tief/Hoch (Floor und Ceiling bleiben). „ü. Ersatz“ heißt künftig **Vorteil** („Vorteil W5“, „Vorteil Rest Saison“). Die Tabellen in Abschnitt 7 und 8 sind entsprechend angepasst.
9. Lesart → **Erklärungen**: ja.
10. Reihenfolge der Pakete: **P1, P4, P2, P3, P5, P6**.
11. Beginn: erst dieses Dokument mit den Antworten nach `main`, der Umbau startet in einer neuen Session mit Paket P1.
