FROM muyajil/crondocker:latest

# Install python
RUN apt-get update && apt-get install -y python3 python3-pip borgbackup rsync

# Install python dependencies
RUN pip3 install retry requests pandas numpy gphotos-sync

# Add files to be run using crontab
COPY ./compute_storage_savings.py /compute_storage_savings.py
COPY ./plex_version_monitor.py /plex_version_monitor.py
COPY ./media_center_stats.py /media_center_stats.py
COPY ./transcode_library.py /transcode_library.py
COPY ./gphotos-sync.sh /gphotos-sync.sh
RUN chmod +x /gphotos-sync.sh