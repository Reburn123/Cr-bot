import requests
import time
import json
import os
import html
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

# Настройки
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
    try:
        res = requests.get(f"{BASE_URL}/locations/global/pathoflegend/players", headers=HEADERS, params={"limit": 10}, timeout=10)
        if res.status_code != 200:
            print(f"⚠️ Сервер API вернул ошибку {res.status_code}. Пропускаю этот запуск.")
            return []
        return res.json().get("items", [])
    except Exception as e:
        print(f"⚠️ Ошибка сети: {e}")
        return []

def get_player_deck(player_tag):
    tag_encoded = player_tag.replace("#", "%23")
    res = requests.get(f"{BASE_URL}/players/{tag_encoded}", headers=HEADERS, timeout=10)
    res.raise_for_status()
    return res.json().get("currentDeck", [])

# --- СЧИТАЕМ ВИНРЕЙТ ПО БОЯМ ---
def get_win_rate(player_tag):
    tag_encoded = player_tag.replace("#", "%23")
    try:
        res = requests.get(f"{BASE_URL}/players/{tag_encoded}/battlelog", headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return 50.0 # Если профиль закрыт, ставим 50%
            
        battles = res.json()
        if not battles:
            return 50.0
            
        wins = 0
        total = 0
        for battle in battles:
            # Берем только бои Пути Легенд (или обычные 1v1, если нужно)
            if battle.get('type') not in ['pathOfLegend', 'PvP']:
                continue
                
            my_crowns = battle['team'][0].get('crowns', 0)
            opp_crowns = battle['opponent'][0].get('crowns', 0)
            
            if my_crowns > opp_crowns:
                wins += 1
            total += 1
            
        if total == 0:
            return 50.0
            
        return round((wins / total) * 100, 1)
    except Exception as e:
        print(f"Ошибка боев {player_tag}: {e}")
        return 50.0

# --- ОПРЕДЕЛЯЕМ АРХЕТИП ---
def get_archetype(cards):
    names = [c['name'] for c in cards]
    if "Hog Rider" in names and "Earthquake" in names: return "Hog EQ"
    if "Golem" in names: return "Golem"
    if "X-Bow" in names or "Mortar" in names: return "Siege"
    if "Goblin Barrel" in names: return "Log Bait"
    if "Royal Giant" in names: return "RG"
    if "Lava Hound" in names: return "LavaLoon"
    if "Graveyard" in names: return "Graveyard"
    if "Miner" in names and "Wall Breakers" in names: return "Miner WB"
    return "META"

# --- РИСУЕМ КАРТИНКУ ---
def build_deck_image(cards, rank, name, trophies, win_rate, archetype, prev_wr):
    w, h = 150, 180
    # Увеличиваем высоту картинки внизу, чтобы влезла инфа
    img_height = h * 2 + 80
    grid_img = Image.new('RGB', (w * 4, img_height), color=(25, 25, 35))
    
    # 1. Рисуем карты
    for index, card in enumerate(cards):
        img_url = card.get('iconUrls', {}).get('medium') or card.get('iconUrls', {}).get('default')
        if img_url:
            try:
                response = requests.get(img_url, timeout=5)
                response.raise_for_status()
                card_img = Image.open(BytesIO(response.content)).convert("RGBA").resize((w, h))
                col = index % 4
                row = index // 4
                grid_img.paste(card_img, (col * w, row * h), card_img)
            except Exception:
                # Если картинка не грузится, рисуем серый квадрат
                draw = ImageDraw.Draw(grid_img)
                col = index % 4
                row = index // 4
                draw.rectangle([col * w, row * h, (col + 1) * w, (row + 1) * h], fill=(60, 60, 70))
                draw.text((col * w + 10, row * h + 80), card['name'], fill=(255, 255, 255))

    # 2. Рисуем текст
    draw = ImageDraw.Draw(grid_img)
    try:
        # Стандартный шрифт на серверах Гитхаба (Ubuntu)
        font_main = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 22)
        font_sub = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_wr = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
    except:
        font_main = ImageFont.load_default()
        font_sub = ImageFont.load_default()
        font_wr = ImageFont.load_default()

    # Цвет винрейта
    if win_rate < 50.0:
        wr_color = (255, 80, 80)  # Красный
    elif win_rate > 51.0:
        wr_color = (80, 255, 80)  # Зеленый
    else:
        wr_color = (180, 180, 180) # Серый

    # Стрелка тренда
    trend = ""
    trend_color = (255, 255, 255)
    if prev_wr is not None and prev_wr != win_rate:
        if win_rate > prev_wr:
            trend = "▲"
            trend_color = (80, 255, 80)
        else:
            trend = "▼"
            trend_color = (255, 80, 80)

    y_text = h * 2 + 10
    
    # Левая часть (Ник и кубки)
    draw.text((15, y_text), f"🏆 {rank}. {name}", font=font_main, fill=(255, 255, 255))
    draw.text((15, y_text + 30), f"🏅 {trophies} | {archetype}", font=font_sub, fill=(200, 200, 200))
    
    # Правая часть (Винрейт и стрелка)
    wr_text = f"WR: {win_rate}%"
    draw.text((w * 4 - 180, y_text), wr_text, font=font_wr, fill=wr_color)
    draw.text((w * 4 - 50, y_text), trend, font=font_wr, fill=trend_color)

    file_path = f"deck_{rank}.png"
    grid_img.save(file_path)
    return file_path

