gphotos-sync --omit-album-date --logfile /logs/gphotos-sync/last_run_debug.log --log-level info --db-path /gphotos-sync /media/photos/ > /logs/gphotos-sync/$(date "+%Y-%m-%d_%H:%M:%S").log 2>&1
