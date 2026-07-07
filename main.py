import os
from datetime import datetime, timedelta
import discord
from discord import app_commands
from discord.ext import commands
from flask import Flask
from threading import Thread

# ==========================================
# 1. Render用 Webサーバー
# ==========================================
app = Flask("")
@app.route("/")
def home(): return "Dia Bot is running!"

def run():
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)

def keep_alive():
    Thread(target=run).start()

# ==========================================
# 2. Discord BOT & スラッシュコマンド設定
# ==========================================
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        await self.tree.sync()

bot = MyBot()

# ❌ 権限エラーが発生したときの処理
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingAnyRole):
        await interaction.response.send_message("⚠️ このコマンドを実行する権限（必要なロール）がありません！", ephemeral=True)
    else:
        await interaction.response.send_message(f"❌ エラーが発生しました: {error}", ephemeral=True)

# ==========================================
# 3. 駅・路線データの定義
# ==========================================
NETWORK = {
    "あおなみセンター": {"虹の原中央": (45, "BRT1"), "三叉路": (60, "虹02")},
    "虹の原中央": {"あおなみセンター": (60, "霞01"), "鶴巻団地": (60, "BRT1"), "中央坂下": (45, "虹02"), "シャトル虹の原": (15, "BRT5"), "団地西": (60, "霞01")},
    "鶴巻団地": {"虹の原中央": (60, "BRT1"), "月見原": (45, "BRT1")},
    "月見原": {"鶴巻団地": (45, "BRT1"), "運動公園": (45, "BRT1"), "波平入口": (45, "霞01")},
    "運動公園": {"月見原": (45, "BRT1"), "春町公園": (45, "BRT1"), "吉田クリニック": (45, "BRT5"), "北吉浪": (90, "BRT5")},
    "春町公園": {"運動公園": (45, "BRT1"), "あけぼの": (45, "BRT1"), "灯": (60, "BRT2")},
    "あけぼの": {"春町公園": (45, "BRT1"), "虹の原中央": (60, "BRT1")},
    "灯": {"春町公園": (60, "BRT2"), "北吉浪": (60, "BRT2")},
    "北吉浪": {"灯": (60, "BRT2"), "本吉浪": (75, "BRT2"), "吉浪各務原": (105, "BRT2-3"), "運動公園": (90, "BRT5")},
    "本吉浪": {"北吉浪": (75, "BRT2"), "吉浪本町": (60, "BRT2"), "本町": (60, "BRT2-3")},
    "吉浪本町": {"本吉浪": (60, "BRT2")},
    "本町": {"本吉浪": (60, "BRT2-3")},
    "吉浪各務原": {"北吉浪": (105, "BRT2-3"), "BRT海老塚": (45, "BRT2-3")},
    "BRT海老塚": {"吉浪各務原": (45, "BRT2-3"), "団地西": (60, "BRT2-3")},
    "団地西": {"BRT海老塚": (60, "BRT2-3"), "総合病院": (60, "BRT2-3"), "中央坂下": (30, "虹02"), "本新宿": (60, "虹02"), "2丁目鶴巻通り": (45, "BRT5"), "波平入口": (60, "霞01"), "虹の原中央": (60, "霞01")},
    "総合病院": {"団地西": (60, "BRT2-3")},
    "中央坂下": {"虹の原中央": (45, "虹02"), "団地西": (30, "虹02")},
    "本新宿": {"団地西": (60, "虹02"), "公民館前": (45, "虹02")},
    "公民館前": {"本新宿": (45, "虹02"), "三叉路": (45, "虹02")},
    "三叉路": {"公民館前": (45, "虹02"), "あおなみセンター": (60, "虹02")},
    "車庫": {"センター本通り": (45, "BRT5(出入)"), "本通り": (30, "BRT5"), "シャトル虹の原": (30, "BRT5")},
    "センター本通り": {"車庫": (45, "BRT5(出入)"), "たちばな": (45, "BRT5(出入)")},
    "たちばな": {"センター本通り": (45, "BRT5(出入)"), "北詰": (45, "BRT5(出入)"), "本通り": (45, "BRT5")},
    "北詰": {"たちばな": (45, "BRT5")},
    "本通り": {"たちばな": (45, "BRT5"), "車庫": (30, "BRT5")},
    "シャトル虹の原": {"車庫": (30, "BRT5"), "虹の原中央": (15, "BRT5")},
    "2丁目鶴巻通り": {"団地西": (45, "BRT5"), "吉田クリニック": (45, "BRT5")},
    "吉田クリニック": {"2丁目鶴巻通り": (45, "BRT5"), "運動公園": (45, "BRT5")},
    "波平入口": {"月見原": (45, "霞01"), "団地西": (60, "霞01")},
    "夢ヶ丘6丁目": {"あおなみセンター": (45, "霞01"), "つばき産業道路": (75, "霞01")},
    "つばき産業道路": {"夢ヶ丘6丁目": (75, "霞01")}
}

# ==========================================
# 4. ダイヤ計算共通ロジック
# ==========================================
def find_route(start, end, via=None):
    queue = [[start]]
    visited = set()
    possible_routes = []
    while queue:
        path = queue.pop(0)
        node = path[-1]
        if node == end:
            possible_routes.append(path)
            continue
        if node not in visited:
            visited.add(node)
            for neighbor in NETWORK.get(node, {}).keys():
                if neighbor not in path:
                    new_path = list(path)
                    new_path.append(neighbor)
                    queue.append(new_path)
    if via:
        for p in possible_routes:
            if via in p: return p
    if possible_routes: return possible_routes[0]
    return None

