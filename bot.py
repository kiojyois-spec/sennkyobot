import os
import discord
from discord.ext import commands

# --- メモリ上でのデータ保存用辞書 ---
# 構造: { "選挙名": { voter_id: candidate_id } }
elections_data = {}

# --- Discord Bot設定 ---
intents = discord.Intents.default()
intents.members = True          # メンバー情報取得用
intents.message_content = True

bot = commands.Bot(command_prefix="/", intents=intents)

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

        # 選挙データの初期化（念のため）
        if self.election_name not in elections_data:
            elections_data[self.election_name] = {}

        # 1人1票制限のチェック
        if voter_id in elections_data[self.election_name]:
            await interaction.response.send_message(
                "⚠️ **すでに投票済みです！** 重複投票はできません。", 
                ephemeral=True
            )
            return

        # メモリ上に投票データを記録
        elections_data[self.election_name][voter_id] = candidate_id

        await interaction.response.send_message(
            f"✅ **{candidate_member.display_name}** さんに投票を完了しました！", 
            ephemeral=True
        )

class VoteView(discord.ui.View):
    def __init__(self, election_name: str, candidates: list):
        super().__init__(timeout=None)
        self.add_item(VoteSelect(election_name, candidates))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user.name}")

# --- 1. 立候補コマンド（一般ユーザー向け） ---
@bot.command(name="apply")
async def apply(ctx, role: discord.Role):
    """
    使用例: /apply @立候補者
    実行したユーザーに指定したロールを付与します。
    """
    try:
        await ctx.author.add_roles(role)
        await ctx.send(f"✅ {ctx.author.mention} さんに **{role.name}** ロールを付与し、立候補を受け付けました！", delete_after=10)
        try:
            await ctx.message.delete()
        except:
            pass
    except discord.Forbidden:
        await ctx.send("❌ Botにロールを付与する権限（ロールの管理）がありません。", delete_after=10)
    except Exception as e:
        await ctx.send(f"❌ エラーが発生しました: {e}", delete_after=10)

# --- 2. 選挙開始コマンド（管理者向け） ---
@bot.command(name="election")
@commands.has_permissions(administrator=True)
async def election(ctx, election_name: str, role: discord.Role):
    """
    使用例: /election "第1回モデレーター選挙" @立候補者
    """
    candidates = [member for member in role.members]
    
    if not candidates:
        await ctx.send("❌ 指定されたロールを持つ立候補者が見つかりませんでした。")
        return

    # 選挙データの初期領域を準備
    if election_name not in elections_data:
        elections_data[election_name] = {}

    embed = discord.Embed(
        title=f"🗳️ モデレーター選挙: {election_name}",
        description="以下の立候補者一覧を確認し、下のメニューから投票してください。\n*(※投票は1人1回まで・匿名です)*",
        color=discord.Color.blue()
    )
    
    candidate_list = "\n".join([f"・ {c.mention}" for c in candidates])
    embed.add_field(name="立候補者一覧", value=candidate_list, inline=False)
    embed.set_footer(text=f"主催: {ctx.author.display_name}")

    view = VoteView(election_name, candidates)
    await ctx.send(embed=embed, view=view)

# --- 3. 開票・集計コマンド（管理者向け） ---
@bot.command(name="results")
@commands.has_permissions(administrator=True)
async def results(ctx, election_name: str):
    """
    使用例: /results "第1回モデレーター選挙"
    """
    if election_name not in elections_data or not elections_data[election_name]:
        await ctx.send(f"❌ 選挙「{election_name}」の投票データが存在しないか、まだ0票です。")
        return

    # メモリ上のデータから各候補者の得票数を集計
    votes = elections_data[election_name]
    candidate_counts = {}
    for candidate_id in votes.values():
        candidate_counts[candidate_id] = candidate_counts.get(candidate_id, 0) + 1

    # 得票数順（降順）にソート
    sorted_results = sorted(candidate_counts.items(), key=lambda x: x[1], reverse=True)

    embed = discord.Embed(
        title=f"📊 開票結果: {election_name}",
        color=discord.Color.green()
    )

    result_text = ""
    for rank, (candidate_id, count) in enumerate(sorted_results, start=1):
        member = ctx.guild.get_member(candidate_id)
        name = member.display_name if member else f"ID: {candidate_id}"
        result_text += f"**{rank}位**: {name} - **{count}票**\n"

    embed.add_field(name="集計結果", value=result_text, inline=False)
    await ctx.send(embed=embed)

bot.run(os.getenv("DISCORD_TOKEN"))
