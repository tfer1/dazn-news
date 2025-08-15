# espn_league_scoring_pool_dynamic_ids_debug.py
import json
import time
from typing import Dict, Any, List, Optional

import numpy as np
import pandas as pd
import requests

# ========= CONFIG =========
SEASON = 2024
LEAGUE_ID = 1789825294                 # <-- your leagueId
SWID = "{4EAA2ED9-5A0B-4B4F-98AC-C936CBBD55D2}"  # <-- keep the braces
ESPN_S2 = "AEB25RwglR2d0hD%2B0AM7aiLYizvLWxZV9FZ9UuH0xVLzFpvQrDmVsOUv%2BtWwvtHQhWy2AJ0J2vrypvvfKE%2BDX5hl17%2BvLW6cmNGRHHeqG%2FddZCXDWbAqemajH%2BmJ4P236awJhsO%2BE7brIR8hG0szJbtfviz27c3RzNgBRP%2BUtowsrceJY1veP56k2gLo0fU%2Bz4%2Bm8E8Mxz9acGXa1iPxScXDBhLtYkM93RC%2BNxoI29sGhCSfdjzGk4M19NRaMXLeYRbOhZYHe0SSeKuZUqjwUI9frNWm6eoG665ulgOwa%2BlWx51ZMrsDuwhORplOX24Ta5GfDNICF60ofgCqLzGw2XSI"
OUTPUT_XLSX = "espn_league_points.xlsx"
# ==========================

BASE_SEASON = f"https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{SEASON}"
BASE_LEAGUE = f"{BASE_SEASON}/segments/0/leagues/{LEAGUE_ID}"
PLAYERS_POOL_URL = f"{BASE_LEAGUE}/players"

# ---------------- Helpers ----------------
def make_session():
    s = requests.Session()
    s.headers.update({"User-Agent": "Mozilla/5.0", "Accept": "application/json, text/plain, */*"})
    s.cookies.set("SWID", SWID, domain=".espn.com")
    s.cookies.set("espn_s2", ESPN_S2, domain=".espn.com")
    return s

def get_json(sess: requests.Session, url: str, params=None, headers=None, retries=3, sleep=1.2):
    for i in range(retries):
        r = sess.get(url, params=params, headers=headers, timeout=30)
        if r.status_code == 200:
            return r.json()
        print(f"[HTTP] {r.status_code} {r.url}")
        if r.status_code in (429, 502, 503, 504):
            time.sleep(sleep * (i + 1)); continue
        try: print("[HTTP] Body:", r.text[:800])
        except: pass
        r.raise_for_status()
    raise RuntimeError(f"GET failed {url}")

def _norm(s: str) -> str:
    s = (s or "").strip().lower()
    return " ".join(s.split())

# ------------- Start -------------
sess = make_session()

print("Loading platform settings…")
platform = get_json(sess, BASE_SEASON, params={"view": "chui_default_platformsettings"})
settings = platform["settings"]
team_map = {t["id"]: t["abbrev"] for t in settings["proTeams"]}
pos_map  = {p["id"]: p["name"] for p in settings["positions"]}
print(f"Loaded {len(team_map)} pro teams, {len(pos_map)} positions")

# ---- Build robust stat name index (handles dict/list/nested, abbreviations) ----
name_index: Dict[str, int] = {}

def _add_stat(sid: int | str, obj: dict):
    pieces = []
    for k in ("name", "shortName", "abbrev", "displayName"):
        v = obj.get(k)
        if isinstance(v, str) and v.strip():
            pieces.append(v)
    nm = _norm(" ".join(pieces))
    if nm:
        name_index[nm] = int(sid)

def _collect_stats(node):
    if isinstance(node, dict):
        # a stat object?
        if "id" in node and any(isinstance(node.get(k), str) for k in ("name","shortName","abbrev","displayName")):
            _add_stat(node["id"], node)
        for v in node.values():
            _collect_stats(v)
    elif isinstance(node, list):
        for it in node:
            _collect_stats(it)

_collect_stats(settings.get("statSettings", {}))
# league mSettings sometimes has extra names
try:
    msettings = get_json(sess, BASE_LEAGUE, params={"view": "mSettings"})
    _collect_stats(msettings.get("scoringSettings", {}).get("stats", []))
except Exception as e:
    print("mSettings fetch skipped/failed:", e)

print(f"Indexed {len(name_index)} stat names")

def find_id_by_keywords(*keywords: str) -> Optional[int]:
    """Exact or either-way substring match against name_index keys."""
    kws = [_norm(k) for k in keywords if k]
    # exact
    for k in kws:
        if k in name_index:
            return name_index[k]
    # contains (either way)
    for nm, sid in name_index.items():
        for k in kws:
            if k in nm or nm in k:
                return sid
    return None

