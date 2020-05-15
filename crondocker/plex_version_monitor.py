import requests
import os
import json
from retry import retry


def send_message_to_slack(message, markdown=True):
    data = {"text": message, "markdown": True}

    _ = requests.post(
        "https://hooks.slack.com/services/" + os.environ.get('SLACK_SERVICE_PATH'),
        data=json.dumps(data),
        headers={'Content-Type': 'application/json'}
    )


def check_and_update_content(content, path):
    if not os.path.exists(path):
        open(path, 'w').write(content)
        return True
    else:
        last_recorded_content = open(path).read().strip()
        if content != last_recorded_content:
            os.remove(path)
            open(path, 'w').write(content)
            return True
        else:
            return False


@retry(RuntimeError, delay=20)
def get_plex_version():
    current_version = requests.get('https://plex.tv/api/downloads/1.json?channel=plexpass').json()
    return current_version['computer']['Linux']['version']


current_version = get_plex_version()
file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'current_plex_version.txt')
changed = check_and_update_content(current_version, file_path)
if changed:
    send_message_to_slack("New Plex version is available: ```" + current_version + "```")
