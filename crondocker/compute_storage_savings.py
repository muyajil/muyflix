import argparse
import pandas as pd
import numpy as np
import os


def get_log_file_names(root_dir):
    filenames = os.listdir(root_dir)
    return filter(lambda x: x.endswith('.log'), filenames)


def extract_common_name(filename):
    if filename.endswith('.mp4'):
        if '720p' in filename:
            return filename[:-18]
        else:
            return filename[:-19]
    else:
        return os.path.splitext(filename)[0]


def compute_storage_savings_single(logfile):
    df = pd.read_csv(logfile)
    df['filename'] = df['File'].apply(extract_common_name)
    df['Time'] = pd.to_datetime(df['Time'])
    df = df.merge(right=df, on='filename')
    df = df[['filename', 'Event_x', 'Event_y', 'Size (GB)_x', 'Size (GB)_y', 'Time_x', 'Time_y']]
    df = df[(df['Event_x'] == 'start') & (df['Event_y'] == 'end')]
    df = df.drop_duplicates('filename', keep='last')
    df['savings'] = df['Size (GB)_x'] - df['Size (GB)_y']
    df['savings_ratio'] = df['savings'] / df['Size (GB)_x']
    df['time'] = (df['Time_x'] - df['Time_y']).apply(lambda x: x.total_seconds()/3600)
    df['savings_per_hour'] = df['savings'] / df['time']
    return list(df['savings']), list(df['savings_ratio']), list(df['savings_per_hour'])


def compute_storage_savings(root_dir):
    all_savings = []
    all_savings_ratios = []
    all_savings_per_hour = []
    filenames = get_log_file_names(root_dir)
    for filename in filenames:
        savings, savings_ratios, savings_per_hour = compute_storage_savings_single(os.path.join(root_dir, filename))
        all_savings.extend(savings)
        all_savings_ratios.extend(savings_ratios)
        all_savings_per_hour.extend(savings_per_hour)

    return np.sum(all_savings)/(2**10), np.mean(all_savings_ratios), -np.mean(all_savings_per_hour)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--log_dir', type=str, default='/home/srv-user/logs/transcode/')

    args = parser.parse_args()

    savings, savings_ratio, savings_per_hour = compute_storage_savings(args.log_dir)

    print('Total Storage Saved: {:.2f} TB'.format(savings))
    print('Average Savings per Item: {:.2f}%'.format(100*savings_ratio))
    print('Average GB Savings per Hour: {:.2f} GB/h'.format(savings_per_hour))
