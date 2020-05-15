import os
from datetime import datetime
import argparse
import subprocess
import shutil
from pymediainfo import MediaInfo
from uuid import uuid4
import time
import socket
import requests
import json
from retry import retry


RADARR_API_ROOT = "http://localhost:7878/api"
RADARR_API_KEY = os.environ.get('RADARR_API_KEY')


def get_file_size_gb(path):
    num_bytes = os.path.getsize(path)
    return num_bytes / (2**30)


def get_absolute_paths(root_dir):
    for dirpath, _, filenames in os.walk(root_dir):
        for f in filenames:
            yield os.path.abspath(os.path.join(dirpath, f))


def is_video(file_path):
    fileInfo = MediaInfo.parse(file_path)
    for track in fileInfo.tracks:
        if track.track_type == "Video":
            return True
    return False


def is_info_file(file_path):
    return file_path.endswith(('jpg', 'nfo', 'transcodelog', 'istranscoded'))


def is_full_hd(file_path):
    fileInfo = MediaInfo.parse(file_path)
    for track in fileInfo.tracks:
        if track.track_type == "Video":
            if track.width > 1900:
                return True
    return False


def get_quality_tag(file_path):
    fileInfo = MediaInfo.parse(file_path)
    for track in fileInfo.tracks:
        if track.track_type == "Video":
            if track.width > 1900:
                return " - WEB-DL-1080p"
            else:
                return " - WEB-DL-720p"
    return ''


def get_tag_file_path(file_path, ending):
    if 'WEB-DL-' in file_path:
        return os.path.splitext(file_path)[0] + '.' + ending
    return os.path.splitext(file_path)[0] + get_quality_tag(file_path) + '.' + ending


def is_transcoded(file_path):
    return os.path.isfile(get_tag_file_path(file_path, 'istranscoded')) and \
        os.path.isfile(get_tag_file_path(file_path, 'mp4'))


def is_transcoding(file_path):
    transcodelog_path = get_tag_file_path(file_path, 'transcodelog')
    if os.path.isfile(transcodelog_path):
        last_change = os.path.getmtime(transcodelog_path)
        if time.time() - last_change > 36000:  # Check if file was modified in last 10 hours > detect program crashes
            return False
        else:
            return True
    else:
        return False


def get_relevant_file_paths(root_dir, ignore_movies):
    file_paths = get_absolute_paths(root_dir)
    if ignore_movies:
        file_paths = filter(lambda f: '/tv/' in f, file_paths)
    else:
        file_paths = filter(
            lambda f: '/movies/' in f or '/tv/' in f, file_paths)

    file_paths = filter(lambda f: 'partial' not in f, file_paths)

    return file_paths


def get_properties(file_path):
    parts = file_path.split('/')
    for idx, part in enumerate(parts):
        if part in ('tv', 'movies'):
            item_type = part
            folder_name = parts[idx+1]
            break
    item_name = parts[-1]
    return item_type, folder_name, item_name


@retry(subprocess.CalledProcessError, delay=60)
def transcode_single(file_path, root_dir):

    if datetime.now().hour < 16:
        num_cpus = 12
    else:
        num_cpus = 8

    new_file_path = os.path.splitext(
        file_path)[0] + get_quality_tag(file_path) + '.mp4'
    new_file_path = new_file_path.replace('tmp',root_dir)

    temp_file_name = os.path.basename(new_file_path)

    docker_command = ["docker", "run"]
    docker_command.extend(["--cpuset-cpus", ','.join(map(lambda x: str(x), range(num_cpus)))])
    docker_command.extend(["--cpus", str(num_cpus)])
    docker_command.extend(["--user", "1000:1000"])
    docker_command.extend(["--name", "transcode"])
    docker_command.extend(["-p", "5800:5800"])
    docker_command.extend(["-v", "{0}:/{0}".format(root_dir)])
    docker_command.extend(["-v", "/{0}:/{0}".format("tmp")])
    docker_command.extend(["--rm", "jlesage/handbrake:latest", "HandBrakeCLI"])
    docker_command.extend(["-i", file_path])
    docker_command.extend(["-o", "/tmp/{}".format(temp_file_name)])
    docker_command.extend(["-f", "av_mp4", "-e",
                           "x264", "-q", "25", "--audio-lang-list", "eng,ger", "--vfr", "-E", "copy:ac3,copy:aac,copy:dts,copy:dtshd",
                           "-Y", "1080", "-X", "1920", "--optimize"])

    transcode_log = open(os.path.splitext(new_file_path)
                         [0] + '.transcodelog', 'w')
    result = subprocess.run(docker_command, stderr=transcode_log)
    result.check_returncode()

    os.remove(file_path)

    shutil.move('/tmp/{}'.format(temp_file_name), new_file_path)

    with open(os.path.splitext(new_file_path)[0] + '.istranscoded', 'w'):
        pass

    return new_file_path


