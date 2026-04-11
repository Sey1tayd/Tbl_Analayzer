"""
TBF (Türkiye Basketbol Federasyonu) API ve HTML scraper.

Strateji:
1. get-leagues-and-seasons-by-prefix  -> güncel sezon ID ve faaliyet ID
2. get-teams-by-leauge                -> o ligin takım listesi
3. get-team-detail-matches-by-season-and-league  -> tüm maçlar (matchId dahil)
4. /ligler/{leagueSlug}/mac-detay/{matchId} HTML -> NUXT_DATA hakem/salon parse
"""
import json
import re
import time
import logging
import requests
try:
    from curl_cffi import requests as cf_requests
    USE_CURL_CFFI = True
except ImportError:
    USE_CURL_CFFI = False

logger = logging.getLogger(__name__)

BASE_API = "https://miniappapi.tbf.org.tr/webapi-service/api"
BASE_WEB = "https://www.tbf.org.tr"

HEADERS_API = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Origin": "https://www.tbf.org.tr",
    "Referer": "https://www.tbf.org.tr/",
    "Accept": "application/json, text/plain, */*",
}

HEADERS_WEB = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://www.tbf.org.tr/",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

LEAGUE_PREFIXES = {
    "BSL":  "BSL",
    "KBSL": "KBSL",
    "TBL":  "TBL",
    "TKBL": "TKBL",
    "TB2L": "TB2L",
    "BGL":  "BGL",
    "BGLK": "BGLK",
    "EBBL": "EBBL",
    "KBBL": "KBBL",
}


def _api(session, path, params=None):
    url = f"{BASE_API}/{path}"
    resp = session.get(url, params=params, timeout=15)
    resp.raise_for_status()
    return resp.json()


def get_current_season(session, prefix):
    """Lig için güncel (en son) sezon bilgisini döndürür."""
    data = _api(session, "League/get-leagues-and-seasons-by-prefix", {"prefix": prefix})
    seasons = data.get("data", [])
    if not seasons:
        raise ValueError(f"[{prefix}] Sezon verisi bulunamadı.")
    # İlk (en güncel) sezon
    s = seasons[0]
    return {
        "faaliyet_id": int(s["faaliyet_ID"]),
        "sezon_id":    int(s["sezon_ID"]),
        "sezon":       s.get("sezon", ""),
        "league_slug": s.get("url", ""),   # örn. "BSL-2025-2026"
        "league_name": s.get("faaliyet", ""),
    }


def get_teams(session, faaliyet_id):
    """Ligteki tüm takımları döndürür."""
    data = _api(session, "Team/get-teams-by-leauge", {"leaugeId": faaliyet_id})
    return data.get("data", [])


def get_team_matches(session, team_process_id, faaliyet_id, sezon_id):
    """Bir takımın bu sezon tüm maçlarını döndürür."""
    data = _api(
        session,
        "Team/get-team-detail-matches-by-season-and-league",
        {
            "teamProcessId": team_process_id,
            "leagueId": faaliyet_id,
            "seasonId": sezon_id,
        },
    )
    return data.get("data", {}).get("maclar", [])


