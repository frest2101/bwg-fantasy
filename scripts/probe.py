"""Probe-Lauf (Session 6): sind Open-Meteo und die ESPN-Site-API aus der GitHub Action erreichbar, und was liefern sie?

Fragt jede Quelle einmal ab und schreibt die Antworten gekürzt ins Log – nichts wird gespeichert oder committet.
Grundlage für die Entscheidung, welche Wetter- und News-Quelle der Tageslauf nutzt (docs/auftraege/session6.md, Punkt 1).
Jede Quelle wird für sich geprüft; ein Fehler bei einer Quelle stoppt die anderen nicht, der Exit-Code bleibt 0.

Aufruf: python scripts/probe.py            # lokal oder in .github/workflows/probe.yml (workflow_dispatch)
"""

import json
import sys
from datetime import date, datetime, timedelta, timezone

import requests

import espn_fetch as ef

TIMEOUT = 30
OPEN_METEO = "https://api.open-meteo.com/v1/forecast"
HOURLY = "temperature_2m,wind_speed_10m,wind_gusts_10m,precipitation_probability,precipitation,snowfall"
SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/football/nfl/scoreboard"
PLAYER_NEWS = "https://site.api.espn.com/apis/fantasy/v2/games/ffl/news/players"
ATHLETE_OVERVIEW = "https://site.web.api.espn.com/apis/common/v3/sports/football/nfl/athletes/{id}/overview"
CLEVELAND = (41.506, -81.699)          # Huntington Bank Field, offenes Stadion (TNF-Spielort in W4)
LONDON = (51.604, -0.066)              # Tottenham Hotspur Stadium (Auslandsspiel W4)
PROBE_PLAYER = 3139477                 # ESPN-Athleten-ID eines bekannten QB (öffentliche ID, Test der News-Abfrage)


def title(text: str) -> None:
    print(f"\n=== {text} ===")


def get(session: requests.Session, url: str, params) -> tuple[int, dict | list | str]:
    """GET mit Status; JSON, wenn möglich, sonst Text (gekürzt)."""
    resp = session.get(url, params=params, timeout=TIMEOUT)
    try:
        return resp.status_code, resp.json()
    except ValueError:
        return resp.status_code, resp.text[:300]


