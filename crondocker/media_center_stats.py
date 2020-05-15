import os
import requests
import json
import argparse
import shutil
from compute_storage_savings import compute_storage_savings


def is_transcoded(file_name):
    file_transcoded = file_name.rpartition('.')[0] + '.istranscoded'
    return os.path.isfile(file_transcoded)


def get_video_file_names(media_folder, category='movies', print_no_video_folders=False):
    VIDEO = ['mp4', 'mkv', 'wmv', 'avi', 'm2ts', 'ts', 'm4v']
    matches = []
    for root, _, filenames in os.walk(media_folder + '/' + category):
        movie_files = [fn for fn in filenames if fn.lower().endswith(tuple(VIDEO))]
        if len(movie_files) < 1 and print_no_video_folders:
            print(filenames)
            print(movie_files)
            print('\n')
        for filename in movie_files:
            matches.append(os.path.join(root, filename))
    return matches


def get_transcoding_data(base_path, suffix):
    all_items = get_video_file_names(base_path, suffix)
    transcoded_items = list(filter(is_transcoded, all_items))
    return len(all_items), len(transcoded_items)


def get_hdd_data(path):
    total, used, _ = shutil.disk_usage(path)

    return round(total/(2**40), 1), round(used/(2**40), 1)


def get_movie_download_data():
    response = requests.get(
        "http://localhost:7878/api/movie?apikey=" + os.environ.get('RADARR_API_KEY'),
    )

    movies = json.loads(response.text)
    total_movies = len(movies)
    downloaded_movies = len(list(filter(lambda x: x['downloaded'], movies)))

    return total_movies, downloaded_movies


def get_tv_download_data():
    response = requests.get(
        "http://localhost:8989/api/series?apikey=" + os.environ.get('SONARR_API_KEY')
    )

    total_episodes = 0
    downloaded_episodes = 0

    series = json.loads(response.text)
    total_series = len(series)
    completed_series = 0

    for serie in series:
        complete = True
        for season in serie['seasons']:
            if not season['monitored']:
                if season['statistics']['episodeFileCount'] == 0:
                    continue
            total_episodes += season['statistics']['totalEpisodeCount']
            downloaded_episodes += season['statistics']['episodeFileCount']
            complete = int(season['statistics']['percentOfEpisodes']) == 100 and complete
        if complete:
            completed_series += 1

    return (total_episodes, downloaded_episodes), (total_series, completed_series)


def create_progress_bar(total, progress):
    progress_bar_width = 15
    progress_percent = 100.0 * progress / total
    progress_bar = "["
    progress_bar += "=" * int((progress_percent / (100 / progress_bar_width)) - 1)
    progress_bar += ">"
    progress_bar += " " * min((progress_bar_width - int(progress_percent/(100 / progress_bar_width))), progress_bar_width - 1)
    progress_bar += "] "
    progress_bar += "({}/{})".format(progress, total).ljust(14)
    progress_bar += "{:.2f}%".format(progress_percent).rjust(6)
    progress_bar += "\n"

    return progress_bar


def create_info_block(title, data, total_width):
    output_string = ''
    output_string += "-"*total_width + '\n'
    output_string += "{}:\n".format(title)
    output_string += "-"*total_width + '\n'
    for name, datapoint in data:
        output_string += "{}:\n".format(name) + create_progress_bar(*datapoint)
    output_string += '\n'

    return output_string


def generate_media_center_stats(notify_slack):
    base_path = '/home/srv-user/media/'
    log_base_path = '/home/srv-user/logs/transcode/'

    output_string = ''
    total_width = 39

    movie_transcoding_data = get_transcoding_data(base_path, 'movies')
    tv_transcoding_data = get_transcoding_data(base_path, 'tv')

    output_string += create_info_block(
        'Transcoding Status',
        [('Movies', movie_transcoding_data), ('TV', tv_transcoding_data)],
        total_width)

    savings, savings_ratio, savings_per_hour = compute_storage_savings(log_base_path)

    output_string += 'Total Storage Saved: {:.2f} TB\n'.format(savings)
    output_string += 'Average Savings per Item: {:.2f}%\n'.format(100*savings_ratio)
    #output_string += 'Average GB Savings per Hour: {:.2f} GB/h\n'.format(savings_per_hour)

    movie_download_data = get_movie_download_data()
    episode_data, series_data = get_tv_download_data()

    output_string += create_info_block(
        'Download Status',
        [('Movies', movie_download_data), ('Episodes', episode_data), ('Series', series_data)],
        total_width)

    home_hdd_data = get_hdd_data("/home")
    root_hdd_data = get_hdd_data("/")
    backup_hdd_data = get_hdd_data("/mnt/nas-backup/")

    output_string += create_info_block(
        'HDD Status',
        [('/home', home_hdd_data), ('/', root_hdd_data), ('/mnt/nas-backup', backup_hdd_data)],
        total_width)

    print(output_string)

    if notify_slack:
        data = {
            "text": "```" + output_string + "```",
            "mrkdown": True}

        response = requests.post(
            "https://hooks.slack.com/services/" + os.environ.get('SLACK_SERVICE_PATH'),
            data=json.dumps(data),
            headers={'Content-Type': 'application/json'}
        )

        if response.status_code != 200:
            raise ValueError(
                'Request to slack returned an error %s, the response is:\n%s'
                % (response.status_code, response.text)
            )


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--notify_slack', action='store_true', default=False)
    args = parser.parse_args()
    generate_media_center_stats(args.notify_slack)
