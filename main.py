from datetime import datetime, timedelta
import json
import os
import random
import threading
import time

# ==========================================
# Flask (ダミー定義含む)
# ==========================================
try:
    from flask import Flask
except ModuleNotFoundError:
    class Flask:
        def __init__(self, name):
            self.name = name
            self.routes = {}

        def route(self, path):
            def decorator(func):
                self.routes[path] = func
                return func
            return decorator

        def run(self, *args, **kwargs):
            pass

        def test_client(self):
            class Client:
                def __init__(self, app):
                    self.app = app

                def get(self, path):
                    body = self.app.routes[path]()
                    return type(
                        "Response",
                        (),
                        {
                            "status_code": 200,
                            "get_data": lambda self, as_text=False: body
                        }
                    )()
            return Client(self)

# ==========================================
# Discord (ダミー定義含む)
# ==========================================
try:
    import discord
    from discord.ext import commands
    from discord import app_commands
except ModuleNotFoundError:
    class DummyChoice:
        def __init__(self, name=None, value=None):
            self.name = name
            self.value = value

        def __class_getitem__(cls, item):
            return cls

    class DummyAppCommands:
        @staticmethod
        def choices(**kwargs):
            def deco(func):
                return func
            return deco
        Choice = DummyChoice

    class DummyIntents:
        members = False
        @staticmethod
        def default():
            return DummyIntents()

    class DummyDiscord:
        Intents = DummyIntents
        Interaction = object

    discord = DummyDiscord()
    app_commands = DummyAppCommands()
    commands = None

# ==========================================
# Bot初期化
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
app = Flask(__name__)

@app.route("/")
def health():
    return "Bot is running"

if commands is None:
    class DummyBot:
        def __init__(self, *args, **kwargs):
            self.tree = self
        def command(self, *args, **kwargs):
            def deco(func):
                return func
            return deco
        def event(self, *args, **kwargs):
            def deco(func):
                return func
            return deco
        async def sync(self):
            pass
        def run(self, *args, **kwargs):
            pass
    bot = DummyBot()
else:
    intents = discord.Intents.default()
    intents.members = True
    bot = commands.Bot(command_prefix="/", intents=intents)

# ==========================================
# JSON 永続化データ管理
# ==========================================
DATA_FILE = "trains.json"
USAGE_FILE = "usage.json"

def load_trains():
    if not os.path.exists(DATA_FILE):
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump({}, f)
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_trains(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

def load_usage_data():
    if not os.path.exists(USAGE_FILE):
        return {}
    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}