def hour(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:00")


def probe_open_meteo(session: requests.Session, now: datetime) -> None:
    """Prognose (2 Tage voraus), Ist (2 Tage zurück, Analysewerte) und der erlaubte Zeitbereich von start_hour."""
    title("Open-Meteo: Prognose, Stundenwerte ab Kickoff (+3 h), Cleveland und London, 2 Tage voraus")
    ahead = now + timedelta(days=2)
    for name, (lat, lon) in (("Cleveland", CLEVELAND), ("London", LONDON)):
        status, data = get(session, OPEN_METEO, {"latitude": lat, "longitude": lon, "timezone": "UTC", "hourly": HOURLY,
                                                 "start_hour": hour(ahead), "end_hour": hour(ahead + timedelta(hours=3))})
        print(f"{name}: HTTP {status}")
        if isinstance(data, dict) and "hourly" in data:
            print("  Einheiten:", data.get("hourly_units"))
            print("  Werte:    ", json.dumps(data["hourly"]))
        else:
            print("  Antwort:", str(data)[:300])

    title("Open-Meteo: Ist-Wetter (Analysewerte, kein Stationsmesswert), Cleveland, 2 Tage zurück")
    back = now - timedelta(days=2)
    status, data = get(session, OPEN_METEO, {"latitude": CLEVELAND[0], "longitude": CLEVELAND[1], "timezone": "UTC",
                                             "hourly": HOURLY, "start_hour": hour(back), "end_hour": hour(back + timedelta(hours=3))})
    print(f"HTTP {status}")
    print("  Werte:", json.dumps(data.get("hourly")) if isinstance(data, dict) else str(data)[:300])

    title("Open-Meteo: past_days=2 als Alternative (liefert Vergangenheit und Zukunft in einer Antwort)")
    status, data = get(session, OPEN_METEO, {"latitude": CLEVELAND[0], "longitude": CLEVELAND[1], "timezone": "UTC",
                                             "hourly": "temperature_2m", "past_days": 2, "forecast_days": 1})
    times = (data.get("hourly") or {}).get("time", []) if isinstance(data, dict) else []
    print(f"HTTP {status}, {len(times)} Stunden von {times[0] if times else '?'} bis {times[-1] if times else '?'}")

    title("Open-Meteo: erlaubter Zeitbereich von start_hour (Fehlertext nennt ihn)")
    status, data = get(session, OPEN_METEO, {"latitude": CLEVELAND[0], "longitude": CLEVELAND[1], "hourly": "temperature_2m",
                                             "start_hour": hour(now - timedelta(days=200)), "end_hour": hour(now - timedelta(days=200, hours=-3))})
    print(f"HTTP {status}: {data}")


def probe_scoreboard(session: requests.Session, season: int, week: int) -> None:
    """ESPN-Scoreboard: je Spiel Anstoß, Spielort mit indoor-Flag, neutraler Ort, ESPN-Wetter (AccuWeather) und Status."""
    for wk, label in ((week, "laufende Woche"), (max(week - 1, 1), "Vorwoche")):
        title(f"ESPN-Site-API: Scoreboard W{wk} ({label})")
        status, data = get(session, SCOREBOARD, {"seasontype": 2, "week": wk, "dates": season})
        events = data.get("events", []) if isinstance(data, dict) else []
        print(f"HTTP {status}, {len(events)} Spiele")
        for e in events:
            comp = e["competitions"][0]
            venue, weather = comp.get("venue") or {}, e.get("weather") or {}
            teams = "@".join(t["team"]["abbreviation"] for t in sorted(comp["competitors"], key=lambda t: t["homeAway"] != "away"))
            print(f"  {e['id']} {e['date']} {teams:<8} {venue.get('fullName', '?'):<28} "
                  f"{(venue.get('address') or {}).get('city', '?'):<16} indoor={venue.get('indoor')!s:<5} "
                  f"neutral={comp.get('neutralSite')!s:<5} wetter={weather.get('displayValue')!s:<18} "
                  f"{weather.get('temperature')!s:>4}°F  {comp.get('status', {}).get('type', {}).get('name')}")


def probe_news(session: requests.Session) -> None:
    """ESPN-News je Spieler: Fantasy-Feed (Rotowire-Meldungen und ESPN-Stories) und Athleten-Übersicht."""
    title("ESPN-Site-API: Fantasy-News je Spieler (news/players?playerId=…&days=30)")
    status, data = get(session, PLAYER_NEWS, {"playerId": PROBE_PLAYER, "days": 30})
    feed = data.get("feed", []) if isinstance(data, dict) else []
    print(f"HTTP {status}, {len(feed)} Meldungen, Schlüssel je Meldung: {sorted(feed[0]) if feed else '–'}")
    for item in feed[:4]:
        links = item.get("links") or {}
        print(f"  {item.get('type'):<9} {item.get('published')}  id={item.get('id')}  playerId={item.get('playerId')}  "
              f"Schlagzeile {len(item.get('headline') or '')} Zeichen: „{(item.get('headline') or '')[:60]}…“  "
              f"Links: {sorted(links)}  web={bool((links.get('web') or {}).get('href'))}")
    status, data = get(session, PLAYER_NEWS, [("playerId", PROBE_PLAYER), ("playerId", PROBE_PLAYER + 1), ("days", 30)])
    print(f"Zwei Spieler in einer Anfrage (playerId doppelt): HTTP {status}, "
          f"{len(data.get('feed', [])) if isinstance(data, dict) else '?'} Meldungen")

    title("ESPN-Site-API: Athleten-Übersicht (common/v3 … /athletes/<id>/overview → news)")
    status, data = get(session, ATHLETE_OVERVIEW.format(id=PROBE_PLAYER), {})
    news = data.get("news") if isinstance(data, dict) else None
    items = news if isinstance(news, list) else (news or {}).get("items") or (news or {}).get("articles") or []
    print(f"HTTP {status}, Schlüssel: {sorted(data) if isinstance(data, dict) else '?'}, {len(items)} News")
    for item in items[:3]:
        print(f"  {item.get('type'):<9} {item.get('published')}  „{(item.get('headline') or '')[:60]}…“  "
              f"web={bool(((item.get('links') or {}).get('web') or {}).get('href'))}")


def main() -> int:
    sys.stdout.reconfigure(errors="replace", line_buffering=True)
    now = datetime.now(timezone.utc)
    season = ef.DEFAULT_SEASON
    week = min(max(ef.calendar_week(season, now.date()), 1), ef.MAX_WEEK)
    print(f"Probe-Lauf {now:%Y-%m-%d %H:%M} UTC, Saison {season}, Kalenderwoche W{week}")
    with requests.Session() as session:
        for name, job in (("Open-Meteo", lambda: probe_open_meteo(session, now)),
                          ("ESPN-Scoreboard", lambda: probe_scoreboard(session, season, week)),
                          ("ESPN-News", lambda: probe_news(session))):
            try:
                job()
            except Exception as exc:  # noqa: BLE001 – jede Quelle für sich melden, der Lauf geht weiter
                print(f"\n{name}: FEHLER – {type(exc).__name__}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
