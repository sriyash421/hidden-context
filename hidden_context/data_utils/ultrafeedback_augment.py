import argparse
import random

import torch
from datasets import load_dataset, Dataset
import numpy as np
import os

import sys, ipdb, traceback


def info(type, value, tb):
    traceback.print_exception(type, value, tb)
    ipdb.pm()


sys.excepthook = info


def random_argmax(values):
    """ a random tie-breaking argmax """
    return np.argmax(np.random.random(values.shape) * (values == values.max()))


def random_greater_than_zero(values):
    return (np.random.randn(values.shape[0]) * (values == 0) > 0.0) | (values > 0.0)


def array_to_type(arr):
    return str(int(np.dot(arr, np.array([8, 4, 2, 1]))))


def get_user_type(chosen_ratings, rejected_ratings, augment_type, users):
    keys = ['helpfulness', 'honesty', 'instruction_following', 'truthfulness']
    chosen_rating_values = list()
    rejected_rating_values = list()
    for key in keys:
        chosen_rating_values.append(chosen_ratings[key])
        rejected_rating_values.append(rejected_ratings[key])
    chosen_values = np.asarray(chosen_rating_values)
    rejected_values = np.asarray(rejected_rating_values)
    has_equal = True in list(chosen_values == rejected_values)
    if augment_type == 'single':
        data_subsets = ['8', '4', '2', '1']
        reversed_labels = list(random_greater_than_zero(rejected_values - chosen_values))
        return data_subsets, reversed_labels, has_equal
    elif augment_type == 'set':
        data_subsets = ['1', '2', '3', '4', '5', '6', '7', '8', '9', '10', '11', '12', '13', '14', '15']
        preferences = np.array([users[user] for user in data_subsets])
        reversed_labels = list(random_greater_than_zero(np.dot(preferences, rejected_values - chosen_values)))
        return data_subsets, reversed_labels, has_equal
    elif augment_type == 'pos_neg':
        user_orig = np.ones(4, dtype=int) * (random_greater_than_zero(chosen_values - rejected_values))
        user_rev = 1 - user_orig
        data_subsets = [array_to_type(user_orig), array_to_type(user_rev)]
        reversed_labels = [False, True]
        return data_subsets, reversed_labels, has_equal
    else:
        raise ValueError('Invalid augment_type')