def save_usage_data(data):
    try:
        with open(USAGE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except OSError:
        pass

# ==========================================
# 権限・クールダウン設定
# ==========================================
COMMAND_ROLE_ID = 1510405214811852900
ADMIN_ROLE_ID = 1510021467167789104
DEFAULT_ROUTE_NAME = "BRT1"

async def check_role(interaction: discord.Interaction) -> bool:
    if not any(role.id == COMMAND_ROLE_ID for role in interaction.user.roles):
        await interaction.response.send_message("このコマンドを使う権限がありません。", ephemeral=True)
        return False
    return True

COMMAND_RULES = {
    "create": {
        "unlimited_roles": [1511882841997185064],
        "limited_roles": [1510021467155202057],
        "window_sec": 12 * 3600,
        "limit": 4
    },
    "create_man": {
        "unlimited_roles": [1511882841997185064],
        "limited_roles": [1510405214811852900],
        "window_sec": 24 * 3600,
        "limit": 4
    },
    "create_auto": {
        "unlimited_roles": [1511882841997185064],
        "limited_roles": [1510405214811852900],
        "window_sec": 24 * 3600,
        "limit": 4
    }
}

def format_remaining_time(seconds):
    if seconds <= 0:
        return "0時間0分"
    hours = seconds // 3600
    minutes = (seconds % 3600 + 59) // 60
    if minutes >= 60:
        hours += 1
        minutes -= 60
    return f"{hours}時間{minutes}分"

async def check_command_permission(interaction: discord.Interaction, command_name: str) -> bool:
    rules = COMMAND_RULES.get(command_name)
    if rules is None:
        await interaction.response.send_message("このコマンドを使用する権限がありません。", ephemeral=True)
        return False

    user_roles = [getattr(role, "id", None) for role in getattr(interaction.user, "roles", [])]
    if ADMIN_ROLE_ID in user_roles:
        return True
    if any(role_id in rules["unlimited_roles"] for role_id in user_roles):
        return True
    if not any(role_id in rules["limited_roles"] for role_id in user_roles):
        await interaction.response.send_message("このコマンドを使用する権限がありません。", ephemeral=True)
        return False

    user_id = str(interaction.user.id)
    now = int(time.time())
    usage_data = load_usage_data()
    user_usage = usage_data.setdefault(user_id, {})
    timestamps = user_usage.setdefault(command_name, [])
    window_start = now - rules["window_sec"]
    timestamps = [ts for ts in timestamps if ts > window_start]

    if len(timestamps) >= rules["limit"]:
        earliest = min(timestamps)
        remaining = earliest + rules["window_sec"] - now
        await interaction.response.send_message(f"クールダウン中です。\n\nあと {format_remaining_time(remaining)}後に利用できます。", ephemeral=True)
        user_usage[command_name] = timestamps
        save_usage_data(usage_data)
        return False

    timestamps.append(now)
    user_usage[command_name] = timestamps
    usage_data[user_id] = user_usage
    save_usage_data(usage_data)
    return True

# ==========================================
# 【完成版】BRTデータ (路線・停留所・所要時間)
# ==========================================
ROUTE_STATIONS = {
    # あけぼの ➔ 虹の原中央 ➔ あおなみセンター の正しい順番に修正
    "BRT1": ["あけぼの", "虹の原中央", "あおなみセンター"],
    # 春巻公園から始まるルートを別路線として独立
    "BRT1(春巻)": ["春巻公園", "運動公園", "月見原", "鶴巻団地", "虹の原中央", "あおなみセンター"],
    
    "BRT2": ["あけぼの", "春町公園", "灯", "北吉浪", "本吉浪", "吉浪本町"],
    "BRT2-3": ["吉浪本町", "本吉浪", "北吉浪", "吉浪各務原", "BRT海老塚", "団地西", "総合病院"],
    "虹2": ["あおなみセンター", "虹の原中央", "中央坂下", "団地西", "本新宿", "公民館前", "三叉路", "あおなみ"],
    "BRT5(出入)": ["車庫", "センター本通り", "たちばな", "北詰"],
    "BRT5": ["北詰", "たちばな", "本通り", "車庫", "シャトル虹の原", "中央", "中央坂下", "団地西", "2丁目鶴巻通り", "吉田クリニック", "運動公園", "北吉浪"],
    "霞01": ["月見原", "波平入口", "団地西", "虹の原中央", "あおなみセンター", "夢が丘6丁目", "つばき産業道路"]
}

STOP_TIME = 15  # 停車時間を15秒に設定
TURNBACK_MINUTES = 5
MIN_HEADWAY = 2

# 隣接区間の所要時間（秒）
SEGMENT_TIMES = {
    # BRT1
    ("あけぼの", "虹の原中央"): 45, 
    ("虹の原中央", "あおなみセンター"): 45,
    
    # BRT1(春巻)
    ("春巻公園", "運動公園"): 45, 
    ("運動公園", "月見原"): 45, 
    ("月見原", "鶴巻団地"): 45, 
    ("鶴巻団地", "虹の原中央"): 60, 
    ("虹の原中央", "あおなみセンター"): 45,
    
    # BRT2
    ("あけぼの", "春町公園"): 45, 
    ("春町公園", "灯"): 60, 
    ("灯", "北吉浪"): 60, 
    ("北吉浪", "本吉浪"): 75, 
    ("本吉浪", "吉浪本町"): 60,
    
    # BRT2-3
    ("吉浪本町", "本吉浪"): 60, 
    ("本吉浪", "北吉浪"): 75, 
    ("北吉浪", "吉浪各務原"): 105, 
    ("吉浪各務原", "BRT海老塚"): 45, 
    ("BRT海老塚", "団地西"): 60, 
    ("団地西", "総合病院"): 60,
    
    # 虹2
    ("あおなみセンター", "虹の原中央"): 75, 
    ("虹の原中央", "中央坂下"): 45, 
    ("中央坂下", "団地西"): 30, 
    ("団地西", "本新宿"): 60, 
    ("本新宿", "公民館前"): 45, 
    ("公民館前", "三叉路"): 45, 
    ("三叉路", "あおなみ"): 60,
    
    # BRT5(出入)
    ("車庫", "センター本通り"): 45, 
    ("センター本通り", "たちばな"): 45, 
    ("たちばな", "北詰"): 45,
    
    # BRT5
    ("北詰", "たちばな"): 45, 
    ("たちばな", "本通り"): 45, 
    ("本通り", "車庫"): 30, 
    ("車庫", "シャトル虹の原"): 30, 
    ("シャトル虹の原", "中央"): 15, 
    ("中央", "中央坂下"): 30, 
    ("中央坂下", "団地西"): 30, 
    ("団地西", "2丁目鶴巻通り"): 45, 
    ("2丁目鶴巻通り", "吉田クリニック"): 45, 
    ("吉田クリニック", "運動公園"): 45, 
    ("運動公園", "北吉浪"): 90,
    
    # 霞01
    ("月見原", "波平入口"): 45, 
    ("波平入口", "団地西"): 60, 
    ("団地西", "虹の原中央"): 60, 
    ("虹の原中央", "あおなみセンター"): 60, 
    ("あおなみセンター", "夢が丘6丁目"): 45, 
    ("夢が丘6丁目", "つばき産業道路"): 75
}

def get_segment_time(u, v):
    if (u, v) in SEGMENT_TIMES: return SEGMENT_TIMES[(u, v)]
    if (v, u) in SEGMENT_TIMES: return SEGMENT_TIMES[(v, u)]
    return None

# ==========================================
# ダイヤ計算ロジック・共通関数
# ==========================================
def round_time(dt):
    if dt.second == 0 or dt.second == 30:
        return dt.replace(microsecond=0)
    if dt.second < 30:
        return dt.replace(second=30, microsecond=0)
    return (dt + timedelta(seconds=60 - dt.second)).replace(second=0, microsecond=0)

def generate_formatted_timetable(route_name, start_station, end_station, start_time):
    if route_name not in ROUTE_STATIONS: return None, f"「{route_name}」は未実装の路線です"
    stations = ROUTE_STATIONS[route_name]

    if start_station not in stations: return None, f"開始停留所「{start_station}」は路線「{route_name}」に存在しません"
    if end_station not in stations: return None, f"終了停留所「{end_station}」は路線「{route_name}」に存在しません"

    # 環状線の1周判定
    if start_station == end_station:
        if stations[0] == stations[-1]:
            idx = stations.index(start_station)
            path = stations[idx:] + stations[1:idx+1]
        else:
            return None, "この路線は環状線ではないため、同じ停留所への運行はできません"
    else:
        start_idx = stations.index(start_station)
        end_idx = stations.index(end_station)
        if start_idx <= end_idx:
            path = stations[start_idx:end_idx + 1]
        else:
            path = list(reversed(stations[end_idx:start_idx + 1]))

    try:
        current = datetime.strptime(start_time, "%H:%M").replace(second=0, microsecond=0)
    except ValueError:
        return None, "開始時間の形式は HH:MM です"

    lines = []
    lines.append(f"{path[0]} {current.strftime('%H:%M:%S')}発")

    for index in range(1, len(path)):
        prev_station = path[index - 1]
        station = path[index]
        travel_time = get_segment_time(prev_station, station)
        if travel_time is None: return None, f"「{prev_station} ➔ {station}」のルート情報（所要時間）がありません"

        current += timedelta(seconds=travel_time)
        arrival = round_time(current)

        if station == path[-1] and index == len(path) - 1:
            lines.append(f"{station} {arrival.strftime('%H:%M:%S')}着")
            current = arrival
        else:
            departure = arrival + timedelta(seconds=STOP_TIME)
            lines.append(f"{station} {arrival.strftime('%H:%M:%S')}着 {departure.strftime('%H:%M:%S')}発")
            current = departure

    return lines, None

def build_station_path(route_name, start_station, end_station):
    if route_name not in ROUTE_STATIONS: return None, "未実装の路線です"
    stations = ROUTE_STATIONS[route_name]
    if start_station not in stations: return None, "開始停留所が存在しません"
    if end_station not in stations: return None, "終了停留所が存在しません"

    if start_station == end_station:
        if stations[0] == stations[-1]:
            idx = stations.index(start_station)
            return stations[idx:] + stations[1:idx+1], None
        return [start_station], None

    s = stations.index(start_station)
    e = stations.index(end_station)
    if s <= e: return stations[s:e + 1], None
    return list(reversed(stations[e:s + 1])), None

def generate_auto_timetable(route_name, start_station, end_station, start_time, end_time, count):
    if count < 1: return None, "本数は1以上です"
    if route_name not in ROUTE_STATIONS: return None, f"「{route_name}」は未実装の路線です"

    station_path, error = build_station_path(route_name, start_station, end_station)
    if error: return None, error

    try:
        start_dt = datetime.strptime(start_time, "%H:%M")
        end_dt = datetime.strptime(end_time, "%H:%M")
    except ValueError:
        return None, "時刻は HH:MM"

    start_min = start_dt.hour * 60 + start_dt.minute
    end_min = end_dt.hour * 60 + end_dt.minute
    if end_min < start_min: end_min += 24 * 60

    departures = []
    trains = []

    for _ in range(count):
        minute = random.randint(start_min, end_min)
        while any(abs(minute - x) < 2 for x in departures):
            minute += 2

        departures.append(minute)
        dep = (datetime(2000, 1, 1) + timedelta(minutes=minute)).strftime("%H:%M")

        timetable, error = generate_formatted_timetable(route_name, start_station, end_station, dep)
        if error: continue

        avoid = None
        candidates = [s for s in station_path[1:-1]]
        if candidates: avoid = random.choice(candidates)

        trains.append({
            "route": route_name, "departure": dep,
            "start": start_station, "end": end_station,
            "note": f"調整停留所: {avoid}" if avoid else "調整停留所:なし",
            "departure_minutes": minute, "timetable": timetable
        })

    trains.sort(key=lambda x: x["departure_minutes"])
    return trains, None

# ==========================================
# Discord スラッシュコマンド
# ==========================================
@bot.tree.command(name="create-auto", description="BRT自動ダイヤ作成")
async def create_auto(interaction: discord.Interaction, 路線: str, 開始駅: str, 終了駅: str, 開始時刻: str, 終了時刻: str, 本数: int):
    if not await check_command_permission(interaction, "create_auto"): return
    
    results, error = generate_auto_timetable(路線, 開始駅, 終了駅, 開始時刻, 終了時刻, 本数)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return

    lines = [f"【自動ダイヤ】{路線} {開始駅}→{終了駅}"]
    for idx, train in enumerate(results, 1):
        lines.append(f"便番号{idx}: {train['departure']}発")
        lines.append(f"  {train['note']}")
        lines.extend(f"  {line}" for line in train["timetable"])
        lines.append("")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@bot.tree.command(name="create", description="BRTダイヤ作成")
async def create(interaction: discord.Interaction, 路線: str, 開始駅: str, 終了駅: str, 開始時間: str = None):
    if not await check_command_permission(interaction, "create"): return

    if not 開始時間:
        await interaction.response.send_message("開始時間の形式は HH:MM です。", ephemeral=True)
        return

    lines, error = generate_formatted_timetable(路線, 開始駅, 終了駅, 開始時間)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return

    output = [f"【{路線} ダイヤ: {開始駅} ➔ {終了駅}】"]
    output.extend(lines)
    await interaction.response.send_message("\n".join(output))

# ==========================================
# システム起動処理
# ==========================================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} でログインしました")

def start_web_server():
    port = int(os.environ.get("PORT", "5000"))
    print(f"Starting Flask on port {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    print("Main started")

    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    print("Web thread started")

    if TOKEN:
        bot.run(TOKEN)
    else:
        print("DISCORD_TOKEN が設定されていません")