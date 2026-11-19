"""Sondeo único (no forma parte del sistema): mira qué mercados de jugador ofrece The Odds API para
liga y Champions y qué devuelve API-Football por jugador. Solo stdlib. No imprime ninguna clave."""

import json
import os
import urllib.error
import urllib.parse
import urllib.request

ODDS = "https://api.the-odds-api.com"
AF = "https://v3.football.api-sports.io"


def get(url: str, headers: dict[str, str] | None = None) -> tuple[int, dict | list | str, dict]:
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310
            body, status, hdr = r.read().decode(), r.status, dict(r.headers)
    except urllib.error.HTTPError as e:
        body, status, hdr = e.read().decode(), e.code, dict(e.headers)
    try:
        return status, json.loads(body), hdr
    except ValueError:
        return status, body[:300], hdr


def odds_probe() -> None:
    key = os.environ["ODDS_API_KEY"]
    for sport in ("soccer_spain_la_liga", "soccer_uefa_champs_league"):
        print(f"\n## Odds API {sport}")
        st, events, _ = get(f"{ODDS}/v4/sports/{sport}/events?apiKey={key}")
        if st != 200 or not isinstance(events, list) or not events:
            print("eventos:", st, str(events)[:200])
            continue
        print("eventos próximos:", len(events), "·", events[0]["home_team"], "-", events[0]["away_team"])
        ev = events[0]["id"]
        q = urllib.parse.urlencode({"apiKey": key, "regions": "eu,uk"})
        st, data, hdr = get(f"{ODDS}/v4/sports/{sport}/events/{ev}/markets?{q}")
        print("markets:", st, "créditos restantes:", hdr.get("x-requests-remaining"))
        if st != 200 or not isinstance(data, dict):
            print(str(data)[:300])
            continue
        per_market: dict[str, list[str]] = {}
        for bk in data.get("bookmakers", []):
            for m in bk.get("markets", []):
                per_market.setdefault(m["key"], []).append(bk["key"])
        for m, bks in sorted(per_market.items()):
            if m.startswith(("player", "goalkeeper")) or "save" in m or "shot" in m:
                print(f"  {m}: {len(bks)} casas -> {', '.join(sorted(bks)[:8])}")
        print("  (otros mercados:", ", ".join(sorted(k for k in per_market if not k.startswith("player")))[:200], ")")


def af_probe() -> None:
    key = os.environ["API_FOOTBALL_KEY"]
    h = {"x-apisports-key": key}
    st, d, hdr = get(f"{AF}/status", h)
    if isinstance(d, dict):
        req = d.get("response", {}).get("requests") if isinstance(d.get("response"), dict) else None
        print("\n## API-Football status", st, "plan:", (d.get("response") or {}).get("subscription") if isinstance(d.get("response"), dict) else d, "requests:", req, "errors:", d.get("errors"))
    for name, league in (("LaLiga", 140), ("Champions", 2)):
        for season in (2026, 2025):
            st, d, hdr = get(f"{AF}/fixtures?league={league}&season={season}&last=3", h)
            resp = d.get("response") if isinstance(d, dict) else None
            print(f"\n## {name} temporada {season}: HTTP {st} errores={d.get('errors') if isinstance(d, dict) else d} partidos={len(resp or [])} restantes/día={hdr.get('x-ratelimit-requests-remaining')}")
            if resp:
                fx = resp[0]["fixture"]["id"]
                st, p, _ = get(f"{AF}/fixtures/players?fixture={fx}", h)
                teams = p.get("response", []) if isinstance(p, dict) else []
                print(f"  fixtures/players {fx}: HTTP {st} equipos={len(teams)} errores={p.get('errors') if isinstance(p, dict) else p}")
                if teams and teams[0].get("players"):
                    one = teams[0]["players"][0]
                    print("  ejemplo jugador:", one["player"]["name"], json.dumps(one["statistics"][0])[:600])
                    gk = [pl for t in teams for pl in t["players"] if pl["statistics"][0]["games"].get("position") == "G"]
                    if gk:
                        print("  ejemplo portero:", gk[0]["player"]["name"], json.dumps(gk[0]["statistics"][0].get("goals")))
                break


if __name__ == "__main__":
    odds_probe()
    af_probe()