def _parse_nuxt_data(html):
    """NUXT_DATA'dan maç header bilgisini (hakem, salon) parse eder."""
    m = re.search(r'NUXT_DATA__">(.*?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except json.JSONDecodeError:
        return None

    # match-header-{matchId} key'ini bul
    for item in data:
        if isinstance(item, dict):
            for key in item:
                if key.startswith("match-header-"):
                    ref_idx = item[key]
                    if isinstance(ref_idx, int) and ref_idx < len(data):
                        header_obj = data[ref_idx]
                        if isinstance(header_obj, dict) and "data" in header_obj:
                            detail_idx = header_obj["data"]
                            if isinstance(detail_idx, int) and detail_idx < len(data):
                                detail = data[detail_idx]
                                if isinstance(detail, dict):
                                    return _resolve_header(data, detail)
    return None


def _resolve_str(data, ref):
    """Verilen index referansını stringe çevirir."""
    if isinstance(ref, int):
        if ref < len(data):
            val = data[ref]
            if isinstance(val, str):
                return val
            if isinstance(val, int):
                return _resolve_str(data, val)
    if isinstance(ref, str):
        return ref
    return ""


def _resolve_score(data, ref):
    """Skor değerini çöz - sadece kısa nümerik string döndür."""
    val = _resolve_str(data, ref)
    if val and str(val).isdigit() and len(str(val)) <= 3:
        return val
    return ""


def _resolve_header(data, detail):
    """match-header dict'inden hakem/salon bilgisi çıkarır."""
    result = {
        "main_referee":       _resolve_str(data, detail.get("mainReferee")),
        "first_assistant":    _resolve_str(data, detail.get("firstAssistantReferee")),
        "second_assistant":   _resolve_str(data, detail.get("secondAssistantReferee")),
        "commissioner":       _resolve_str(data, detail.get("temsilciAdi")),
        "venue":              _resolve_str(data, detail.get("location")),
        "match_status_id":    detail.get("matchStatusId"),
        "home_score":         _resolve_score(data, detail.get("homeTeamScore")),
        "away_score":         _resolve_score(data, detail.get("awayTeamScore")),
    }
    return result


def get_match_detail(league_slug, match_id):
    """Maç detay sayfasından hakem ve salon bilgisini çeker."""
    url = f"{BASE_WEB}/ligler/{league_slug}/mac-detay/{match_id}"
    try:
        if USE_CURL_CFFI:
            resp = cf_requests.get(
                url,
                impersonate="chrome120",
                headers={"Referer": BASE_WEB + "/"},
                timeout=20,
            )
        else:
            web_session = requests.Session()
            web_session.headers.update(HEADERS_WEB)
            resp = web_session.get(url, timeout=20)
        resp.raise_for_status()
        return _parse_nuxt_data(resp.text)
    except Exception as e:
        logger.warning(f"Maç detay alınamadı ({match_id}): {e}")
        return None


def scrape_league(league_code, fetch_details=True):
    """
    Ana scrape fonksiyonu. Ligin tüm maçlarını ve hakem bilgilerini döndürür.

    Returns: list of dicts:
        {
          league, season, week,
          match_date, home_team, away_team,
          venue, score, status, tbf_match_id,
          referees: [
            {'name': str, 'role': '1'|'2'|'3'|'commissioner'}
          ]
        }
    """
    prefix = LEAGUE_PREFIXES.get(league_code)
    if not prefix:
        raise ValueError(f"Bilinmeyen lig kodu: {league_code}")

    session = requests.Session()
    session.headers.update(HEADERS_API)

    # 1. Güncel sezon
    season_info = get_current_season(session, prefix)
    faaliyet_id = season_info["faaliyet_id"]
    sezon_id    = season_info["sezon_id"]
    league_slug = season_info["league_slug"]
    season_name = season_info["sezon"]
    logger.info(f"[{league_code}] Sezon: {season_name} | faaliyetId={faaliyet_id} | slug={league_slug}")

    # 2. Takım listesi
    teams = get_teams(session, faaliyet_id)
    logger.info(f"[{league_code}] {len(teams)} takım bulundu.")

    if not teams:
        raise ValueError(f"[{league_code}] Takım listesi boş.")

    # 3. Maçları topla - ilk takımın maçları tüm ligin maçlarını kapsar
    # (deplasman/ev sahipliği her iki takım için de döndürülür)
    all_matches = {}
    for team in teams:
        team_id = int(team["teamProcessId"])
        try:
            matches = get_team_matches(session, team_id, faaliyet_id, sezon_id)
            for m in matches:
                mid = m.get("matchId")
                if mid and mid not in all_matches:
                    all_matches[mid] = m
        except Exception as e:
            logger.warning(f"[{league_code}] Takım {team_id} maçları alınamadı: {e}")

    logger.info(f"[{league_code}] Toplam {len(all_matches)} benzersiz maç.")

    # 4. Her maç için detay al (hakem + salon)
    result = []

    for i, (match_id, m) in enumerate(all_matches.items()):
        entry = {
            "league":       league_code,
            "season":       season_name,
            "week":         m.get("formattedWeek", ""),
            "home_team":    m.get("takimA", ""),
            "away_team":    m.get("takimB", ""),
            "match_date":   _parse_date(m.get("tarih")),
            "venue":        m.get("salon", ""),
            "score":        _format_score(m.get("skorA"), m.get("skorB")),
            "status":       "",
            "tbf_match_id": f"{league_code}_{match_id}",
            "referees":     [],
        }

        if fetch_details:
            detail = get_match_detail(league_slug, match_id)
            if detail:
                if detail.get("venue"):
                    entry["venue"] = detail["venue"]
                if detail.get("home_score") and detail.get("away_score"):
                    hs = str(detail["home_score"]).strip()
                    as_ = str(detail["away_score"]).strip()
                    if hs and as_ and hs != "0" and as_ != "0":
                        entry["score"] = f"{hs} - {as_}"
                refs = []
                if detail.get("main_referee"):
                    refs.append({"name": detail["main_referee"],    "role": "1"})
                if detail.get("first_assistant"):
                    refs.append({"name": detail["first_assistant"], "role": "2"})
                if detail.get("second_assistant"):
                    refs.append({"name": detail["second_assistant"],"role": "3"})
                if detail.get("commissioner"):
                    refs.append({"name": detail["commissioner"],    "role": "commissioner"})
                entry["referees"] = refs

            # Rate limiting
            if (i + 1) % 5 == 0:
                time.sleep(0.5)

        result.append(entry)

    return result


def _parse_date(date_str):
    """ISO 8601 tarihini timezone-aware datetime'a çevirir."""
    if not date_str:
        return None
    from datetime import datetime, timezone as tz
    import pytz
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            istanbul = pytz.timezone("Europe/Istanbul")
            dt = istanbul.localize(dt)
        return dt
    except (ValueError, AttributeError):
        return None


def _format_score(score_a, score_b):
    """Skor formatlar."""
    if score_a is not None and score_b is not None:
        sa, sb = str(score_a).strip(), str(score_b).strip()
        if sa and sb:
            return f"{sa} - {sb}"
    return ""
