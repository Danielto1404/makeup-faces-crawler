import argparse
import os.path
from multiprocessing import Pool
from threading import Thread

from dotenv import load_dotenv
from progress.bar import Bar

from crawler import Crawler
from users import UsersCrawler


def run_hashtags_search(hashtags, crawler):
    threads = []
    for hashtag in hashtags:
        if hashtag.startswith('#'):
            hashtag = hashtag[1:]

        thread = Thread(target=crawler.process,
                        args=(hashtag,))
        thread.start()
        threads += [thread]

    for thread in threads:
        thread.join()


def run_users_search(users, crawler):
    threads = []
    for user in users:
        thread = Thread(target=crawler.process,
                        args=(user,))
        thread.start()
        threads += [thread]

    for thread in threads:
        thread.join()


if __name__ == '__main__':
    load_dotenv()
    parser = argparse.ArgumentParser()
    parser.add_argument('--hashtags', type=str, required=False,
                        help='list of hashtags separated by space, e.g. \"#makeuplook #yellowmakeup\"')
    parser.add_argument('-e', '--extract', action='store_true',
                        help='skip image downloading and run extractor for hashtags')
    parser.add_argument('--users', type=str, required=False,
                        help="download all user photos, e.g. \"tomholland2013 zendaya\"")
    args = parser.parse_args()

    INSTAGRAM_LOGIN = os.getenv('INSTAGRAM_LOGIN')
    INSTAGRAM_PASSWORD = os.getenv('INSTAGRAM_PASSWORD')
    IMAGES_NUMBER = os.getenv('IMAGES_NUMBER')
    IMAGES_NUMBER = int(IMAGES_NUMBER) if IMAGES_NUMBER else 0
    DELAY_BEFORE = eval(os.getenv('DELAY_BEFORE'))
    DELAY_ERROR = eval(os.getenv('DELAY_ERROR'))
    UNIQ_TYPE = int(os.getenv('UNIQ_TYPE'))
    PROCESSES = int(os.getenv('PROCESSES')) if os.getenv('PROCESSES') else os.cpu_count() - 1
    THREADS = int(os.getenv('THREADS')) if os.getenv('THREADS') else os.cpu_count() - 1

    progress_bar = Bar(max=int(IMAGES_NUMBER) if IMAGES_NUMBER else 1)

    with Pool(processes=PROCESSES) as process_pool:

        print(f"Start downloading on {PROCESSES} processes")

        if args.users:
            crawler = UsersCrawler(INSTAGRAM_LOGIN, INSTAGRAM_PASSWORD, process_pool, PROCESSES,
                                   THREADS, DELAY_BEFORE, DELAY_ERROR, UNIQ_TYPE, progress_bar, args.extract,
                                   IMAGES_NUMBER)
            crawler.listener.start()
            run_users_search(args.users.split(), crawler)
        elif args.hashtags:
            crawler = Crawler(INSTAGRAM_LOGIN, INSTAGRAM_PASSWORD, process_pool, PROCESSES, THREADS, DELAY_BEFORE,
                              DELAY_ERROR, UNIQ_TYPE, progress_bar, args.extract, IMAGES_NUMBER)
            crawler.listener.start()
            run_hashtags_search(args.hashtags.split(), crawler)
        else:
            print("Please provide either usernames or hashtags")
            exit()

    progress_bar.finish()
    if crawler.stage == 1:
        print('Good:', crawler.good_extract)
