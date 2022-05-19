### Установка
```shell
git clone https://github.com/ksburaya/makeup-crawler && cd makeup-crawler
python3 -m venv venv && source venv/bin/activate
pip install cmake && pip install -r requirements.txt
cp .env.example .env && nano .env
```

### Запустить сбор фото для хэштегов makeup и yellowmakeup
```shell
python main.py "makeup yellowmakeup"
```

### Запустить обработку фото из папок makeup и bluemakeup
```shell
python main.py "makeup bluemakeup" -e
```

### Hotkeys
q - остановка всего

e - остановить скачивание и запустить обработку
