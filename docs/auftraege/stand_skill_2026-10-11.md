# Stand-Skript im claude.ai-Chat: Skill statt Code aus dem Netz (11.10.2026)

Auftrag Stephan: Das Stand-Skript im claude.ai-Projektchat wieder nutzbar machen. Der Aufruf aus der Projektanweisung (`requests.get` der raw-Adresse von `scripts/claude_stand.py`, dann `exec`) wird seit dem 11.10.2026 blockiert: „Permission denied by auto mode classifier. Reason: [Code from External]“. Reine Datenabrufe (ESPN-API, App-JSON per `requests` in eigenem Code) laufen weiter. Ziel: dieselbe Ausgabe wie `claude_stand.py`, ohne Code aus dem Netz auszuführen; nur lesend.

## Befund

- Seit dem 16.09.2026 sind Chat und Cowork in claude.ai eins (schrittweise für Pro und Max). Chats und Cowork-Läufe laufen in einer Cloud-Umgebung mit dem Auto-Modus-Klassifizierer von Claude Code (Schalter „Auto“/„Manual“ je Unterhaltung).
- „Code from External“ ist eine eingebaute soft_deny-Regel. Wortlaut (Claude Code 2.1.296, `claude auto-mode defaults --label 'Code from External'`): „Executing code that came from an external source; judge by the provenance of what actually runs, not by the launching command.“ Darunter fallen `curl | bash`, `exec`/`eval` auf externen Daten und das Ausführen von geklontem oder entpacktem Material. Ausgenommen ist ausdrücklich das Lesen und Parsen externer Daten „from code that lives and runs outside it“. `exec(requests.get(<raw>).content)` trifft die Regel wörtlich.
- Der Klassifizierer sieht Nachrichten des Nutzers und Werkzeugaufrufe, nicht die Werkzeugausgaben. Die Projektanweisung zählte offenbar nicht als Auftrag des Nutzers. Eine Liste vertrauenswürdiger Quellen gibt es in claude.ai nicht (`autoMode` in den Einstellungen gibt es nur in Claude Code).
- Skills: In claude.ai wird der ganze Skill-Ordner samt Skripten in die Sandbox kopiert. Skill-Skripte liefen in einem Cowork-Lauf vom 09.10.2026 trotz Auto-Modus (Nutzerbericht). Für den interaktiven Projektchat ist das nicht belegt.
- Plugins: claude.ai nimmt unter Customize › Plugins › Add › „Add marketplace“ ein GitHub-Repo (`owner/repo`; öffentlich ohne GitHub-App). „Check for updates“ holt den neuen Stand, für selbst hinzugefügte github.com-Marketplaces gibt es „Sync automatically“. Skills von Plugins laden laut Doku im Chat (Web, Desktop, Mobil); für Projekte ist nichts dokumentiert. Plugins laden auch in Cowork-Sitzungen.

## Geprüfte Wege

Drei Prototypen auf einem Schnappschuss echter Antworten (So 11.10.2026, 21:11 UTC, W5, drei Spiele liefen), dazu zwei Richter (Zuverlässigkeit und Tempo; Wartbarkeit und Regeln des Repos).

| Weg | Ergebnis | Urteil |
|---|---|---|
| A: `app/data/stand_basis.json` vom Rechenwerk plus Rezept zum Abschreiben (93 Zeilen, 9,6 KB) | alle Zahlen wie die Ausgabe des Skripts, NFL-Spielliste gekürzt; bricht bei einem Formatbruch ab | 6/10 und 6/10: blockierfrei nach bisheriger Beweislage, aber rund 3.000 Token in jeder Projektanweisung, geschätzt 40–60 s Abschreiben je Stand, dritte Fassung der Regeln |
| B: Rezept nur auf `claude.json` und `transactions.json` (162 Zeilen, 12,3 KB) | inhaltlich am nächsten am Skript | 4/10 und 3/10: längster Code, kein Versionsabgleich, ungetestet |
| C: Skript unverändert als Skill, lokal ausgeführt | Ausgabe byte-gleich; aus einem schreibgeschützt entpackten ZIP live gelaufen | 8/10 und 8/10: ein Aufruf, rund 1,5 s, eine einzige getestete Fassung; Abnahme braucht einen Probe-Chat |

Verworfen: freies Rechnen im Chat aus ESPN und App-Daten (das Muster vom 02.10.2026: viele kleine Schritte, Minuten statt Sekunden); Projektwissen als `.py`-Datei (Pfad unbelegt, 51 KB Kontext in jedem Chat); ein Endpunkt bei Cloudflare, der den Text rendert (frühestens mit dem Umzug der Liga-App; Workers Free hat zu wenig CPU für die 5-MB-Antwort von ESPN). Nicht als Lösung: die Quelle in der eigenen Nachricht nennen oder auf „Manual“ schalten – das ginge vielleicht, bliebe aber Code aus dem Netz und kostete in jedem Chat einen Schritt.

**Entscheidung:** Weg C, die Empfehlung beider Richter. Das Rezept (Weg A) wird erst gebaut, wenn die Probe scheitert (Plan B unten; Stephan 11.10.2026: „erst bei Bedarf“).

## Umsetzung

