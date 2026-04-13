import logging
import os
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

# Kaç saatte bir güncelleme yapılacak (varsayılan: 6)
SCRAPE_INTERVAL_HOURS = int(os.environ.get('SCRAPE_INTERVAL_HOURS', 6))


def run_full_scrape():
    """Tüm ligleri veritabanına çeker. Scheduler tarafından çağrılır."""
    # Import burada — scheduler thread'inde Django tamamen hazır olmalı
    from tracker.models import Match, Referee, MatchReferee, ScrapeLog, LEAGUE_CHOICES
    from tracker import scraper as tbf_scraper

    leagues = [code for code, _ in LEAGUE_CHOICES]
    logger.info("[Scheduler] Otomatik guncelleme basliyor — %d lig", len(leagues))

    for league_code in leagues:
        try:
            match_list = tbf_scraper.scrape_league(league_code)
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
                for ref_name in refs:
                    if not ref_name:
                        continue
                    ref_obj, _ = Referee.objects.get_or_create(name=ref_name)
                    MatchReferee.objects.get_or_create(match=obj, referee=ref_obj)
                saved += 1

            ScrapeLog.objects.create(
                league=league_code, success=True,
                matches_found=saved, message=f"{saved} mac guncellendi (otomatik)."
            )
            logger.info("[Scheduler] %s: %d mac kaydedildi", league_code, saved)

        except Exception as exc:
            logger.error("[Scheduler] %s hatasi: %s", league_code, exc)
            try:
                ScrapeLog.objects.create(
                    league=league_code, success=False, message=str(exc)
                )
            except Exception:
                pass

    logger.info("[Scheduler] Otomatik guncelleme tamamlandi.")


def start():
    """Arka plan scheduler'ını başlatır. apps.py ready()'den çağrılır."""
    scheduler = BackgroundScheduler(timezone='Europe/Istanbul')

    scheduler.add_job(
        run_full_scrape,
        trigger=IntervalTrigger(hours=SCRAPE_INTERVAL_HOURS),
        id='tbf_full_scrape',
        name='TBF Tam Guncelleme',
        replace_existing=True,
        # Uygulama ayağa kalkar kalkmaz ilk çekimi hemen yap
        next_run_time=None,  # apps.py'de ilk çalıştırma ayrıca yapılacak
    )

    scheduler.start()
    logger.info(
        "[Scheduler] Baslatildi — her %d saatte bir guncelleme yapilacak.",
        SCRAPE_INTERVAL_HOURS,
    )
    return scheduler