def inner_join(original, binarized, augment_type, users, two_two_only=False, filter_equal=False):
    agreed_counter = 0
    controversial_counter = 0
    three_one_counter = 0
    two_two_counter = 0
    one_three_counter = 0
    keys = ['helpfulness', 'honesty', 'instruction_following', 'truthfulness']
    reversed_counter = {key: 0 for key in users.keys()}
    dumb_baseline = {key: 0 for key in users.keys()}
    orig_idx = 0
    out_idx = 0
    dataset_dict = {
        'Index': list(),
        'prompt': list(),
        'chosen': list(),
        'rejected': list(),
        'data_subset': list(),
        'controversial': list(),
        'reversed': list(),
    }
    for bin_idx in range(len(binarized)):
        while binarized[bin_idx]['prompt'] != original[orig_idx]['instruction']:
            orig_idx += 1
        prompt = binarized[bin_idx]['prompt']
        chosen = binarized[bin_idx]['chosen'][1]['content']
        rejected = binarized[bin_idx]['rejected'][1]['content']
        if chosen == '' or rejected == '':
            continue
        chosen_ratings = dict()
        rejected_ratings = dict()
        flag = True
        for c in original[orig_idx]['completions']:
            if c['response'] == chosen:
                for key in keys:
                    r = c['annotations'][key]['Rating']
                    if r == 'N/A':
                        flag = False
                        continue
                    chosen_ratings[key] = int(r)
            elif c['response'] == rejected:
                for key in keys:
                    r = c['annotations'][key]['Rating']
                    if r == 'N/A':
                        flag = False
                        continue
                    rejected_ratings[key] = int(r)
            else:
                continue
        if not flag or len(chosen_ratings) != 4 or len(rejected_ratings) != 4:
            continue

        data_subsets, reversed_labels, has_equal = get_user_type(chosen_ratings, rejected_ratings, augment_type, users)
        if has_equal and filter_equal:
            continue
        if two_two_only:
            if reversed_labels.count(True) == 2:
                two_two_counter += 1
            elif reversed_labels.count(True) == 3:
                one_three_counter += 1
                continue
            elif reversed_labels.count(True) == 1:
                three_one_counter += 1
                continue
            else:
                agreed_counter += 1
                continue
        for idx, data_subset in enumerate(data_subsets):
            if True in reversed_labels:
                controversial_counter += 1
            if reversed_labels[idx]:
                reversed_counter[data_subset] += 1
                dumb_baseline[data_subset] += reversed_labels.count(True)
            else:
                dumb_baseline[data_subset] += reversed_labels.count(False)
            dataset_dict['Index'].append(out_idx)
            dataset_dict['prompt'].append(prompt)
            if not reversed_labels[idx]:
                dataset_dict['chosen'].append('Human: ' + prompt + '\n\nAssistant: ' + chosen)
                dataset_dict['rejected'].append('Human: ' + prompt + '\n\nAssistant: ' + rejected)
            else:
                dataset_dict['chosen'].append('Human: ' + prompt + '\n\nAssistant: ' + rejected)
                dataset_dict['rejected'].append('Human: ' + prompt + '\n\nAssistant: ' + chosen)
            dataset_dict['data_subset'].append(data_subset)
            dataset_dict['controversial'].append(True in reversed_labels)
            dataset_dict['reversed'].append(reversed_labels[idx])
            out_idx += 1
    print(agreed_counter, three_one_counter, two_two_counter, one_three_counter)
    print(out_idx, controversial_counter)
    print("Reversed counter:", reversed_counter)
    print("Dumb baseline:", dumb_baseline)
    return Dataset.from_dict(dataset_dict)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--seed', type=int, default=42, help='Random seed')
    parser.add_argument('-a', '--augment_type', type=str, default=None, help='How to augment data')
    args = parser.parse_args()
    seed = args.seed
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    sixteen = {
        '0': (0, 0, 0, 0),
        '1': (0, 0, 0, 1),
        '2': (0, 0, 1, 0),
        '3': (0, 0, 1, 1),
        '4': (0, 1, 0, 0),
        '5': (0, 1, 0, 1),
        '6': (0, 1, 1, 0),
        '7': (0, 1, 1, 1),
        '8': (1, 0, 0, 0),
        '9': (1, 0, 0, 1),
        '10': (1, 0, 1, 0),
        '11': (1, 0, 1, 1),
        '12': (1, 1, 0, 0),
        '13': (1, 1, 0, 1),
        '14': (1, 1, 1, 0),
        '15': (1, 1, 1, 1),
    }
    if args.augment_type == 'single':
        user_types = {
            '8': (1, 0, 0, 0),
            '4': (0, 1, 0, 0),
            '2': (0, 0, 1, 0),
            '1': (0, 0, 0, 1),
        }
    elif args.augment_type == 'set':
        user_types = sixteen.copy()
        user_types.pop('0')
    elif args.augment_type == 'pos_neg':
        user_types = sixteen
    else:
        raise ValueError('Invalid augment_type')

    ultra_feedback = load_dataset('openbmb/UltraFeedback')
    binarized_cleaned = load_dataset('argilla/ultrafeedback-binarized-preferences-cleaned')
    length = len(binarized_cleaned['train'])
    print(length)
    test_ids = list(np.random.choice(length, int(length * 0.1), replace=False))
    train_split = binarized_cleaned['train'].filter(lambda example, idx: idx not in test_ids, with_indices=True)
    test_split = binarized_cleaned['train'].filter(lambda example, idx: idx in test_ids, with_indices=True)
    print(len(train_split), len(test_split))
    print("start processing train split")
    joined_dataset_train = inner_join(ultra_feedback['train'], train_split, args.augment_type, user_types,
                                      two_two_only=True, filter_equal=True)
    print("start processing test split")
    joined_dataset_test = inner_join(ultra_feedback['train'], test_split, args.augment_type, user_types,
                                     two_two_only=True, filter_equal=True)

    output_dir = os.path.join('data', 'UltraFeedback_{}_finegrained_filtered'.format(args.augment_type))
    for user_type in user_types.keys():
        train_subset = joined_dataset_train.filter(lambda x: x['data_subset'] == user_type)
        test_subset = joined_dataset_test.filter(lambda x: x['data_subset'] == user_type)
        print(user_types[user_type], len(train_subset), len(test_subset))
        train_subset.to_json(os.path.join(output_dir, user_type, 'train.jsonl'))
        test_subset.to_json(os.path.join(output_dir, user_type, 'test.jsonl'))

# python -m hidden_context.data_utils.ultrafeedback_augment -a single

# 60917
# 243332 122776
# {'8': 9163, '4': 10459, '2': 8274, '1': 14910}
# {'8': 192810, '4': 194090, '2': 195842, '1': 187890}