def require_id(label: str, *keywords: str) -> int:
    sid = find_id_by_keywords(*keywords)
    if sid is None:
        print(f"\n[ID MISSING] {label} with any of: {keywords}")
        # helpful dump (first 40 likely-offensive)
        shown = 0
        for nm, sid0 in name_index.items():
            if any(tok in nm for tok in ("pass","rush","rec","target","fum","two","int","yd","td","att","comp")):
                print(f" - {nm} -> {sid0}")
                shown += 1
                if shown >= 40: break
        raise SystemExit(1)
    return sid

# ---- Resolve stat IDs (broad keywords to handle abbreviations) ----
ID_PASS_ATT = require_id("PASS_ATT", "passing attempts", "pass attempts", "pass att", "att")
ID_PASS_CMP = require_id("PASS_CMP", "completions", "passing completions", "pass comp", "comp")
ID_PASS_YDS = require_id("PASS_YDS", "passing yards", "pass yards", "pass yds")
ID_PASS_TD  = require_id("PASS_TD",  "passing touchdowns", "pass td")
ID_INT      = require_id("INT",      "interceptions", "interceptions thrown", "intt", "int")

ID_RUSH_ATT = require_id("RUSH_ATT", "rushing attempts", "rush attempts", "rush att")
ID_RUSH_YDS = require_id("RUSH_YDS", "rushing yards", "rush yards", "rush yds")
ID_RUSH_TD  = require_id("RUSH_TD",  "rushing touchdowns", "rush td")

ID_RECV_YDS = require_id("REC_YDS",  "receiving yards", "rec yards", "rec yds")
ID_RECV_TD  = require_id("REC_TD",   "receiving touchdowns", "rec td")
ID_TARGETS  = require_id("TARGETS",  "targets", "receiving targets", "tgt", "targets rec")

# Optional two-pointers (sum if present)
ID_2PT_PASS = find_id_by_keywords("two point passes made", "2pt pass", "two-pt pass")
ID_2PT_RUSH = find_id_by_keywords("two point rushes made", "2pt rush", "two-pt rush")
ID_2PT_REC  = find_id_by_keywords("two point receptions made", "2pt rec", "two-pt rec", "two point receptions")

ID_FUMBLES  = require_id("FUMBLES",  "lost fumbles", "fumbles lost", "fuml")

print("Resolved stat IDs:", {
    "PASS_ATT": ID_PASS_ATT, "PASS_CMP": ID_PASS_CMP, "PASS_YDS": ID_PASS_YDS, "PASS_TD": ID_PASS_TD, "INT": ID_INT,
    "RUSH_ATT": ID_RUSH_ATT, "RUSH_YDS": ID_RUSH_YDS, "RUSH_TD": ID_RUSH_TD,
    "REC_YDS": ID_RECV_YDS, "REC_TD": ID_RECV_TD, "TARGETS": ID_TARGETS,
    "2PT_PASS": ID_2PT_PASS, "2PT_RUSH": ID_2PT_RUSH, "2PT_REC": ID_2PT_REC,
    "FUMBLES": ID_FUMBLES
})

# Per-player “receptions” can be named weirdly (recs/rec); pick best id based on nonzero totals
def guess_receptions_id(totals: Dict[int, float]) -> Optional[int]:
    candidates: List[int] = []
    for nm, sid in name_index.items():
        if ("rec" in nm or "reception" in nm) and not ("yd" in nm or "yard" in nm):
            candidates.append(sid)
    # also try the common classic ids seen in feeds
    for hard in (41, 53):
        if hard not in candidates:
            candidates.append(hard)
    if not candidates:
        return None
    # choose the one with the largest value in this totals row
    return max(candidates, key=lambda i: totals.get(i, 0.0))

# ---- Fetch players pool (FA + Waivers + OnTeam + IR) ----
def first_non_empty_stats(players_like: List[dict]) -> Optional[List[dict]]:
    for p in players_like:
        s = p.get("player", {}).get("stats", [])
        if s: return s
    return None

def fetch_players_pool(session: requests.Session) -> List[dict]:
    f = {
        "players": {"limit": 10000, "offset": 0},
        "filterStatus": {"value": ["ONTEAM","FREEAGENT","WAIVERS","INJURED_RESERVE","UNKNOWN"]},
        "filterStatsForSeasonId": {"value": SEASON},
        "sortPercOwned": {"sortPriority": 1, "sortAsc": False},
    }
    hdr = {"x-fantasy-filter": json.dumps(f)}
    print("TRY pool:", list(f.keys()))
    batch = get_json(session, PLAYERS_POOL_URL, params={"view": "kona_player_info"}, headers=hdr)
    print("  → pool count:", len(batch), "has_stats:", bool(first_non_empty_stats(batch)))
    return batch

players_like = fetch_players_pool(sess)
print("USING SOURCE: players_pool | total:", len(players_like))

# ---- Helpers to read season rows ----
def pick_season_row(stats: List[dict]) -> Optional[dict]:
    rows = [s for s in stats if s.get("seasonId")==SEASON and s.get("statSplitTypeId")==0 and s.get("stats")]
    if not rows: return None
    rows.sort(key=lambda s: sum(1 for v in s["stats"].values() if float(v)!=0.0), reverse=True)
    return rows[0]

