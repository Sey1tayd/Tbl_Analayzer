import threading
import logging
from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q
from datetime import datetime
from .models import Match, Referee, MatchReferee, ScrapeLog, LEAGUE_CHOICES
from . import scraper as tbf_scraper

logger = logging.getLogger(__name__)
LEAGUES = [code for code, _ in LEAGUE_CHOICES]

# Hangi liglerin şu an scrape edildiğini takip et
_scraping_status: dict[str, bool] = {}
_status_lock = threading.Lock()


def _save_match_list(league_code, match_list):
    saved = 0
    for m in match_list:
        refs = m.pop('referees', [])
        match_id = m.get('tbf_match_id') or \
            f"{league_code}_{m.get('home_team','')}_{m.get('away_team','')}"
        if not match_id.strip('_'):
            continue
        obj, _ = Match.objects.update_or_create(
            tbf_match_id=match_id,
            defaults={**m},
        )
        # refs: [{"name": str, "role": "1"|"2"|"3"|"commissioner"}, ...]
        for ref in refs:
            if isinstance(ref, dict):
                ref_name = (ref.get('name') or '').strip()
                ref_role = ref.get('role', '1')
            else:
                ref_name = str(ref).strip()
                ref_role = '1'
            if not ref_name:
                continue
            ref_obj, _ = Referee.objects.get_or_create(name=ref_name)
            MatchReferee.objects.update_or_create(
                match=obj, referee=ref_obj,
                defaults={'role': ref_role},
            )
        saved += 1
    return saved


def _scrape_league_bg(league_code):
    """Arka planda tek bir ligi günceller."""
    with _status_lock:
        _scraping_status[league_code] = True
    try:
        match_list = tbf_scraper.scrape_league(league_code)
        saved = _save_match_list(league_code, match_list)
        ScrapeLog.objects.create(
            league=league_code, success=True,
            matches_found=saved, message=f"{saved} mac guncellendi."
        )
        logger.info("[View] %s: %d mac kaydedildi", league_code, saved)
    except Exception as exc:
        logger.error("[View] %s hatasi: %s", league_code, exc)
        try:
            ScrapeLog.objects.create(league=league_code, success=False, message=str(exc))
        except Exception:
            pass
    finally:
        with _status_lock:
            _scraping_status[league_code] = False


def _scrape_all_bg():
    """Arka planda tüm ligleri günceller."""
    for league_code in LEAGUES:
        _scrape_league_bg(league_code)


def index(request):
    active_league = request.GET.get('league', 'BSL')
    if active_league not in LEAGUES:
        active_league = 'BSL'

    search = request.GET.get('search', '').strip()
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')

    qs = Match.objects.filter(league=active_league).prefetch_related(
        'matchreferee_set__referee'
    )

    if search:
        qs = qs.filter(
            Q(home_team__icontains=search) |
            Q(away_team__icontains=search) |
            Q(referees__name__icontains=search)
        ).distinct()

    if date_from:
        try:
            qs = qs.filter(match_date__date__gte=datetime.strptime(date_from, '%Y-%m-%d').date())
        except ValueError:
            pass

    if date_to:
        try:
            qs = qs.filter(match_date__date__lte=datetime.strptime(date_to, '%Y-%m-%d').date())
        except ValueError:
            pass

    matches_by_week = {}
    for match in qs:
        week = match.week or 'Tarihsiz'
        if week not in matches_by_week:
            matches_by_week[week] = []
        matches_by_week[week].append(match)

    league_counts = {code: Match.objects.filter(league=code).count() for code in LEAGUES}
    last_scrape = {code: ScrapeLog.objects.filter(league=code).first() for code in LEAGUES}

    with _status_lock:
        scraping_now = dict(_scraping_status)

    context = {
        'leagues': LEAGUE_CHOICES,
        'active_league': active_league,
        'matches_by_week': matches_by_week,
        'total_matches': qs.count(),
        'league_counts': league_counts,
        'last_scrape': last_scrape,
        'search': search,
        'date_from': date_from,
        'date_to': date_to,
        'scraping_now': scraping_now,
        'any_scraping': any(scraping_now.values()),
    }
    return render(request, 'tracker/index.html', context)


def scrape_league(request, league_code):
    if request.method != 'POST':
        return redirect('index')
    if league_code not in LEAGUES:
        messages.error(request, 'Gecersiz lig kodu.')
        return redirect('index')

    with _status_lock:
        already = _scraping_status.get(league_code, False)

    if already:
        messages.warning(request, f"{league_code} zaten guncelleniyor, lutfen bekleyin.")
    else:
        t = threading.Thread(target=_scrape_league_bg, args=(league_code,), daemon=True)
        t.start()
        messages.success(request, f"{league_code} guncellemesi baslatildi. Veriler birkaç dakika icinde hazir olacak.")

    return redirect(f"/?league={league_code}")


def scrape_all(request):
    if request.method != 'POST':
        return redirect('index')

    with _status_lock:
        already = any(_scraping_status.values())

    if already:
        messages.warning(request, "Guncelleme zaten devam ediyor, lutfen bekleyin.")
    else:
        t = threading.Thread(target=_scrape_all_bg, daemon=True)
        t.start()
        messages.success(request, "Tum ligler icin guncelleme baslatildi. Veriler birkaç dakika icinde hazir olacak.")

    return redirect('index')
