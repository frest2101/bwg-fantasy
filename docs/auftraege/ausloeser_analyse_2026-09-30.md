# Auslöser-Fähnchen D/ST und Positions-Matchup – Analyse und Beschluss (30.09.2026)

Anlass: Nach W3 trugen im Positions-Matchup (Session 8) je Position 10–19 von 32 Defenses ein ⚑ (mit Vorjahr 5–14), bei
den D/ST-Faktoren 4 von 32. Stephan wollte die Fähnchen genauer verstehen und neu definieren.

## Herkunft und Regeln bis 30.09.2026
- Herkunft: „Warum-Abfrage“ des D/ST-Boards in Notion (August 2026). Die Fähnchen waren eine Arbeitsliste: Claude sollte je
  markiertem Team die Ursache recherchieren (QB-Ausfall, Coordinator-Wechsel, Verletzungswelle), höchstens 3 Teams je Woche
  als Rückfrage; die Entscheidung, dem Faktor zu folgen, lag bei Stephan. Seit 29.09. entfiel dieser Schritt („Kontext Warum“),
  die Fähnchen standen ohne Folgeschritt in der App.
- Regeln (ein Treffer genügt): |ΔF| ≥ 0,10 zur Vorwoche · Rangsprung ≥ 5 · nur D/ST: z = (Ø Z letzte 3 − Z26)/(0,55·LS26·√(1/3 − 1/n)),
  |z| ≥ 2 ab 4 Spielen, dazu „beobachten“ = die drei größten |z|. Positions-Matchup: „wie D/ST“ ohne z (Vorschlag Session 8).

## Methode
- **Probelauf:** Saison 2025 Woche für Woche wie in der App, Vorjahr 2024 (ESPN `leaguedefaults/3`, nur lesend, nicht im Repo),
  Liga-Scoring 2026 aus den Rohstats, Funktionen aus `dst.py`; D/ST und Positionen QB, RB, WR, TE, K.
- **Zufallsmodell:** 4000 simulierte Saisons mit den gemessenen Parametern (Streuung je Spiel, echte Unterschiede zwischen
  Defenses, Vorjahreskorrelation), zuerst ohne jede echte Veränderung (jedes Fähnchen = Fehlalarm), dann mit einer echten
  Veränderung der Stärke um ±20/40/60 % ab W4, W7 oder W10.
- Die Kernzahl (Korrelation 2024 → 2025) ist unabhängig nachgerechnet.

## Ergebnisse
**Fehlalarm im Zufallsmodell** (Anteil markierter Zellen je Woche, Ø W1–14) und echt 2025:

| Regel | QB | RB | WR | TE | K | D/ST | echt 2025 (W1–14) Positionen / D/ST |
|---|---|---|---|---|---|---|---|
| bisher (ΔF oder Rangsprung; D/ST mit z) | 16,8 % | 15,5 % | 20,0 % | 16,7 % | 18,7 % | 11,2 % | 19,0 % / 8,3 % |
| Rangsprung erst ab 4 Spielen | 10,1 % | 9,4 % | 12,4 % | 10,9 % | 12,2 % | 7,7 % | 11,6 % / 5,8 % |
| nur \|z\| ≥ 2 (gemessene Streuung) | 3,6 % | 3,7 % | 3,6 % | 3,6 % | 3,6 % | 3,5 % | 2,5 % / 4,2 % |
| nur \|z\| ≥ 2,5 | 1,0 % | 1,2 % | 1,1 % | 1,2 % | 1,0 % | 1,0 % | – |

- Die bisherigen Fähnchen markierten also rein zufällig mindestens so viele Zellen wie in echt – sie waren nicht von Zufall zu unterscheiden.
  Grund: Die F-Werte liegen dicht, Rangsprung-Fähnchen hatten 2025 im Median nur |ΔF| = 0,044; 32 % der Rangsprünge kehrten
  sich in der Folgewoche um. ΔF ≥ 0,10 reagiert fast nur nach oben (ΔF ≈ (x − F)/(n + 11), x = Wert des neuen Spiels, bei gleichem Ligaschnitt) und wird im
  Saisonverlauf stumpf.
- **Trefferquote:** Eine echte Veränderung der Stärke um ±20 % erkennt z ≥ 2 innerhalb von 3 Wochen nur zu etwa 13 %
  – kaum mehr als die etwa 10 %, mit denen dieselbe Regel eine unveränderte Defense in 3 Wochen zufällig markiert; ±40 % zu
  17–26 %. Einzelne Spiele streuen zu stark.
- **Nutzen:** Kein Fähnchen verbesserte 2025 die Vorhersage der nächsten 3 Spiele (Verbesserung markiert vs. unmarkiert im
  Rahmen des Zufalls; bisherige Regel: Richtung trifft 52 % vs. 53 %). Einziges leichtes Gegensignal: Bei den Positionen
  setzte sich nach |z| ≥ 2 die Abweichung von F in den nächsten 3 Spielen leicht fort (55 Zellen, 62 % in z-Richtung,
  Ø 0,10 Ligaschnitt, Intervall 0,01–0,18), bei D/ST umgekehrt – eine Saison, nicht gegen Mehrfachtests abgesichert.
- **Streuung je Spiel** (CV, Grundlage eines z): QB 0,48 · RB 0,48 · WR 0,45 · TE 0,66 · K 0,59 · D/ST 0,54 (bisher angenommen 0,55) – Streuung der Positionssumme je Defense
  (D/ST je Offense), nicht die Spieler-CV der Trendregel.

**Das Positions-Matchup selbst ist ein schwacher Hinweis:**

| | QB | RB | WR | TE | K | D/ST |
|---|---|---|---|---|---|---|
| Korrelation Z 2024 → 2025 je Defense (D/ST je Offense) | 0,08 | 0,19 | −0,13 | 0,24 | 0,17 | 0,43 |
| Split-Half 2025 (gerade/ungerade Wochen) | 0,31 | 0,16 | 0,15 | 0,28 | 0,53 | – |
| Fehler nächste 3 Spiele: F heute | 0,239 | 0,243 | 0,216 | 0,316 | 0,281 | – |
| … F mit 5 Spielen Vorjahr + 25 Ligamittel | 0,241 | 0,241 | 0,215 | 0,318 | 0,276 | – |
| … nur 1,00 (kein Matchup) | 0,247 | 0,245 | 0,217 | 0,326 | 0,276 | – |

Stärkerer Zug zum Ligamittel ließ die Rangfolge praktisch gleich (Rangkorrelation 0,999–1,000 in W8), halbierte die Spanne
der F-Werte und verbesserte die Vorhersage 2025 nicht messbar. Das F schlägt „kein Matchup“ nur knapp (außer K).

**Grenzen:** eine Saison (2025) als Probelauf; bei D/ST wenige markierte Zellen, breite Unsicherheit. Das Ergebnis heißt
„kein messbarer Nutzen“, nicht „bewiesen null“.

## Beschluss Stephan (30.09.2026)
- Keine Auslöser-Fähnchen mehr, weder bei den D/ST-Faktoren noch im Positions-Matchup (auch kein z, kein „beobachten“).
  ΔF, Rang der Vorwoche und „Z letzte 3“ bleiben als Werte. Das ⚑ bedeutet in der App damit nur noch Wetter.
- Formel des Positions-Matchups bleibt die Saison über fest; Rückschau nach W17 mit den Daten 2026 (Gewicht des Ligamittels).
  Die App beschriftet das Matchup als schwachen Hinweis.
