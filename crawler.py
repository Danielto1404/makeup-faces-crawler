from multiprocessing import Pool
from multiprocessing.pool import ThreadPool
from random import randint
import pynput
from instagram_private_api import Client, ClientCookieExpiredError, ClientLoginRequiredError
import ssl
import json
import codecs
import os.path
import requests
import re
from progress.bar import Bar
from typing import Optional, Union, List, Tuple
import extractors
from PIL import Image
from time import sleep


class Crawler:
    base_path = 'data/'
    full_images_path = '/full/'
    palette_images_path = '/palette/'
    left_eye_images_path = '/left_eye/'
    right_eye_images_path = '/right_eye/'
    left_right_eye_images_path = '/left_right_eyes/'
    left_eyelid_images_path = '/left_eyelid/'
    right_eyelid_images_path = '/right_eyelid/'
    left_right_eyelids_images_path = '/left_right_eyelids/'
    teeth_images_path = '/teeth/'
    mouth_images_path = '/mouth/'
    lips_images_path = '/lips/'
    eyelids_lips_images_path = '/eyelids_lips/'
    folders = [left_eye_images_path,
               right_eye_images_path,
               left_right_eye_images_path,
               left_eyelid_images_path,
               right_eyelid_images_path,
               left_right_eyelids_images_path,
               teeth_images_path,
               mouth_images_path,
               lips_images_path,
               eyelids_lips_images_path,
               palette_images_path,
               full_images_path]

    def __init__(self, login: str, password: str, process_pool: Pool, processes: int,
                 threads: int, delay_before: tuple, delay_error: tuple, uniq_type: int, progress_bar: Bar,
                 extractor_stage: int = False, images_number: int = None) -> None:
        self.listener = pynput.keyboard.Listener(on_press=self.on_press)
        ssl._create_default_https_context = ssl._create_unverified_context
        device_id = None

        try:
            os.makedirs('sessions', exist_ok=True)
            session_file = 'sessions/' + login + '.dat'
            if not os.path.isfile(session_file):
                self.api = Client(login, password, on_login=lambda x: self.on_login(x, session_file))
            else:
                with open(session_file) as file_data:
                    cached_settings = json.load(file_data, object_hook=Crawler.from_json)
                device_id = cached_settings.get('device_id')
                self.api = Client(login, password, settings=cached_settings)

        except (ClientCookieExpiredError, ClientLoginRequiredError) as e:
            self.api = Client(login, password, device_id=device_id, on_login=lambda x: self.on_login(session_file))

        self.process_pool = process_pool
        # self.thread_pool = thread_pool
        self.images = {}
        self.extractor_stage = extractor_stage
        self.extractor_stage_printed = False
        self.downloading_stage_printed = False
        self.delay_before = delay_before
        self.delay_error = delay_error
        self.uniq_type = uniq_type
        self.terminate = False
        self.stage = 0
        if self.extractor_stage:
            self.stage = 1
        self.good_extract = 0
        self.processes = processes
        self.threads = threads
        self.images_number = images_number
        self.rank_token = self.api.settings.get('uuid')
        self.post_codes = []
        self.image_ids = []
        self.progress_bar = progress_bar

    @staticmethod
    def on_login(api: Client, new_settings_file: str) -> None:
        cache_settings = api.settings
        with open(new_settings_file, 'w') as outfile:
            json.dump(cache_settings, outfile, default=Crawler.to_json)

    @staticmethod
    def to_json(python_object: bytes) -> dict:
        if isinstance(python_object, bytes):
            return {'__class__': 'bytes',
                    '__value__': codecs.encode(python_object, 'base64').decode()}
        raise TypeError(repr(python_object) + ' is not JSON serializable')

    @staticmethod
    def from_json(json_object: dict) -> Union[dict, str]:
        if '__class__' in json_object and json_object['__class__'] == 'bytes':
            return codecs.decode(json_object['__value__'].encode(), 'base64')
        return json_object

    @staticmethod
    def check_image_fields(image: dict) -> bool:
        return 'id' in image and 'image_versions2' in image and 'candidates' in image.get(
            'image_versions2') and 'url' in \
               image.get('image_versions2').get('candidates')[0]

    def get_image_urls(self, hashtag: str, max_id: str = None) -> Tuple[list, str]:
        result = []
        next_max_id = ''
        data = None
        while data is None:
            if self.terminate or self.stage != 0:
                return [], ''
            if self.images_number and self.progress_bar.index >= self.images_number:
                self.stage = 1
            try:
                if max_id:
                    data = self.api.feed_tag(hashtag, self.rank_token, max_id=max_id)
                else:
                    data = self.api.feed_tag(hashtag, self.rank_token)
            except Exception:
                sleep(randint(15, 60))
        if 'items' in data:
            if 'more_available' in data and data.get('more_available') and 'next_max_id' in data:
                next_max_id = data.get('next_max_id')

            for e in data.get('items'):
                if self.terminate or self.stage != 0:
                    return [], ''
                if self.images_number and self.progress_bar.index >= self.images_number:
                    self.stage = 1
                if not ('media_type' in e and 'code' in e and 'id' in e):
                    continue

                media_type = e.get('media_type')
                if media_type == 1:
                    if not Crawler.check_image_fields(e):
                        continue
                    image_url = e.get('image_versions2').get('candidates')[0].get('url')
                    filename = self.get_id_from_url(image_url)
                    if not self.is_filename_uniq(filename, hashtag, self.uniq_type):
                        continue
                    self.images[hashtag] += [filename]
                    result += [image_url]

                elif media_type == 8:
                    if 'carousel_media' not in e:
                        continue
                    for ce in e.get('carousel_media'):
                        if 'media_type' not in ce:
                            continue
                        if ce.get('media_type') != 1 or not Crawler.check_image_fields(ce):
                            continue
                        image_url = ce.get('image_versions2').get('candidates')[0].get('url')
                        filename = self.get_id_from_url(image_url)
                        if not self.is_filename_uniq(filename, hashtag, self.uniq_type):
                            continue
                        self.images[hashtag] += [filename]
                        result += [image_url]
        return result, next_max_id

    def is_filename_uniq(self, filename: str, hashtag: str, uniq_type: int = 0) -> bool:
        if uniq_type == 0:
            return filename not in self.images[hashtag]
        if uniq_type == 1:
            images = []
            for _, value in self.images.items():
                images += value
            return filename not in images
        return True

    def process(self, hashtag: str) -> None:
        for folder in self.folders:
            os.makedirs(self.base_path + hashtag + folder, exist_ok=True)

        if self.stage == 1:
            self.start_extractor(hashtag)
            return

        if not self.downloading_stage_printed:
            self.downloading_stage_print()

        self.images[hashtag] = []
        if os.path.isfile(self.base_path + hashtag + '/downloaded_images.txt'):
            with open(self.base_path + hashtag + '/downloaded_images.txt', 'r') as fp:
                self.images[hashtag] = fp.read().split('\n')
        next_max_id = None
        fp = open(self.base_path + hashtag + '/downloaded_images.txt', 'w')
        fp.write('\n'.join(self.images[hashtag]))
        thread_pool = ThreadPool(self.threads)
        while (not self.terminate) and next_max_id != '' and self.stage == 0:
            res = thread_pool.apply_async(self.get_image_urls, (hashtag, next_max_id))
            urls, next_max_id = res.get()
            urls = [[hashtag, url] for url in urls]
            results = thread_pool.imap_unordered(self.save_from_url, urls)
            for result in results:
                if result:
                    fp.write(result + '\n')
                    if self.stage == 0:
                        self.progress_bar.next()
        fp.close()
        if self.stage == 1:
            return self.start_extractor(hashtag)

    def on_press(self, key) -> Optional[bool]:
        try:
            if key is None or key.char == 'q':
                print('\nStopping...')
                self.terminate = True
                self.process_pool.close()
                self.process_pool.join()
                return False
            elif key.char == 'e' and self.stage == 0:
                self.stage = 1
                self.extractor_stage_print()
        except Exception as e:
            pass

    def downloading_stage_print(self) -> None:
        if self.downloading_stage_printed:
            return
        self.downloading_stage_printed = True
        print('\n\nStarting download...')
        print('Press e to run extractor')
        print('Press q to quit')
        self.progress_bar.next()
        self.progress_bar.next(-1)

    def extractor_stage_print(self, progress_bar_max: int = None) -> None:
        if self.extractor_stage_printed:
            return
        self.extractor_stage_printed = True
        print('\n\nStarting extractor...')
        print('Press q to quit')
        self.progress_bar.max = self.progress_bar.index if self.progress_bar.index else progress_bar_max
        self.progress_bar.index = 0
        self.progress_bar.next()
        self.progress_bar.next(-1)

    def save_from_url(self, data: List[str]) -> Optional[str]:
        hashtag, url = data
        filename = self.get_id_from_url(url)
        response = None
        if self.terminate or self.stage != 0:
            return
        if self.images_number and self.progress_bar.index >= self.images_number:
            self.stage = 1
            self.extractor_stage_print()
            return
        with open(self.base_path + hashtag + self.full_images_path + filename, 'wb') as handle:
            while not response:
                try:
                    sleep(randint(*self.delay_before) / 1000)
                    response = requests.get(url, stream=True)
                except Exception:
                    sleep(randint(*self.delay_error) / 1000)
            if not response.ok:
                return
            for block in response.iter_content(1024):
                if self.terminate or self.stage != 0:
                    os.remove(self.base_path + hashtag + self.full_images_path + filename)
                    return
                if self.images_number and self.progress_bar.index >= self.images_number:
                    os.remove(self.base_path + hashtag + self.full_images_path + filename)
                    self.stage = 1
                    self.extractor_stage_print()
                    return
                if not block:
                    break
                handle.write(block)
        return filename

    def get_id_from_url(self, url: str) -> str:
        return re.search(r'[\w-]+\.jpg', url).group(0).replace('.jpg', '.png')

    def start_extractor(self, hashtag: str) -> None:
        paths = []
        for filename in os.listdir(self.base_path + hashtag + self.full_images_path):
            if not filename.endswith('.png'):
                continue
            paths += [self.base_path + hashtag + self.full_images_path + filename]

        if not self.extractor_stage_printed:
            self.extractor_stage_print(len(paths))

        # for extract_batch in range(0, len(paths), self.processes):
        results = self.process_pool.imap_unordered(extract, paths)
        for result in results:
            if self.terminate:
                return
            path, images = result
            self.progress_bar.next()
            if not images:
                continue
            for i in range(len(images)):
                image_filename = path.split('/')[-1]
                images[i].save(self.base_path + hashtag + self.folders[i] + image_filename)
            self.good_extract += 1


def extract(path: str) -> Tuple[str, list]:
    img = Image.open(path)
    try:
        images = extractors.extractor(img)
        if images is None:
            return path, []
        # number of folders without "full" folder
        if len(images) != len(Crawler.folders) - 1:
            return path, []
        return path, images
    except Exception:
        return path, []