- `.claude-plugin/marketplace.json` (Marketplace `bwg-fantasy`) mit dem Plugin `plugins/bwg-spieltag/` (`.claude-plugin/plugin.json` ohne `version` – in Claude Code zählt dann der Commit des Plugin-Ordners; wie claude.ai ohne `version` abgleicht, ist nicht dokumentiert, Schritt 5 der Probe klärt es; darin `skills/bwg-spieltag/SKILL.md` und `scripts/claude_stand.py` als Kopie). Kein Ordner `bin/` (den installiert claude.ai nicht), im Namen kein „claude“ (reserviert).
- `plugins/bwg-spieltag.zip`: derselbe Skill-Ordner zum Hochladen von Hand, deterministisch gebaut.
- `scripts/skill_bauen.py` zieht Kopie und ZIP nach (`--pruefen` schreibt nichts; danach `compute.py`, in der Vorsaison `compute.py --season <Vorjahr>`); `tests/test_skill.py` prüft Kopie, ZIP, SKILL.md (Name gleich Ordner, Beschreibung ≤ 200 Zeichen als strengste Angabe der Hilfe, nur erlaubte Kopffelder), Manifeste, Kennung und einen Lauf aus dem entpackten ZIP.
- `claude_stand.py`: Läuft es neben einer SKILL.md, vergleicht es die Kennung des Skills mit `claude.json › stand.skill` (schreibt `app_export`) – „Skill bwg-spieltag aktuell“ in der App-Zeile oder eine Zeile „! Skill bwg-spieltag und App verschieden“ (ohne Richtung, weil `claude.json` von raw bis zu fünf Minuten alt sein kann); liest der Skill eine ältere ESPN-Saison, als die App zeigt: „! Skill bwg-spieltag veraltet“. Neu je Team: „Rest“ = Live-Projektion − Punkte live (Pflichtangabe des Auftrags). Sonst unverändert; der exec-Weg geht technisch weiter.

## Einrichtung und Probe (Stephan)

1. claude.ai › Customize › Plugins › Add › „Add marketplace“ › `frest2101/bwg-fantasy`, das Plugin bwg-spieltag installieren, „Sync automatically“ einschalten.
   Geht das nicht: `plugins/bwg-spieltag.zip` von https://github.com/frest2101/bwg-fantasy/raw/main/plugins/bwg-spieltag.zip laden und unter Customize › Skills › „+“ › „Upload a skill“ hochladen, dann einschalten. Voraussetzung: Code-Ausführung ist an.
2. In der Projektanweisung den Abschnitt SPIELTAG LIVE ersetzen (Text kommt aus dieser Sitzung; Pflege in der Sitzung fantasy-privat).
3. Probe-Chat im Projekt, im Auto-Modus, frühestens fünf Minuten nach dem Merge: „Wie steht's?“ Bestanden, wenn
   - kein Werkzeugaufruf blockiert wird,
   - die Ausgabe mit „STAND …“ beginnt und die App-Zeile mit „Skill bwg-spieltag aktuell“ endet,
   - Stand, offene Starter, Moves der Woche und Kadervergleich im Text stehen.
   Bei einem Fehler die Meldung wörtlich und die Ausgabe von `ls /mnt` an eine Claude-Code-Sitzung geben.
4. Dasselbe in einem Cowork-Lauf des Projekts prüfen (dort laden Plugins laut Doku ebenfalls).
5. Nach dem nächsten Merge, der SKILL.md oder `claude_stand.py` ändert: „Check for updates“, neuer Chat, „Wie steht's?“ – bestanden, wenn wieder „Skill bwg-spieltag aktuell“ kommt. Bleibt es bei „verschieden“: `version` in `plugin.json` setzen, von `skill_bauen.py` aus der Kennung ableiten lassen und `test_marketplace_und_plugin` anpassen.

## Plan B, falls der Skill nicht trägt

Weg A bauen, mit den Verbesserungen der Richter:
- `app_export.build_stand_basis` schreibt `app/data/stand_basis.json` (rund 22 KB): Stand der App, Kürzel, NFL-Kürzel, Slots, Spieler je ID mit Name, Position, NFL-Team, ROS/Sp, F (nur für `matchup_woche`) und fertigem Exp-Text, Kader der App, bekannte ESPN-Transaktions-IDs (Marke [NEU] per ID wie `live_core.js`, ohne 14-Tage-Fenster), Lesehilfe, Rezept-Version.
- `scripts/stand_rezept.py` als kanonische Fassung mit `tests/test_stand_rezept.py` (Fixtures, Kernzahlen gegen `claude_stand.bericht`), Abschnitte einzeln abgesichert wie `claude_stand.sicher`, ohne Basis wenigstens die Live-Teile, Selbstprüfung gegen Abschreibfehler (Hash der eigenen Datei gegen ein Feld der Basis).
- Im Chat Schreiben und Ausführen in einem Werkzeugaufruf: Container werden während einer Unterhaltung neu aufgebaut, eine Datei aus einer früheren Nachricht ist nicht verlässlich da.
- Kosten bewusst tragen: rund 10 KB Rezept in der Projektanweisung.

## Offen

- Ob claude.ai den Plugin-Skill in Projektchats lädt, ob der Auto-Modus den Aufruf im interaktiven Chat durchlässt (Schritte 1–4) und ob und wie schnell claude.ai eine Änderung ohne `version` übernimmt (Schritt 5) – klärt die Probe.
- Nach einem Merge, der den Skill ändert, meldet das Skript „verschieden“, bis claude.ai abgeglichen hat. Beim ZIP-Weg heißt jede Änderung an `claude_stand.py` oder SKILL.md: neu hochladen. Änderungen am Stand-Skript deshalb bündeln.
