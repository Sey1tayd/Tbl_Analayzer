from django.shortcuts import render, redirect
from django.contrib import messages
from django.db.models import Q
from datetime import datetime
from .models import Match, Referee, MatchReferee, ScrapeLog, LEAGUE_CHOICES
from . import scraper as tbf_scraper


LEAGUES = [code for code, _ in LEAGUE_CHOICES]


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

    # Haftaya göre grupla
    matches_by_week = {}
    for match in qs:
        week = match.week or 'Tarihsiz'
        if week not in matches_by_week:
            matches_by_week[week] = []
        matches_by_week[week].append(match)

    # Her lig için maç sayısı
    league_counts = {code: Match.objects.filter(league=code).count() for code in LEAGUES}

    last_scrape = {code: ScrapeLog.objects.filter(league=code).first() for code in LEAGUES}

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
    }
    return render(request, 'tracker/index.html', context)


def _save_match_list(league_code, match_list):
    saved = 0
    for m in match_list:
        refs = m.pop('referees', [])
        match_id = m.get('tbf_match_id') or f"{league_code}_{m.get('home_team','')}_{m.get('away_team','')}"
        if not match_id.strip('_'):
            continue
        obj, _ = Match.objects.update_or_create(
            tbf_match_id=match_id,
            defaults={**m},
        )
        for ref_name in refs:
            if not ref_name:
                continue
            ref_obj, _ = Referee.objects.get_or_create(name=ref_name)
            MatchReferee.objects.get_or_create(match=obj, referee=ref_obj)
        saved += 1
    return saved


def scrape_league(request, league_code):
    if request.method != 'POST':
        return redirect('index')
    if league_code not in LEAGUES:
        messages.error(request, 'Geçersiz lig kodu.')
        return redirect('index')
    try:
        match_list = tbf_scraper.scrape_league(league_code)
        saved = _save_match_list(league_code, match_list)
        ScrapeLog.objects.create(league=league_code, success=True,
                                  matches_found=saved, message=f"{saved} maç güncellendi.")
        messages.success(request, f"{league_code}: {saved} maç başarıyla güncellendi.")
    except Exception as e:
        ScrapeLog.objects.create(league=league_code, success=False, message=str(e))
        messages.error(request, f"{league_code} verisi çekilemedi: {e}")
    return redirect(f"/?league={league_code}")


def scrape_all(request):
    if request.method != 'POST':
        return redirect('index')
    total, errors = 0, []
    for league_code in LEAGUES:
        try:
            match_list = tbf_scraper.scrape_league(league_code)
            saved = _save_match_list(league_code, match_list)
            total += saved
            ScrapeLog.objects.create(league=league_code, success=True,
                                      matches_found=saved, message=f"{saved} maç.")
        except Exception as e:
            errors.append(f"{league_code}: {e}")
            ScrapeLog.objects.create(league=league_code, success=False, message=str(e))
    if errors:
        messages.warning(request, f"{total} maç güncellendi. Hatalar: {'; '.join(errors)}")
    else:
        messages.success(request, f"Tüm ligler güncellendi. Toplam {total} maç.")
    return redirect('index')
