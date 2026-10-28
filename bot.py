import requests
import time
import json
import os
from io import BytesIO
from PIL import Image

# Берем токены из настроек Гитхаба (секретов)
CR_API_TOKEN = os.environ.get("CR_API_TOKEN")
TG_BOT_TOKEN = os.environ.get("TG_BOT_TOKEN")
TG_CHANNEL_ID = os.environ.get("TG_CHANNEL_ID")

BASE_URL = "https://proxy.royaleapi.dev/v1"
HEADERS = {
    "Authorization": f"Bearer {CR_API_TOKEN}",
    "Accept": "application/json"
}
STATE_FILE = "last_top10.json"

def get_top_10():
    # Указываем эндпоинт для Пути Легенд
    res = requests.get(f"{BASE_URL}/locations/global/pathoflegend/players", headers=HEADERS, params={"limit": 10}, timeout=10)
    print("СТАТУС ОТ КЛЕШ РОЯЛЬ:", res.status_code)
    print("ЧТО ОТВЕТИЛ СЕРВЕР:", res.text)
    res.raise_for_status()
    return res.json().get("items", [])

def build_deck_image(cards, rank):
    w, h = 150, 180
    grid_img = Image.new('RGB', (w * 4, h * 2), color=(40, 40, 40))
    for index, card in enumerate(cards):
        # Берем официальную ссылку на картинку прямо из API
        img_url = card.get('iconUrls', {}).get('medium')
        if not img_url:
            continue
        try:
            response = requests.get(img_url, timeout=5)
            response.raise_for_status()
            card_img = Image.open(BytesIO(response.content)).convert("RGBA").resize((w, h))
            col = index % 4
            row = index // 4
            grid_img.paste(card_img, (col * w, row * h), card_img)
        except Exception as e:
            print(f"Ошибка загрузки картинки {card['name']}: {e}")
    file_path = f"deck_{rank}.png"
    grid_img.save(file_path)
    return file_path

def build_deck_image(cards, rank):
    w, h = 150, 180
    grid_img = Image.new('RGB', (w * 4, h * 2), color=(40, 40, 40))
    for index, card in enumerate(cards):
        card_name = card['name'].replace(" ", "%20")
        img_url = f"https://cdn.royaleapi.com/static/img/cards-150/{card_name}.png"
        try:
            response = requests.get(img_url, timeout=5)
            response.raise_for_status()
            card_img = Image.open(BytesIO(response.content)).convert("RGBA").resize((w, h))
            col = index % 4
            row = index // 4
            grid_img.paste(card_img, (col * w, row * h), card_img)
        except Exception as e:
            print(f"Ошибка картинки: {e}")
    file_path = f"deck_{rank}.png"
    grid_img.save(file_path)
    return file_path

def send_telegram_photo(photo_path, caption):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
    with open(photo_path, 'rb') as photo:
        res = requests.post(url, files={'photo': photo}, data={'chat_id': TG_CHANNEL_ID, 'caption': caption, 'parse_mode': 'HTML'})
        print("ОТВЕТ ТЕЛЕГРАМА НА ФОТО:", res.text) # <--- ВОТ ЭТА ХУЙНЯ ПОКАЖЕТ ОШИБКУ

def main():
    print("1. Начинаю запрос к API...")
    current_top = get_top_10()
    print(f"2. API вернул {len(current_top)} игроков.")
    current_tags = [p['tag'] for p in current_top]
    
    previous_tags = []
    if os.path.exists(STATE_FILE):
        print("3. Файл памяти найден. Читаю...")
        try:
            with open(STATE_FILE, 'r') as f:
                previous_tags = json.load(f)
        except Exception as e:
            print(f"Ошибка чтения памяти: {e}")
            previous_tags = []
    else:
        print("3. Файла памяти нет. Считаю топ пустым.")

    if current_tags != previous_tags:
        print("6. Топ изменился! Отправляю в ТГ...")
        header_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        res_header = requests.post(header_url, data={'chat_id': TG_CHANNEL_ID, 'text': "🚨 <b>Обновление Топ-10!</b>", 'parse_mode': 'HTML'})
        
        # Пост-заголовок улетел, теперь очередь картинок
        for player in current_top:
            try:
                print(f"Обрабатываю игрока: {player['name']}...")
                deck = get_player_deck(player['tag'])
                if deck:
                    img_path = build_deck_image(deck, player['rank'])
                    caption = f"🏆 <b>Топ {player['rank']}</b>\n👤 {player['name']}"
                    send_telegram_photo(img_path, caption)
                    os.remove(img_path)
                    time.sleep(2)
                else:
                    print(f"У игрока {player['name']} нет колоды или профиль закрыт.")
            except Exception as e:
                print(f"ПРОБЛЕМА С ИГРОКОМ {player['name']}: {e}")
                continue # Если упал один - идем к следующему
                
        with open(STATE_FILE, 'w') as f:
            json.dump(current_tags, f)
            print("7. Память сохранена.")
    else:
        print("6. Топ НЕ изменился. Ничего не делаю.") 
if __name__ == "__main__":
    main()