def is_command_completed(command_id):
    response = requests.get(
        "{}/command/{}?apikey={}".format(RADARR_API_ROOT, command_id, RADARR_API_KEY))
    command = json.loads(response.text)
    return command['state'] == 'completed'


def get_movie_filename(movie_id):
    response = requests.get(
        "{}/movie/{}?apikey={}".format(RADARR_API_ROOT, movie_id, RADARR_API_KEY))
    movie = json.loads(response.text)
    if 'movieFile' in movie:
        return movie['movieFile']['relativePath']
    else:
        return ''


def update_movie_radarr(old_file_name, new_file_name):
    response = requests.get(
        "{}/movie?apikey={}".format(RADARR_API_ROOT, RADARR_API_KEY))

    for movie in json.loads(response.text):
        if movie['downloaded']:
            if movie['movieFile']['relativePath'] == old_file_name:
                tries = 0
                while get_movie_filename(movie['id']) != new_file_name and tries < 5:
                    data = {"name": "RefreshMovie", "movieId": movie['id']}
                    response = requests.post(
                        "{}/command?apikey={}".format(RADARR_API_ROOT, RADARR_API_KEY),
                        data=json.dumps(data),
                        headers={'Content-Type': 'application/json'}
                    )

                    command = json.loads(response.text)

                    while not is_command_completed(command['id']):
                        time.sleep(10)
                    tries += 1
                return


def transcode(root_dir, max_hours, ignore_movies, timeout_mins, include_hd, log_dir):
    log_path = '{}/{}.log'.format(log_dir, socket.gethostname())
    if os.path.isfile(log_path):
        logfile = logfile = open(log_path, 'a')
    else:
        logfile = logfile = open(log_path, 'w')
        logfile.write('Time,Event,Type,Name,File,Size (GB)\n')
    start_time = datetime.now()

    file_paths = get_relevant_file_paths(root_dir, ignore_movies)

    for file_path in file_paths:
        transcode_start = datetime.now()
        item_type, folder_name, item_name = get_properties(file_path)

        try:
            if not is_info_file(file_path) and not is_transcoding(file_path) and not is_transcoded(file_path) and is_video(file_path):
                if include_hd or (not include_hd and is_full_hd(file_path)):
                    logfile.write('{},start,{},"{}","{}",{:.2f}\n'.format(
                        datetime.now().isoformat(' ', 'seconds'),
                        item_type,
                        folder_name,
                        item_name,
                        get_file_size_gb(file_path)))

                    logfile.flush()
                    new_file_path = transcode_single(file_path, root_dir)
                    logfile.write('{},end,{},"{}","{}",{:.2f}\n'.format(
                        datetime.now().isoformat(' ', 'seconds'),
                        item_type,
                        folder_name,
                        new_file_path.split('/')[-1],
                        get_file_size_gb(new_file_path)))

                    logfile.flush()

                    if item_type == 'movies' and socket.gethostname() == 'srv.ajil.ch':
                        update_movie_radarr(os.path.basename(file_path), os.path.basename(new_file_path))

                    elapsed_time = datetime.now() - transcode_start
                    print(
                        'Finished Transcoding!\n\tCurrent Time: {}\n\tFile: {}\n\tTranscoding Time: {}\n\tTaking a break...'.format(
                            datetime.now().isoformat(' ', 'seconds'), item_name, elapsed_time))

                    if max_hours >= 0 and (datetime.now() - start_time).seconds >= max_hours*3600:
                        break

                time.sleep(timeout_mins*60)
        except FileNotFoundError:
            continue

    logfile.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--root_dir', required=True, type=str)
    parser.add_argument('--max_hours', '-t', type=int, default=-1)
    parser.add_argument('--ignore_movies', action='store_true', default=False)
    parser.add_argument('--include_hd', action='store_true', default=False)
    parser.add_argument('--timeout_mins', type=int, default=5)
    parser.add_argument('--log_dir', type=str, required=True)

    args = parser.parse_args()

    transcode(args.root_dir, args.max_hours,
              args.ignore_movies, args.timeout_mins, args.include_hd, args.log_dir)
