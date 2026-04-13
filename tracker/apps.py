import os
import sys
import logging
from django.apps import AppConfig

logger = logging.getLogger(__name__)

_scheduler_started = False


class TrackerConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'tracker'

    def ready(self):
        global _scheduler_started
        if _scheduler_started:
            return

        # Test, migrate, collectstatic gibi komutlarda scheduler başlatma
        skip_cmds = ('test', 'collectstatic', 'migrate', 'makemigrations',
                     'shell', 'dbshell', 'check', 'showmigrations')
        if any(cmd in sys.argv for cmd in skip_cmds):
            return

        # Django dev server: RUN_MAIN=true olan child process'te çalış
        # Gunicorn --preload: RUN_MAIN yok, master process'te çalış
        run_main = os.environ.get('RUN_MAIN')
        is_dev_server = 'runserver' in sys.argv
        if is_dev_server and run_main != 'true':
            return  # dev server'da sadece child process'te çalış

        _scheduler_started = True

        try:
            from tracker import scheduler as tbf_scheduler
            import threading

            # Periyodik scheduler başlat
            tbf_scheduler.start()

            # Uygulama açılışında bir kez hemen çek
            t = threading.Thread(target=tbf_scheduler.run_full_scrape, daemon=True)
            t.start()
            logger.info("[Scheduler] Ilk guncelleme arkaplanada baslatildi.")

        except Exception as exc:
            logger.error("[Scheduler] Baslatma hatasi: %s", exc)