def calculate_dia(start, end, start_time_str, via=None):
    route = find_route(start, end, via)
    if not route: return f"❌ 「{start}」から「{end}」への経路が見つかりません。駅名や経由地を確認してください。"
    current_time = datetime.strptime(start_time_str, "%H:%M:%S")
    result = f"```\n運行ダイヤ ({start} ➔ {end})\n"
    for i, station in enumerate(route):
        if i == 0:
            result += f"{station:<14} {current_time.strftime('%H:%M:%S')} 発\n"
        else:
            prev_station = route[i-1]
            seconds_to_add, _ = NETWORK[prev_station][station]
            current_time += timedelta(seconds=seconds_to_add)
            if i == len(route) - 1:
                result += f"{station:<14} {current_time.strftime('%H:%M:%S')} 着\n"
            else:
                arr_time = current_time
                current_time += timedelta(seconds=15)
                result += f"{station:<14} {arr_time.strftime('%H:%M:%S')} 着  {current_time.strftime('%H:%M:%S')} 発\n"
    result += "```"
    return result

# ==========================================
# 5. /create コマンド (通常1車両分)
# ==========================================
@bot.tree.command(name="create", description="1車両分のダイヤを作成します（直通・経由対応）")
@app_commands.describe(start="出発地", end="終点", start_time="発車時間", via="経由地（任意）")
# ⚠️ 【create用】を使わせたい役職のロールID（数字）に書き換えてね！
@app_commands.checks.has_any_role(1510021467167789104) 
async def create_cmd(interaction: discord.Interaction, start: str, end: str, start_time: str, via: str = None):
    await interaction.response.defer()
    try:
        output = calculate_dia(start, end, start_time, via)
        await interaction.followup.send(output)
    except Exception:
        await interaction.followup.send(f"❌ エラーが発生しました。入力形式を確認してください。")

# ==========================================
# 6. /create-man コマンド (複数編成フォーム対応)
# ==========================================
class TrainForm(discord.ui.Modal):
    def __init__(self, index, total):
        super().__init__(title=f"【{index}/{total}編成目】ダイヤ入力フォーム")
        self.start_input = discord.ui.TextInput(label="出発地", placeholder="例: あおなみセンター", required=True)
        self.end_input = discord.ui.TextInput(label="終点", placeholder="例: 吉浪本町", required=True)
        self.time_input = discord.ui.TextInput(label="発車時間", placeholder="例: 10:00:00", required=True)
        self.via_input = discord.ui.TextInput(label="経由地（ない場合は空欄）", required=False)
        self.add_item(self.start_input)
        self.add_item(self.end_input)
        self.add_item(self.time_input)
        self.add_item(self.via_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        self.data = {"start": self.start_input.value, "end": self.end_input.value, "time": self.time_input.value, "via": self.via_input.value if self.via_input.value else None}
        self.stop()

class FormView(discord.ui.View):
    def __init__(self, interaction, count):
        super().__init__(timeout=600)
        self.orig_interaction = interaction
        self.count = count
        self.current = 1
        self.results = []

    async def start_session(self):
        embed = discord.Embed(title="マルチダイヤ作成", description=f"1〜{self.count}編成分の入力を開始します。")
        button = discord.ui.Button(label="1編成目を入力", style=discord.ButtonStyle.primary)
        button.callback = self.on_button_click
        self.add_item(button)
        await self.orig_interaction.followup.send(embed=embed, view=self)

    async def on_button_click(self, interaction: discord.Interaction):
        modal = TrainForm(self.current, self.count)
        await interaction.response.send_modal(modal)
        await modal.wait()
        if hasattr(modal, 'data'):
            self.results.append(modal.data)
            self.current += 1
            if self.current <= self.count:
                self.clear_items()
                next_button = discord.ui.Button(label=f"{self.current}編成目を入力", style=discord.ButtonStyle.primary)
                next_button.callback = self.on_button_click
                self.add_item(next_button)
                await interaction.followup.edit_message(message_id=(await interaction.original_response()).id, view=self)
            else:
                self.clear_items()
                await interaction.followup.edit_message(message_id=(await interaction.original_response()).id, content="🎉 全編成の入力が完了しました！ダイヤを出力します。", view=None)
                for idx, t_data in enumerate(self.results, 1):
                    dia_output = calculate_dia(t_data["start"], t_data["end"], t_data["time"], t_data["via"])
                    await interaction.followup.send(f"🚉 **【第 {idx} 編成】**\n{dia_output}")
                self.stop()

@bot.tree.command(name="create-man", description="複数編成のダイヤをフォーム形式で一枠ずつ作成します")
@app_commands.describe(train_count="作成する編成数 (1-10)")
@app_commands.choices(train_count=[app_commands.Choice(name=str(i), value=i) for i in range(1, 11)])
# ⚠️ 【create-man用】を使わせたい役職のロールID（数字）に書き換えてね！（createとは別のIDにできます）
@app_commands.checks.has_any_role(1510021467167789104)
async def create_man_cmd(interaction: discord.Interaction, train_count: int):
    await interaction.response.defer()
    view = FormView(interaction, train_count)
    await view.start_session()

# ==========================================
# 7. BOTの起動
# ==========================================
keep_alive()
TOKEN = os.environ.get("DISCORD_TOKEN")
if TOKEN:
    bot.run(TOKEN)
else:
    print("エラー: DISCORD_TOKENが設定されていません。")