def season_totals(stats: List[dict]) -> Dict[int, float]:
    row = pick_season_row(stats)
    return {int(k): float(v) for k, v in row.get("stats", {}).items()} if row else {}

def games_played(stats: List[dict]) -> int:
    weeks = [s for s in stats if s.get("seasonId")==SEASON and s.get("statSplitTypeId")==1 and s.get("stats")]
    return len([w for w in weeks if any(float(v) > 0 for v in w["stats"].values())])

def iz(t: Dict[int, float], sid: Optional[int]) -> int:
    return int(t.get(int(sid), 0.0)) if sid is not None else 0

# ---- Build output ----
rows = []
kept = skipped = 0
for entry in players_like:
    info = entry.get("player", {})
    if not info: skipped += 1; continue
    pos_id = info.get("defaultPositionId")
    if pos_id not in {1,2,3,4}:  # QB,RB,WR,TE
        skipped += 1; continue

    stats = info.get("stats", [])
    totals = season_totals(stats)
    if not totals: skipped += 1; continue

    rec_id = guess_receptions_id(totals)
    two_pt = 0
    for i in (ID_2PT_PASS, ID_2PT_RUSH, ID_2PT_REC):
        if i: two_pt += totals.get(i, 0.0)

    rows.append({
        "Name": f"{info.get('firstName','')} {info.get('lastName','')}".strip(),
        "Team": team_map.get(info.get("proTeamId"), "FA"),
        "Position": pos_map.get(pos_id, "UNK"),
        "Games": games_played(stats),
        "Comp":    iz(totals, ID_PASS_CMP),
        "Att":     iz(totals, ID_PASS_ATT),
        "PassYds": iz(totals, ID_PASS_YDS),
        "PassTD":  iz(totals, ID_PASS_TD),
        "INT":     iz(totals, ID_INT),
        "RushAtt": iz(totals, ID_RUSH_ATT),
        "RushYds": iz(totals, ID_RUSH_YDS),
        "RushTD":  iz(totals, ID_RUSH_TD),
        "Rec":     iz(totals, rec_id),
        "RecYds":  iz(totals, ID_RECV_YDS),
        "RecTD":   iz(totals, ID_RECV_TD),
        "Targets": iz(totals, ID_TARGETS),
        "TwoPt":   int(two_pt),
        "Fumbles": iz(totals, ID_FUMBLES),
    })
    kept += 1

print(f"Players kept (offense w/season totals): {kept} | skipped: {skipped}")

if not rows:
    first = players_like[0] if players_like else {}
    print("SAMPLE_PLAYER_JSON:", json.dumps(first, indent=2)[:1200])
    raise RuntimeError("No season rows parsed. Check SEASON or ESPN response shape.")

raw_df = pd.DataFrame(rows).sort_values(["Position","Name"]).reset_index(drop=True)

# ---- Scoring (from your league PDF) ----
CFG = {
    "pass_yards_pts_per_yard": 0.04,
    "rush_yards_pts_per_yard": 0.10,
    "rec_yards_pts_per_yard":  0.10,
    "pass_td_points": 4,
    "rush_td_points": 6,
    "rec_td_points":  6,
    "int_points":     -2,
    "ppr":            1.0,
    "two_pt_points":  2,
    "fumble_lost_points": -2,
    "bonuses": []
}

def calc_points(r: pd.Series, c: Dict[str, float]) -> float:
    return (
        r["PassYds"]*c["pass_yards_pts_per_yard"] +
        r["RushYds"]*c["rush_yards_pts_per_yard"] +
        r["RecYds"] *c["rec_yards_pts_per_yard"] +
        r["PassTD"]*c["pass_td_points"] +
        r["RushTD"]*c["rush_td_points"] +
        r["RecTD"] *c["rec_td_points"] +
        r["Rec"]   *c["ppr"] +
        r["TwoPt"] *c["two_pt_points"] +
        r["INT"]   *c["int_points"] +
        r["Fumbles"]*c["fumble_lost_points"]
    )

scored = raw_df.copy()
scored["FPTS"] = scored.apply(lambda r: calc_points(r, CFG), axis=1)
scored["FPTS/G"] = scored["FPTS"] / scored["Games"].replace(0, np.nan)
scored["PosRank"] = scored.groupby("Position")["FPTS"].rank(ascending=False, method="min")

with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as wb:
    pd.DataFrame([{
        "Season": SEASON,
        "LeagueId": LEAGUE_ID,
        "Notes": "IDs auto-discovered; pool includes FA+Waivers+OnTeam+IR",
        **CFG
    }]).to_excel(wb, sheet_name="Info", index=False)
    raw_df.to_excel(wb, sheet_name="Raw_Stats", index=False)
    scored.to_excel(wb, sheet_name="League_Scoring", index=False)

print(f"Wrote {OUTPUT_XLSX}")
