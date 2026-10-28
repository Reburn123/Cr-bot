import requests
import time
import json
import os
import html
import urllib.request
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
from collections import Counter

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

# КАЧАЕМ ЖИРНЫЙ ШРИФТ С ПОДДЕРЖКОЙ ИЕРОГЛИФОВ (NotoSansSC-Bold)
FONT_URL = "https://github.com/googlefonts/noto-cjk/raw/main/Sans/OTF/SimplifiedChinese/NotoSansSC-Bold.otf"
FONT_PATH = "NotoSansSC-Bold.otf"

def download_font():
    if not os.path.exists(FONT_PATH):
        try:
            print("Скачиваю шрифт (может занять 5-10 сек)...")
            urllib.request.urlretrieve(FONT_URL, FONT_PATH)
        except Exception as e:
            print(f"Не смог скачать шрифт: {e}")

def get_top_10():
    try:
        res = requests.get(f"{BASE_URL}/locations/global/pathoflegend/players", headers=HEADERS, params={"limit": 10}, timeout=10)
        if res.status_code != 200:
            return []
        return res.json().get("items", [])
    except:
        return []

def get_main_deck_and_winrate(player_tag):
    tag_encoded = player_tag.replace("#", "%23")
    try:
        res = requests.get(f"{BASE_URL}/players/{tag_encoded}/battlelog", headers=HEADERS, timeout=10)
        if res.status_code != 200:
            return None, None, 0
            
        battles = res.json()
        valid_decks = []
        
        for battle in battles:
            # Отсеиваем испытания и ивенты
            if battle.get('type') not in ['PvP', 'pathOfLegend']:
                continue
                
            # ЖЕСТКАЯ ЗАЩИТА ОТ БИТОГО API (Тест 1)
            if not battle.get('team') or not battle.get('opponent') or len(battle['opponent']) == 0:
                continue
                
            team_cards = battle['team'][0].get('cards', [])
            if len(team_cards) != 8:
                continue
                
            card_ids = tuple(sorted([c['id'] for c in team_cards]))
            is_win = battle['team'][0].get('crowns', 0) > battle['opponent'][0].get('crowns', 0)
            
            valid_decks.append({
                'key': card_ids,
                'cards': team_cards,
                'is_win': is_win
            })
            
        if not valid_decks:
            return None, None, 0
            
        deck_counts = Counter([d['key'] for d in valid_decks])
        most_common_key = deck_counts.most_common(1)[0][0]
        
        main_deck = None
        wins = 0
        total = 0
        for d in valid_decks:
            if d['key'] == most_common_key:
                main_deck = d['cards']
                total += 1
                if d['is_win']:
                    wins += 1
                    
        win_rate = round((wins / total) * 100, 1) if total > 0 else None
        return main_deck, win_rate, total
    except Exception as e:
        print(f"Ошибка парсинга боев: {e}")
        return None, None, 0

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

def get_font(size):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except:
        try:
            return ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", size)
        except:
            return ImageFont.load_default()

