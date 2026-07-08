from datetime import datetime, timedelta
import json
import os
import random
import threading
import time
import heapq
from flask import Flask
import discord
from discord.ext import commands
from discord import app_commands

# ==========================================
# Flask & Discord Bot 初期化
# ==========================================
TOKEN = os.getenv("DISCORD_TOKEN")
app = Flask(__name__)

@app.route("/")
def health():
    return "BRT Bot is running"

intents = discord.Intents.default()
intents.members = True
bot = commands.Bot(command_prefix="/", intents=intents)

# ==========================================
# JSON 永続化データ管理
# ==========================================
USAGE_FILE = "brt_usage.json"

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

COMMAND_RULES = {
    "create": {
        "unlimited_roles": [1511882841997185064],
        "limited_roles": [1510021467155202057],
        "window_sec": 12 * 3600,
        "limit": 4
    },
    "create_emp": {
        "unlimited_roles": [1510405214811852900],
        "limited_roles": [1510021467167789097, 1511882841997185064],
        "window_sec": 24 * 3600,
        "limit": 5
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
# 統合された全区間ネットワークデータ (双方向対応)
# ==========================================
STOP_TIME = 15  # 停車時間（秒）

RAW_SEGMENTS = [
    # BRT1 (虹の原中央を起点とする環状線)
    ("虹の原中央", "団地", 45), ("団地", "月見原", 45), ("月見原", "あけぼの", 45), ("あけぼの", "虹の原中央", 45),
    ("団地", "中央", 60), ("中央", "センター", 45), ("運動公園", "春巻公園", 45), ("春巻公園", "運動公園", 45),
    # BRT2
    ("あけぼon", "春町公園", 45), ("春町公園", "灯", 60), ("灯", "北吉浪", 60), ("北吉浪", "本吉浪", 75), ("本吉浪", "本町", 60),
    # BRT2-3
    ("本町", "本吉浪", 60), ("本吉浪", "北吉浪", 75), ("北吉浪", "吉浪各務原", 105), ("吉浪各務原", "BRT海老塚", 45), ("BRT海老塚", "団地西", 60), ("団地西", "病院", 60),
    # 虹2 (あおなみを出たら虹の原中央を経由する環状線)
    ("あおなみ", "虹の原中央", 30), ("虹の原中央", "中央", 45), ("中央", "中央坂下", 45), ("中央坂下", "団地西", 30), 
    ("団地西", "本新宿", 60), ("本新宿", "公民館前", 45), ("公民館前", "三叉路", 45), ("三叉路", "あおなみ", 60),
    # BRT5(出入)
    ("車庫", "センター本通り", 45), ("センター本通り", "たちばな", 45), ("たちばな", "北詰", 45),
    # BRT5
    ("北詰", "たちばな", 45), ("たちばな", "本通り", 45), ("本通り", "車庫", 30), ("車庫", "シャトル虹の原", 30), ("シャトル虹の原", "中央", 15), ("中央", "中央坂下", 30), ("中央坂下", "団地西", 30), ("団地西", "2丁目鶴巻通り", 45), ("2丁目鶴巻通り", "吉田クリニック", 45), ("吉田クリニック", "運動公園", 45), ("運動公園", "北吉浪", 90),
    # 霞01
    ("月見原", "波平入口", 45), ("波平入口", "団地西", 60), ("団地西", "中央", 60), ("中央", "あおなみ", 60), ("あおなみ", "夢丘6丁", 45), ("夢丘6丁", "つばき産道", 75)
]

# 隣接リストの構築
NETWORK = {}
for u, v, t in RAW_SEGMENTS:
    NETWORK.setdefault(u, {})[v] = t
    NETWORK.setdefault(v, {})[u] = t

# ==========================================
# 経路探索 (ダイクストラ法) & 運行計算ロジック
# ==========================================
def find_shortest_path(start, end):
    if start not in NETWORK or end not in NETWORK:
        return None
    
    if start == end:
        shortest_full_path = None
        min_cost = float('inf')
        for neighbor, time_cost in NETWORK[start].items():
            queue = [(time_cost, neighbor, [start, neighbor])]
            seen = {start}
            while queue:
                cost, node, path = heapq.heappop(queue)
                if node == end:
                    if cost < min_cost:
                        min_cost = cost
                        shortest_full_path = path
                    break
                if node not in seen:
                    seen.add(node)
                    for nxt, t_c in NETWORK[node].items():
                        if nxt not in seen or (nxt == end and len(path) > 2):
                            heapq.heappush(queue, (cost + t_c, nxt, path + [nxt]))
        return shortest_full_path

    queue = [(0, start, [])]
    seen = set()
    while queue:
        (cost, node, path) = heapq.heappop(queue)
        if node not in seen:
            seen.add(node)
            path = path + [node]
            if node == end:
                return path
            for next_node, time_cost in NETWORK[node].items():
                if next_node not in seen:
                    heapq.heappush(queue, (cost + time_cost, next_node, path))
    return None

def round_up_to_30_seconds(dt: datetime) -> datetime:
    if dt.second == 0 or dt.second == 30:
        return dt.replace(microsecond=0)
    if dt.second < 30:
        return dt.replace(second=30, microsecond=0)
    return (dt + timedelta(seconds=60 - dt.second)).replace(second=0, microsecond=0)

def generate_formatted_timetable(start_station, end_station, start_time):
    path = find_shortest_path(start_station, end_station)
    if not path:
        return None, "指定された停留所間でルートを繋ぐことができませんでした"

    try:
        current = datetime.strptime(start_time, "%H:%M").replace(second=0, microsecond=0)
    except ValueError:
        return None, "時刻の形式は HH:MM で入力してください"

    lines = []
    lines.append(f"{path[0]} {current.strftime('%H:%M:%S')}発")

    for index in range(1, len(path)):
        prev_station = path[index - 1]
        station = path[index]
        travel_time = NETWORK[prev_station][station]

        current += timedelta(seconds=travel_time)
        arrival = round_up_to_30_seconds(current)

        if station == path[-1] and index == len(path) - 1:
            lines.append(f"{station} {arrival.strftime('%H:%M:%S')}着")
            current = arrival
        else:
            departure = arrival + timedelta(seconds=STOP_TIME)
            lines.append(f"{station} {arrival.strftime('%H:%M:%S')}着 {departure.strftime('%H:%M:%S')}発")
            current = departure

    return lines, None

def generate_auto_timetable(start_station, end_station, start_time, end_time, count):
    if count < 1: return None, "運行本数は1以上で指定してください"
    if start_station not in NETWORK or end_station not in NETWORK: return None, "指定された停留所が存在しません"

    try:
        start_dt = datetime.strptime(start_time, "%H:%M")
        end_dt = datetime.strptime(end_time, "%H:%M")
    except ValueError:
        return None, "時刻形式は HH:MM です"

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
        timetable, error = generate_formatted_timetable(start_station, end_station, dep)
        if error: continue

        trains.append({
            "departure": dep, "start": start_station, "end": end_station,
            "departure_minutes": minute, "timetable": timetable
        })

    trains.sort(key=lambda x: x["departure_minutes"])
    return trains, None

# ==========================================
# Discord スラッシュコマンド & モーダル UI
# ==========================================
class NextCompositionView(discord.ui.View):
    def __init__(self, composition_index: int, total_compositions: int, all_trains_data: list, callback=None):
        super().__init__()
        self.composition_index = composition_index
        self.total_compositions = total_compositions
        self.all_trains_data = all_trains_data
        self.callback = callback

    @discord.ui.button(label="次の車両設定へ", style=discord.ButtonStyle.primary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TrainInfoModal(self.composition_index + 1, self.total_compositions, self.all_trains_data, self.callback))

class TrainInfoModal(discord.ui.Modal):
    def __init__(self, composition_index: int, total_compositions: int, all_trains_data: list, callback=None):
        super().__init__(title=f"運用車両設定 {composition_index}/{total_compositions}")
        self.composition_index = composition_index
        self.total_compositions = total_compositions
        self.all_trains_data = all_trains_data
        self.callback = callback

    departure_time = discord.ui.TextInput(label="発車時刻", placeholder="HH:MM", required=True)
    start_station = discord.ui.TextInput(label="乗車停留所(起点)", required=True)
    end_station = discord.ui.TextInput(label="降車停留所(終点)", required=True)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        train_data = {
            "departure": str(self.departure_time), "start": str(self.start_station), "end": str(self.end_station)
        }
        self.all_trains_data.append(train_data)

        if self.composition_index < self.total_compositions:
            view = NextCompositionView(self.composition_index, self.total_compositions, self.all_trains_data, self.callback)
            await interaction.response.send_message(f"車両 {self.composition_index} の設定を記録しました。\n「次の車両設定へ」を押して次を入力してください。", view=view, ephemeral=True)
        else:
            await interaction.response.defer()
            if self.callback:
                await self.callback(interaction, self.all_trains_data)
            else:
                await interaction.followup.send(f"全 {self.composition_index} 台のBRT自由直通運用を記録しました。", ephemeral=True)

@bot.tree.command(name="brt-create-auto", description="BRT自動運行表生成（自由直通対応）")
async def brt_create_auto(interaction: discord.Interaction, 開始停留所: str, 終了停留所: str, 開始時刻: str, 終了時刻: str, 本数: int):
    if not await check_command_permission(interaction, "create_auto"): return
    results, error = generate_auto_timetable(開始停留所, 終了停留所, 開始時刻, 終了時刻, 本数)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return

    lines = [f"【BRT自由直通 自動運行ダイヤ】 {開始停留所} ➔ {終了停留所}"]
    for idx, train in enumerate(results, 1):
        lines.append(f"便番号{idx}: {train['departure']}発")
        lines.extend(f"  {line}" for line in train["timetable"])
        lines.append("")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)

@bot.tree.command(name="brt-create", description="BRT運行表作成（自由直通対応）")
async def brt_create(interaction: discord.Interaction, 開始停留所: str, 終了停留所: str, 開始時間: str):
    if not await check_command_permission(interaction, "create"): return
    lines, error = generate_formatted_timetable(開始停留所, 終了停留所, 開始時間)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return

    output = [f"【BRT自由直通系統: {開始停留所} ➔ {終了停留所}】"]
    output.extend(lines)
    await interaction.response.send_message("\n".join(output))

# 選択肢の設定をデコレータの最下層（関数の直上）に配置して修正
@app_commands.choices(
    車両数=[
        app_commands.Choice(name="1台", value=1), app_commands.Choice(name="2台", value=2),
        app_commands.Choice(name="3台", value=3), app_commands.Choice(name="4台", value=4),
        app_commands.Choice(name="5台", value=5)
    ]
)
@bot.tree.command(name="brt-create-emp", description="複数車両BRTダイヤ作成（フォーム自由入力）")
async def brt_create_emp(interaction: discord.Interaction, 車両数: int):
    if not await check_command_permission(interaction, "create_emp"): return

    async def generate_emp_timetable(interaction: discord.Interaction, all_trains_data: list):
        messages = []
        for idx, train_data in enumerate(all_trains_data, 1):
            departure = train_data["departure"]
            start_station = train_data["start"]
            end_station = train_data["end"]
            timetable, error = generate_formatted_timetable(start_station, end_station, departure)
            if error:
                messages.append(f"❌ 便{idx}: {error}")
            else:
                messages.append(f"✅ 便{idx}: 【直通】 {start_station} ➔ {end_station}")
                messages.extend(timetable)
                messages.append("")
        await interaction.followup.send("\n".join(messages), ephemeral=True)

    await interaction.response.send_modal(TrainInfoModal(1, 車両数, [], generate_emp_timetable))

# ==========================================
# システム起動処理
# ==========================================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"{bot.user} (BRT Mode - Real Loops Connected) でログインしました")

def start_web_server():
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)

if __name__ == "__main__":
    web_thread = threading.Thread(target=start_web_server, daemon=True)
    web_thread.start()
    if TOKEN:
        bot.run(TOKEN)