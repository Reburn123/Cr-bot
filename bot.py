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

# УМНАЯ ЗАГРУЗКА ШРИФТОВ
def get_font(font_name, size):
    # Возможные пути, где могут лежать шрифты на сервере Гитхаба
    paths = [
        f"/usr/share/fonts/opentype/noto/{font_name}",
        f"/usr/share/fonts/truetype/noto/{font_name}",
        f"/usr/share/fonts/truetype/dejavu/{font_name}",
        f"./{font_name}" # Если ты сам закинул шрифт в репозиторий
    ]
    for path in paths:
        try:
            return ImageFont.truetype(path, size)
        except IOError:
            continue
    return ImageFont.load_default() # Если вообще ничего не нашли

def get_top_10():
    try:
        res = requests.get(f"{BASE_URL}/locations/global/pathoflegend/players", headers=HEADERS, params={"limit": 10}, timeout=10)
        if res.status_code != 200:
            return []
        return res.json().get("items", [])
    except:
        return []

def get_player_deck(player_tag):
    tag_encoded = player_tag.replace("#", "%23")
    try:
        res = requests.get(f"{BASE_URL}/players/{tag_encoded}", headers=HEADERS, timeout=10)
        if res.status_code == 200:
            return res.json().get("currentDeck", [])
    except:
        pass
    return []

def get_win_rate(player_tag):
    tag_encoded = player_tag.replace("#", "%23")
    try:
        res = requests.get(f"{BASE_URL}/players/{tag_encoded}/battlelog", headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return None, 0
            
        battles = res.json()
        wins = 0
        total = 0
        
        for battle in battles:
            if battle.get('type') != 'pathOfLegend':
                continue
            if 'team' not in battle or 'opponent' not in battle:
                continue
                
            my_crowns = battle['team'][0].get('crowns', 0)
            opp_crowns = battle['opponent'][0].get('crowns', 0)
            
            if my_crowns > opp_crowns:
                wins += 1
            total += 1
            
        if total < 10:
            return None, total
            
        return round((wins / total) * 100, 1), total
    except:
        return None, 0

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
    return "Meta Deck"

def build_deck_image(cards, rank, name, trophies, win_rate, battles, archetype, prev_wr):
    w, h = 150, 180
    padding = 20
    img_width = w * 4 + padding * 2
    img_height = h * 2 + 160 
    
    base = Image.new('RGB', (img_width, img_height), color=(18, 24, 38))
    draw = ImageDraw.Draw(base)
    
    # Используем нашу умную загрузку (NotoSansCJK-Bold.ttc точно есть на Ubuntu)
    font_main = get_font("NotoSansCJK-Bold.ttc", 22)
    font_sub = get_font("NotoSansCJK-Regular.ttc", 16)
    font_wr = get_font("NotoSansCJK-Bold.ttc", 42)

    # Верхняя панель
    draw.rounded_rectangle([10, 10, img_width - 10, 70], radius=10, fill=(28, 35, 55), outline=(255, 215, 0), width=2)
    draw.text((padding + 10, 25), f"#{rank}  {name}", font=font_main, fill=(255, 255, 255))
    
    if win_rate is None:
        wr_text = "N/A"
        wr_color = (150, 150, 150)
        trend = ""
    else:
        wr_text = f"{win_rate}%"
        if win_rate < 50.0: wr_color = (255, 60, 60)
        elif win_rate > 51.0: wr_color = (50, 255, 50)
        else: wr_color = (180, 180, 180)
        
        trend = ""
        trend_color = (255, 255, 255)
        if isinstance(prev_wr, (int, float)) and prev_wr != win_rate:
            if win_rate > prev_wr:
                trend = "▲"
                trend_color = (50, 255, 50)
            else:
                trend = "▼"
                trend_color = (255, 60, 60)

    bbox = draw.textbbox((0, 0), wr_text, font=font_wr)
    wr_width = bbox[2] - bbox[0]
    draw.text((img_width - 40 - wr_width, 15), wr_text, font=font_wr, fill=wr_color)
    if trend:
        draw.text((img_width - 35, 25), trend, font=font_main, fill=trend_color)

    # Карты
    start_y = 90
    for index, card in enumerate(cards):
        img_url = card.get('iconUrls', {}).get('medium') or card.get('iconUrls', {}).get('default')
        if img_url:
            try:
                response = requests.get(img_url, timeout=5)
                response.raise_for_status()
                card_img = Image.open(BytesIO(response.content)).convert("RGBA").resize((w, h))
                
                col = index % 4
                row = index // 4
                x = padding + col * w
                y = start_y + row * h
                
                draw.rectangle([x + 3, y + 3, x + w + 3, y + h + 3], fill=(10, 10, 15))
                base.paste(card_img, (x, y), card_img)
                draw.rectangle([x, y, x + w, y + h], outline=(255, 215, 0), width=2)
            except:
                pass

    # Низ
    y_bottom = img_height - 55
    draw.rounded_rectangle([10, y_bottom, img_width - 10, img_height - 10], radius=10, fill=(28, 35, 55), outline=(255, 215, 0), width=2)
    
    draw.text((padding + 10, y_bottom + 12), f"Trophies: {trophies}  |  {archetype}", font=font_sub, fill=(255, 255, 255))
    
    if battles < 10:
        draw.text((img_width - 160, y_bottom + 12), f"Battles: {battles}", font=font_sub, fill=(200, 100, 100))

    file_path = f"deck_{rank}.png"
    base.save(file_path)
    return file_path

def send_telegram_photo(photo_path, caption):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
    with open(photo_path, 'rb') as photo:
        res = requests.post(url, files={'photo': photo}, data={'chat_id': TG_CHANNEL_ID, 'caption': caption, 'parse_mode': 'HTML'})
        print("ОТВЕТ ТГ:", res.text)

def main():
    print("1. Запрашиваю топ...")
    current_top = get_top_10()
    if not current_top:
        return
        
    current_tags = [p['tag'] for p in current_top]
    previous_data = {}
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r') as f:
                previous_data = json.load(f)
        except:
            pass

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
                    wr, battles = get_win_rate(player['tag'])
                    archetype = get_archetype(deck)
                    
                    prev_wr = None
                    if player['tag'] in previous_data:
                        prev_wr = previous_data[player['tag']].get('win_rate')
                    
                    img_path = build_deck_image(
                        deck, player['rank'], player['name'], 
                        player['eloRating'], wr, battles, archetype, prev_wr
                    )
                    
                    safe_name = html.escape(player['name'])
                    caption = f"🏆 <b>Топ {player['rank']}</b>\n👤 {safe_name}\n🏅 {player['eloRating']} кубков"
                    
                    send_telegram_photo(img_path, caption)
                    os.remove(img_path)
                    time.sleep(3)
                    
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
