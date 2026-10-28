import requests
import time
import json
import os
import html
import urllib.request
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

# Шрифт Oswald
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/oswald/Oswald%5Bwght%5D.ttf"
FONT_PATH = "Oswald.ttf"

def download_font():
    if not os.path.exists(FONT_PATH):
        try:
            urllib.request.urlretrieve(FONT_URL, FONT_PATH)
        except Exception:
            pass

def get_font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except Exception:
            return ImageFont.load_default()

def get_top_10():
    try:
        res = requests.get(f"{BASE_URL}/locations/global/pathoflegend/players", headers=HEADERS, params={"limit": 10}, timeout=10)
        if res.status_code != 200:
            return []
        return res.json().get("items", [])
    except Exception:
        return []

def get_player_stats(player_tag):
    tag_encoded = player_tag.replace("#", "%23")
    deck = []
    
    # Получаем колоду
    try:
        res = requests.get(f"{BASE_URL}/players/{tag_encoded}", headers=HEADERS, timeout=10)
        if res.status_code == 200:
            deck = res.json().get("currentDeck", [])
    except Exception:
        pass
        
    wr, battles = None, 0
    
    # Считаем винрейт
    try:
        res = requests.get(f"{BASE_URL}/players/{tag_encoded}/battlelog", headers=HEADERS, timeout=10)
        if res.status_code == 200:
            battle_log = res.json()
            wins = 0
            total = 0
            
            current_deck_ids = sorted([c['id'] for c in deck]) if deck else []
            if not current_deck_ids:
                return deck, None, 0
            
            for battle in battle_log:
                if battle.get('type') not in ['PvP', 'pathOfLegend']:
                    continue
                if not battle.get('team') or not battle.get('opponent'):
                    continue
                    
                battle_cards_data = battle['team'][0].get('cards', [])
                if not battle_cards_data:
                    continue
                    
                battle_cards = sorted([c['id'] for c in battle_cards_data])
                if battle_cards == current_deck_ids:
                    total += 1
                    if battle['team'][0].get('crowns', 0) > battle['opponent'][0].get('crowns', 0):
                        wins += 1
            if total > 0:
                wr = round((wins / total) * 100, 1)
                battles = total
    except Exception:
        pass
        
    return deck, wr, battles

def get_archetype(cards):
    if not cards: return "Unknown"
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

def build_deck_image(deck, rank, name, trophies, win_rate, battles, archetype):
    w, h = 140, 168
    padding = 20
    img_width = (w * 4) + (padding * 5)
    img_height = (h * 2) + 160
    
    base = Image.new('RGB', (img_width, img_height), color=(18, 20, 24))
    draw = ImageDraw.Draw(base)
    
    font_main = get_font(24)
    font_sub = get_font(18)
    font_wr = get_font(60)
    
    rank_text = f"#{rank}"
    bbox_rank = draw.textbbox((0, 0), rank_text, font=font_main)
    rank_width = bbox_rank[2] - bbox_rank[0]
    max_name_width = img_width - padding * 2 - rank_width - 40 
    
    safe_name = name
    while len(safe_name) > 0 and draw.textbbox((0, 0), safe_name + "...", font=font_main)[2] > max_name_width:
        safe_name = safe_name[:-1]
    if len(safe_name) < len(name):
        safe_name += "..."
        
    draw.text((padding, 20), f"{safe_name} {rank_text}", font=font_main, fill=(255, 255, 255))
    draw.text((padding, 50), f"Trophies: {trophies} | {archetype}", font=font_sub, fill=(150, 150, 160))
    
    start_y = 85
    for index in range(8):
        x = padding + (index % 4) * (w + padding)
        y = start_y + (index // 4) * (h + padding)
        
        if index < len(deck):
            card = deck[index]
            img_url = card.get('iconUrls', {}).get('medium') or card.get('iconUrls', {}).get('default')
            try:
                response = requests.get(img_url, timeout=5)
                response.raise_for_status()
                card_img = Image.open(BytesIO(response.content)).convert("RGBA").resize((w, h))
                
                mask = Image.new("L", (w, h), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle([0, 0, w, h], radius=10, fill=255)
                base.paste(card_img, (x, y), mask)
            except Exception:
                draw.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=(35, 38, 45))
                draw.text((x + 20, y + 70), "NO IMG", font=font_sub, fill=(120, 120, 120))
        else:
            draw.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=(25, 28, 35), outline=(50, 50, 60), width=2)
            draw.text((x + 15, y + 70), "NO CARD", font=font_sub, fill=(80, 80, 90))

    y_bottom = img_height - 60
    
    if win_rate is not None:
        wr_text = f"{win_rate}%"
        if win_rate < 50.0: wr_color = (255, 75, 75)
        elif win_rate > 51.0: wr_color = (75, 255, 75)
        else: wr_color = (180, 180, 180)
        
        bbox = draw.textbbox((0, 0), wr_text, font=font_wr)
        wr_width = bbox[2] - bbox[0]
        draw.text((img_width - padding - wr_width, y_bottom - 10), wr_text, font=font_wr, fill=wr_color)
        
        draw.text((padding, y_bottom + 10), f"Winrate ({battles} games)", font=font_sub, fill=(120, 120, 130))
    else:
        draw.text((padding, y_bottom + 10), "No data for this deck", font=font_sub, fill=(120, 120, 130))

    file_path = f"deck_{rank}.png"
    base.save(file_path)
    return file_path

def send_telegram_photo(photo_path, caption):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendPhoto"
    with open(photo_path, 'rb') as photo:
        res = requests.post(url, files={'photo': photo}, data={'chat_id': TG_CHANNEL_ID, 'caption': caption, 'parse_mode': 'HTML'})
        print("ОТВЕТ ТГ:", res.text)

def main():
    download_font() 
    
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
        except Exception:
            pass

    if current_tags != list(previous_data.keys()):
        print("2. Топ изменился! Работаем...")
        header_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        requests.post(header_url, data={'chat_id': TG_CHANNEL_ID, 'text': "🚨 <b>Обновление Топ-10!</b>", 'parse_mode': 'HTML'})
        
        new_data = {}
        for player in current_top:
            try:
                print(f"Собираю данные: {player['name']}...")
                
                deck, wr, battles = get_player_stats(player['tag'])
                archetype = get_archetype(deck)
                
                safe_elo = player.get('eloRating', player.get('trophies', 0))
                
                img_path = build_deck_image(
                    deck, player['rank'], player['name'], 
                    safe_elo, wr, battles, archetype
                )
                
                safe_name = html.escape(player['name'])
                caption = f"🏆 <b>Топ {player['rank']}</b>\n👤 {safe_name}\n🏅 {safe_elo} кубков"
                
                send_telegram_photo(img_path, caption)
                os.remove(img_path)
                time.sleep(1)
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