# --- ОТПРАВКА ---
def send_telegram_photo(photo_path, caption):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
    with open(photo_path, 'rb') as photo:
        res = requests.post(url, files={'photo': photo}, data={'chat_id': TG_CHANNEL_ID, 'caption': caption, 'parse_mode': 'HTML'})
        print("ОТВЕТ ТГ:", res.text)

# --- ГЛАВНЫЙ ЦИКЛ ---
def main():
    print("1. Запрашиваю топ...")
    current_top = get_top_10()
    current_tags = [p['tag'] for p in current_top]
    
    previous_data = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                previous_data = json.load(f)
        except Exception:
            pass

    # Сравниваем списки тегов
    if current_tags != list(previous_data.keys()):
        print("2. Топ изменился! Работаем...")
        header_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        requests.post(header_url, data={'chat_id': TG_CHANNEL_ID, 'text': "🚨 <b>Обновление Топ-10!</b>", 'parse_mode': 'HTML'})
        
        new_data = {}
        for player in current_top:
            try:
                print(f"Обрабатываю: {player['name']}...")
                deck = get_player_deck(player['tag'])
                if deck:
                    # Получаем WR и архетип
                    wr = get_win_rate(player['tag'])
                    archetype = get_archetype(deck)
                    
                    # Смотрим, какой был WR в прошлый раз
                    prev_wr = None
                    if player['tag'] in previous_data:
                        prev_wr = previous_data[player['tag']].get('win_rate')
                    
                    # Рисуем
                    img_path = build_deck_image(
                        deck, player['rank'], player['name'], 
                        player['eloRating'], wr, archetype, prev_wr
                    )
                    
                    safe_name = html.escape(player['name'])
                    caption = f"🏆 <b>Топ {player['rank']}</b>\n👤 {safe_name}\n🏅 {player['eloRating']} кубков"
                    
                    send_telegram_photo(img_path, caption)
                    os.remove(img_path)
                    time.sleep(3)
                    
                    # Запоминаем текущий WR
                    new_data[player['tag']] = {'win_rate': wr}
            except Exception as e:
                print(f"ОШИБКА С {player['name']}: {e}")
                continue 
                
        with open(STATE_FILE, 'w') as f:
            json.dump(new_data, f)
            print("Память сохранена.")
    else:
        print("Топ НЕ изменился.")

if __name__ == "__main__":
    main()