def build_deck_image(deck, rank, name, trophies, win_rate, battles, archetype, prev_wr):
    if not deck:
        deck = []
        
    w, h = 160, 192
    padding = 30
    img_width = w * 4 + padding * 2
    img_height = h * 2 + 220 
    
    base = Image.new('RGB', (img_width, img_height), color=(11, 16, 30))
    draw = ImageDraw.Draw(base)
    for i in range(img_height):
        color = (11 + int(i * 0.02), 16 + int(i * 0.03), 30 + int(i * 0.05))
        draw.line([(0, i), (img_width, i)], fill=color)
    
    font_main = get_font(22)
    font_sub = get_font(16)
    font_wr = get_font(55)
    font_rank = get_font(28)

    draw.rounded_rectangle([15, 15, img_width - 15, 85], radius=15, fill=(22, 28, 45), outline=(245, 194, 66), width=3)
    
    # УМНАЯ ОБРЕЗКА НИКА (Тест 3)
    rank_text = f"#{rank}"
    bbox_rank = draw.textbbox((0, 0), rank_text, font=font_rank)
    rank_width = bbox_rank[2] - bbox_rank[0]
    max_name_width = img_width - 30 - rank_width - 60 
    
    safe_name = name
    # Защита от бесконечного цикла, если шрифт совсем не влезает
    while len(safe_name) > 0 and draw.textbbox((0, 0), safe_name + "...", font=font_main)[2] > max_name_width:
        safe_name = safe_name[:-1]
    if len(safe_name) < len(name):
        safe_name += "..."
        
    draw.text((30, 30), safe_name, font=font_main, fill=(255, 255, 255))
    
    safe_trophies = trophies if trophies else 0
    draw.text((30, 55), f"Trophies: {safe_trophies} | {archetype}", font=font_sub, fill=(180, 190, 210))
    
    draw.text((img_width - 30 - rank_width, 35), rank_text, font=font_rank, fill=(245, 194, 66))

    start_y = 110
    for index in range(8): 
        x = padding + (index % 4) * w
        y = start_y + (index // 4) * h
        
        draw.rounded_rectangle([x + 4, y + 4, x + w + 4, y + h + 4], radius=10, fill=(0, 0, 0))
        
        if index < len(deck):
            card = deck[index]
            img_url = card.get('iconUrls', {}).get('medium') or card.get('iconUrls', {}).get('default')
            try:
                response = requests.get(img_url, timeout=5)
                card_img = Image.open(BytesIO(response.content)).convert("RGBA").resize((w, h))
                mask = Image.new("L", (w, h), 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle([0, 0, w, h], radius=10, fill=255)
                base.paste(card_img, (x, y), mask)
                draw.rounded_rectangle([x, y, x + w, y + h], radius=10, outline=(245, 194, 66), width=3)
            except:
                draw.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=(40, 45, 60), outline=(245, 194, 66), width=3)
                draw.text((x + w//4, y + h//2 - 10), "NO IMG", font=font_sub, fill=(150, 150, 150))
        else:
            draw.rounded_rectangle([x, y, x + w, y + h], radius=10, fill=(30, 35, 50), outline=(100, 100, 100), width=2)

    badge_w, badge_h = 180, 70
    badge_x = img_width - badge_w - 20
    badge_y = img_height - 100
    
    if win_rate is None:
        wr_text = "N/A"
        wr_color = (150, 150, 150)
        trend = ""
    else:
        wr_text = f"{win_rate}%"
        if win_rate < 50.0: wr_color = (231, 76, 60)
        elif win_rate > 51.0: wr_color = (46, 204, 113)
        else: wr_color = (149, 165, 166)
        
        trend = ""
        trend_color = (255, 255, 255)
        if isinstance(prev_wr, (int, float)) and prev_wr != win_rate:
            if win_rate > prev_wr:
                trend = "▲"
                trend_color = (46, 204, 113)
            else:
                trend = "▼"
                trend_color = (231, 76, 60)

    draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], radius=15, fill=(15, 20, 35), outline=wr_color, width=3)
    
    bbox_wr = draw.textbbox((0, 0), wr_text, font=font_wr)
    wr_w = bbox_wr[2] - bbox_wr[0]
    wr_h = bbox_wr[3] - bbox_wr[1]
    draw.text((badge_x + (badge_w - wr_w)//2 - (15 if trend else 0), badge_y + (badge_h - wr_h)//2 - 8), wr_text, font=font_wr, fill=wr_color)
    
    if trend:
        draw.text((badge_x + badge_w - 35, badge_y + 20), trend, font=font_main, fill=trend_color)

    if battles > 0:
        draw.text((30, img_height - 75), f"Games on this deck: {battles}", font=font_sub, fill=(150, 160, 180))
    else:
        draw.text((30, img_height - 75), f"No valid battles", font=font_sub, fill=(150, 160, 180))

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
        except:
            pass

    if current_tags != list(previous_data.keys()):
        print("2. Топ изменился! Работаем...")
        header_url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
        requests.post(header_url, data={'chat_id': TG_CHANNEL_ID, 'text': "🚨 <b>Обновление Топ-10!</b>", 'parse_mode': 'HTML'})
        
        new_data = {}
        for player in current_top:
            try:
                print(f"Анализирую бои: {player['name']}...")
                
                main_deck, wr, battles = get_main_deck_and_winrate(player['tag'])
                
                if not main_deck:
                    res = requests.get(f"{BASE_URL}/players/{player['tag'].replace('#', '%23')}", headers=HEADERS)
                    if res.status_code == 200:
                        main_deck = res.json().get("currentDeck", [])
                
                archetype = get_archetype(main_deck)
                
                prev_wr = None
                if player['tag'] in previous_data:
                    prev_wr = previous_data[player['tag']].get('win_rate')
                
                safe_elo = player.get('eloRating', player.get('trophies', 0))
                
                img_path = build_deck_image(
                    main_deck, player['rank'], player['name'], 
                    safe_elo, wr, battles, archetype, prev_wr
                )
                
                safe_name = html.escape(player['name'])
                caption = f"🏆 <b>Топ {player['rank']}</b>\n👤 {safe_name}\n🏅 {safe_elo} кубков\n\n📊 <i>Винрейт по основной колоде</i>"
                
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
