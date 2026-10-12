import os
import discord
from discord.ext import commands
from discord import app_commands

# メモリ上でのデータ保存用 ({ "選挙名": { voter_id: candidate_id } })
elections_data = {}

intents = discord.Intents.default()
intents.members = True          # メンバー情報取得用
intents.message_content = True

class ElectionBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        # スラッシュコマンドをDiscordに同期する
        await self.tree.sync()
        print("Slash commands synced.")

bot = ElectionBot()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")

# --- 投票用UIセレクトメニュー ---
class VoteSelect(discord.ui.Select):
    def __init__(self, election_name: str, candidates: list):
        self.election_name = election_name
        options = [
            discord.SelectOption(label=c.display_name, value=str(c.id), description=f"@{c.name}")
            for c in candidates[:25]
        ]
        super().__init__(placeholder="🗳️ 投票する候補者を選択してください", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        voter_id = interaction.user.id
        candidate_id = int(self.values[0])
        candidate_member = interaction.guild.get_member(candidate_id)

        if self.election_name not in elections_data:
            elections_data[self.election_name] = {}

        # 1人1票制限のチェック
        if voter_id in elections_data[self.election_name]:
            await interaction.response.send_message(
                "⚠️ **すでに投票済みです！** 重複投票はできません。", 
                ephemeral=True
            )
            return

        # メモリ上に記録
        elections_data[self.election_name][voter_id] = candidate_id

        await interaction.response.send_message(
            f"✅ **{candidate_member.display_name}** さんに投票を完了しました！", 
            ephemeral=True
        )

class VoteView(discord.ui.View):
    def __init__(self, election_name: str, candidates: list):
        super().__init__(timeout=None)
        self.add_item(VoteSelect(election_name, candidates))

# --- 1. 立候補コマンド（一般ユーザー向け） ---
@bot.tree.command(name="apply", description="指定した立候補ロールを自分に付与して立候補します")
@app_commands.describe(role="付与する立候補者のロール")
async def apply(interaction: discord.Interaction, role: discord.Role):
    try:
        await interaction.user.add_roles(role)
        await interaction.response.send_message(
            f"✅ {interaction.user.mention} さんに **{role.name}** ロールを付与し、立候補を受け付けました！", 
            ephemeral=True
        )
    except discord.Forbidden:
        await interaction.response.send_message("❌ Botにロールを付与する権限（ロールの管理）がありません。", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ エラーが発生しました: {e}", ephemeral=True)

# --- 2. 選挙開始コマンド（管理者向け） ---
@bot.tree.command(name="election", description="モデレーター選挙を開始し、投票パネルを設置します")
@app_commands.describe(election_name="選挙の名前", role="立候補者のロール")
@app_commands.checks.has_permissions(administrator=True)
async def election(interaction: discord.Interaction, election_name: str, role: discord.Role):
    candidates = [member for member in role.members]
    
    if not candidates:
        await interaction.response.send_message("❌ 指定されたロールを持つ立候補者が見つかりませんでした。", ephemeral=True)
        return

    if election_name not in elections_data:
        elections_data[election_name] = {}

    embed = discord.Embed(
        title=f"🗳️ モデレーター選挙: {election_name}",
        description="以下の立候補者一覧を確認し、下のメニューから投票してください。\n*(※投票は1人1回まで・匿名です)*",
        color=discord.Color.blue()
    )
    
    candidate_list = "\n".join([f"・ {c.mention}" for c in candidates])
    embed.add_field(name="立候補者一覧", value=candidate_list, inline=False)
    embed.set_footer(text=f"主催: {interaction.user.display_name}")

    view = VoteView(election_name, candidates)
    
    await interaction.response.send_message(f"選挙「{election_name}」の投票パネルを作成しました！", ephemeral=True)
    await interaction.channel.send(embed=embed, view=view)

# --- 3. 開票・集計コマンド（管理者向け） ---
@bot.tree.command(name="results", description="選挙の開票結果を集計して表示します")
@app_commands.describe(election_name="集計する選挙の名前")
@app_commands.checks.has_permissions(administrator=True)
async def results(interaction: discord.Interaction, election_name: str):
    if election_name not in elections_data or not elections_data[election_name]:
        await interaction.response.send_message(f"❌ 選挙「{election_name}」の投票データが存在しないか、まだ0票です。", ephemeral=True)
        return

    votes = elections_data[election_name]
    candidate_counts = {}
    for candidate_id in votes.values():
        candidate_counts[candidate_id] = candidate_counts.get(candidate_id, 0) + 1

    sorted_results = sorted(candidate_counts.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title=f"📊 開票結果: {election_name}",
        color=discord.Color.green()
    )

    result_text = ""
    for rank, (candidate_id, count) in enumerate(sorted_results, start=1):
        member = interaction.guild.get_member(candidate_id)
        name = member.display_name if member else f"ID: {candidate_id}"
        result_text += f"**{rank}位**: {name} - **{count}票**\n"

    embed.add_field(name="集計結果", value=result_text, inline=False)
    await interaction.response.send_message(embed=embed)

# 権限エラーのハンドリング
@results.error
async def results_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ このコマンドを実行する権限がありません（管理者限定）。", ephemeral=True)

@election.error
async def election_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.errors.MissingPermissions):
        await interaction.response.send_message("❌ このコマンドを実行する権限がありません（管理者限定）。", ephemeral=True)

bot.run(os.getenv("DISCORD_TOKEN"))
