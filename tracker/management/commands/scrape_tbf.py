"""
Kullanım:
    python manage.py scrape_tbf                      # Tüm ligler
    python manage.py scrape_tbf --league BSL         # Sadece BSL
    python manage.py scrape_tbf --league BSL --no-details  # Hakem detayı olmadan
    python manage.py scrape_tbf --league BSL --workers 4   # 4 paralel istek
"""
import time
import concurrent.futures
from django.core.management.base import BaseCommand
from tracker.models import Match, Referee, MatchReferee, ScrapeLog, LEAGUE_CHOICES
from tracker.scraper import (
    get_current_season, get_teams, get_team_matches,
    get_match_detail, _parse_date, _format_score, HEADERS_API,
)
import requests

LEAGUES = [code for code, _ in LEAGUE_CHOICES]


class Command(BaseCommand):
    help = 'TBF sitesinden maç ve hakem verilerini çeker'

    def add_arguments(self, parser):
        parser.add_argument('--league', type=str, default=None,
                            help='Lig kodu: BSL, KBSL, TBL, TKBL')
        parser.add_argument('--no-details', action='store_true',
                            help='Hakem detaylarını çekme (sadece maç listesi)')
        parser.add_argument('--workers', type=int, default=3,
                            help='Paralel istek sayısı (varsayılan: 3)')

    def handle(self, *args, **options):
        target = options['league']
        fetch_details = not options['no_details']
        workers = options['workers']
        leagues = [target] if target and target in LEAGUES else LEAGUES

        for league_code in leagues:
            self.stdout.write(f'[{league_code}] Veri çekiliyor...')
            start = time.time()
            try:
                saved = self._scrape_league(
                    league_code, fetch_details, workers
                )
                elapsed = time.time() - start
                ScrapeLog.objects.create(
                    league=league_code, success=True,
                    matches_found=saved,
                    message=f"{saved} maç güncellendi ({elapsed:.0f}s)."
                )
                self.stdout.write(self.style.SUCCESS(
                    f'  [{league_code}] {saved} maç kaydedildi ({elapsed:.0f}s).'
                ))
            except Exception as e:
                ScrapeLog.objects.create(
                    league=league_code, success=False, message=str(e)
                )
                self.stdout.write(self.style.ERROR(f'  [{league_code}] HATA: {e}'))

    def _scrape_league(self, league_code, fetch_details, workers):
        from tracker.scraper import LEAGUE_PREFIXES
        prefix = LEAGUE_PREFIXES.get(league_code)
        if not prefix:
            raise ValueError(f'Bilinmeyen lig: {league_code}')

        session = requests.Session()
        session.headers.update(HEADERS_API)

        # Sezon bilgisi
        season_info = get_current_season(session, prefix)
        faaliyet_id = season_info['faaliyet_id']
        sezon_id    = season_info['sezon_id']
        league_slug = season_info['league_slug']
        season_name = season_info['sezon']

        # Takım listesi
        teams = get_teams(session, faaliyet_id)
        self.stdout.write(f'  Sezon: {season_name} | {len(teams)} takim')
        if not teams:
            raise ValueError('Takım listesi boş')

        # Maç listesi (deduplicate)
        all_matches = {}
        for team in teams:
            tid = int(team['teamProcessId'])
            try:
                for m in get_team_matches(session, tid, faaliyet_id, sezon_id):
                    mid = m.get('matchId')
                    if mid and mid not in all_matches:
                        all_matches[mid] = m
            except Exception as e:
                self.stdout.write(f'  Uyari: Takim {tid} maclar alinmadi: {str(e)[:50]}')

        self.stdout.write(f'  {len(all_matches)} mac bulundu.')

        if not all_matches:
            return 0

        # Maç detaylarını paralel çek
        details = {}
        if fetch_details:
            self.stdout.write(f'  Hakem detaylari cekiliyor ({workers} paralel)...')

            def fetch_detail(mid):
                return mid, get_match_detail(league_slug, mid)

            with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {
                    executor.submit(fetch_detail, mid): mid
                    for mid in all_matches
                }
                done = 0
                for future in concurrent.futures.as_completed(futures):
                    try:
                        mid, detail = future.result()
                        if detail:
                            details[mid] = detail
                    except Exception:
                        pass
                    done += 1
                    if done % 20 == 0:
                        self.stdout.write(f'  {done}/{len(all_matches)} detay alindi...')

        # Veritabanına kaydet
        saved = 0
        for mid, m in all_matches.items():
            detail = details.get(mid, {})
            venue = (detail.get('venue') or m.get('salon') or '')
            hs = str(detail.get('home_score') or m.get('skorA') or '').strip()
            as_ = str(detail.get('away_score') or m.get('skorB') or '').strip()
            score = f'{hs} - {as_}' if hs and as_ else ''

            obj, _ = Match.objects.update_or_create(
                tbf_match_id=f'{league_code}_{int(mid)}',
                defaults=dict(
                    league=league_code,
                    season=season_name,
                    week=(m.get('formattedWeek') or ''),
                    match_date=_parse_date(m.get('tarih')),
                    home_team=(m.get('takimA') or ''),
                    away_team=(m.get('takimB') or ''),
                    venue=venue,
                    score=score,
                )
            )

            roles = [
                ('main_referee',    '1'),
                ('first_assistant', '2'),
                ('second_assistant','3'),
                ('commissioner',    'commissioner'),
            ]
            for field, role in roles:
                name = (detail.get(field) or '').strip()
                if name:
                    ref_obj, _ = Referee.objects.get_or_create(name=name)
                    MatchReferee.objects.get_or_create(
                        match=obj, referee=ref_obj,
                        defaults={'role': role}
                    )
            saved += 1

        return saved
