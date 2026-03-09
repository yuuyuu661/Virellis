# cogs/hotel/room_buttons.py
import discord
from datetime import timedelta, datetime
from discord.ui import Button, View, Modal, TextInput, Select


# =========================
# 共通：room/config取得 & 権限
# =========================
async def _get_room_and_config(interaction: discord.Interaction):
    vc = interaction.channel
    if not isinstance(vc, discord.VoiceChannel):
        return None, None, "❌ VCに紐づくテキスト欄で実行してください。"

    guild_id = str(interaction.guild.id)

    room = await interaction.client.db.get_room(str(vc.id))
    if not room:
        return None, None, "❌ このVCはホテルルームとして登録されていません。"

    # 🔥 conn → pool
    async with interaction.client.db.pool.acquire() as conn:
        config = await conn.fetchrow(
            "SELECT * FROM hotel_settings WHERE guild_id=$1",
            guild_id
        )

    if not config:
        return None, None, "❌ ホテル初期設定がありません。（/ホテル初期設定）"

    return room, config, None

def _has_room_permission(interaction: discord.Interaction, room, config) -> bool:
    # ① オーナー
    if str(interaction.user.id) == str(room["owner_id"]):
        return True

    # ② ホテル管理ロール（manager_role）
    try:
        manager_role_id = int(config["manager_role"])
    except Exception:
        return False

    role = interaction.guild.get_role(manager_role_id)
    return role is not None and role in interaction.user.roles


async def _require_room_permission(interaction: discord.Interaction):
    room, config, err = await _get_room_and_config(interaction)
    if err:
        await interaction.response.send_message(err, ephemeral=True)
        return None, None

    if not _has_room_permission(interaction, room, config):
        await interaction.response.send_message(
            "❌ このパネルを操作できるのは「チェックインした本人」と「ホテル管理人ロール」のみです。",
            ephemeral=True
        )
        return None, None

    return room, config


# ======================================================
# ① 人数制限 +1（1枚）※押した人のチケットを消費（現行通り）
# ======================================================
class RoomAddMemberLimitButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="人数 +1（1枚）",
            style=discord.ButtonStyle.green,
            custom_id="hotel_room_add_member_limit",
        )

    async def callback(self, interaction: discord.Interaction):
        room, config = await _require_room_permission(interaction)
        if room is None:
            return

        vc: discord.VoiceChannel = interaction.channel
        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        tickets = await interaction.client.db.get_tickets(user_id, guild_id)
        if tickets < 1:
            return await interaction.response.send_message("❌ チケット不足です。", ephemeral=True)

        await interaction.client.db.remove_tickets(user_id, guild_id, 1)

        new_limit = (vc.user_limit or 2) + 1
        await vc.edit(user_limit=new_limit)

        await interaction.response.send_message(
            f"👥 人数上限を **{new_limit}人** に増やしました。",
            ephemeral=True
        )


# ======================================================
# ② VC名変更（無料）
# ======================================================
class RoomRenameButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="VC名変更（無料）",
            style=discord.ButtonStyle.blurple,
            custom_id="hotel_room_rename",
        )

    async def callback(self, interaction: discord.Interaction):
        room, config = await _require_room_permission(interaction)
        if room is None:
            return

        class RenameModal(Modal, title="VC名変更"):
            new_name = TextInput(label="新しいVC名", max_length=50)

            async def on_submit(self, modal_interaction: discord.Interaction):
                vc = modal_interaction.channel
                if not isinstance(vc, discord.VoiceChannel):
                    return await modal_interaction.response.send_message(
                        "❌ VC内でのみ実行できます。",
                        ephemeral=True
                    )
                await vc.edit(name=self.new_name.value)
                await modal_interaction.response.send_message(
                    f"✏️ 名称変更 → **{self.new_name.value}**",
                    ephemeral=True
                )

        await interaction.response.send_modal(RenameModal())


# ======================================================
# ③ 接続許可ボタン（検索）
# ======================================================
class RoomAllowMemberButton(Button):
    def __init__(self):
        super().__init__(
            label="🔓 接続許可（検索）",
            style=discord.ButtonStyle.primary,
            custom_id="hotel_room_allow_member",
        )

    async def callback(self, interaction: discord.Interaction):
        room, config = await _require_room_permission(interaction)
        if room is None:
            return
        await interaction.response.send_modal(AllowMemberSearchModal())


class AllowMemberSearchModal(Modal, title="接続許可ユーザー検索"):
    keyword = TextInput(
        label="ユーザーID / 名前 / ニックネーム",
        style=discord.TextStyle.short,
        placeholder="例: 1010... / Yuu / ゆう",
        required=True
    )

    async def on_submit(self, interaction: discord.Interaction):
        room, config, err = await _get_room_and_config(interaction)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)

        if not _has_room_permission(interaction, room, config):
            return await interaction.response.send_message("❌ 権限がありません。", ephemeral=True)

        guild = interaction.guild
        query = self.keyword.value.strip()

        if query.startswith("<@") and query.endswith(">"):
            query = query.replace("<@", "").replace(">", "").replace("!", "")

        candidates = []

        if query.isdigit():
            m = guild.get_member(int(query))
            if m:
                candidates.append(m)

        q_lower = query.lower()
        for m in guild.members:
            if (q_lower in m.name.lower()) or (m.nick and q_lower in m.nick.lower()):
                candidates.append(m)

        candidates = list({m.id: m for m in candidates}.values())

        if not candidates:
            return await interaction.response.send_message("❌ 一致するユーザーが見つかりませんでした。", ephemeral=True)

        if len(candidates) == 1:
            return await allow_member_to_vc(interaction, candidates[0])

        view = AllowMemberSelectView(candidates)
        return await interaction.response.send_message(
            "複数候補が見つかりました。ユーザーを選択してください👇",
            view=view,
            ephemeral=True
        )


class AllowMemberSelectView(View):
    def __init__(self, members):
        super().__init__(timeout=20)
        self.add_item(AllowMemberSelect(members))


class AllowMemberSelect(Select):
    def __init__(self, members):
        options = [discord.SelectOption(label=m.display_name, value=str(m.id)) for m in members]
        super().__init__(placeholder="ユーザーを選択…", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        room, config, err = await _get_room_and_config(interaction)
        if err:
            return await interaction.response.send_message(err, ephemeral=True)

        if not _has_room_permission(interaction, room, config):
            return await interaction.response.send_message("❌ 権限がありません。", ephemeral=True)

        member_id = int(self.values[0])
        member = interaction.guild.get_member(member_id)
        if not member:
            return await interaction.response.send_message("❌ そのユーザーは見つかりません。", ephemeral=True)

        await interaction.response.defer(ephemeral=True)
        await add_member_to_vc(interaction, member)
        await interaction.followup.send(f"✅ **{member.display_name}** に接続許可を付与しました。", ephemeral=True)


async def add_member_to_vc(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    if not isinstance(channel, discord.VoiceChannel):
        raise TypeError("この操作は VC に紐づくテキストチャットでのみ実行できます。")

    ow = channel.overwrites_for(member)
    ow.view_channel = True
    ow.connect = True
    ow.speak = True
    ow.stream = True
    await channel.set_permissions(member, overwrite=ow, reason="高級ホテルVC 接続許可")


async def allow_member_to_vc(interaction: discord.Interaction, member: discord.Member):
    channel = interaction.channel
    if not isinstance(channel, discord.VoiceChannel):
        return await interaction.response.send_message(
            "❌ この操作は VC 内のテキスト欄で実行してください。",
            ephemeral=True
        )

    await channel.set_permissions(member, view_channel=True, connect=True)
    await interaction.response.send_message(
        f"✅ **{member.display_name}** に接続許可を付与しました。",
        ephemeral=True
    )


# ======================================================
# ④ 接続拒否（無料）
# ======================================================
class RoomDenyMemberButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="接続拒否（無料）",
            style=discord.ButtonStyle.gray,
            custom_id="hotel_room_deny_member",
        )

    async def callback(self, interaction: discord.Interaction):
        room, config = await _require_room_permission(interaction)
        if room is None:
            return

        vc: discord.VoiceChannel = interaction.channel

        owner_id = str(room["owner_id"])

        allowed = [
           m for m, perms in vc.overwrites.items()
           if (
               isinstance(m, discord.Member)
               and perms.view_channel
               and str(m.id) != owner_id      # オーナー除外
               and not m.bot                  # Bot除外
           )
       ]
        if not allowed:
            return await interaction.response.send_message(
                "⚠ 現在許可済みユーザーはいません。",
                ephemeral=True
            )

        class DenySelect(Select):
            def __init__(self):
                super().__init__(
                    placeholder="拒否するユーザーを選択",
                    min_values=1,
                    max_values=1,
                    options=[discord.SelectOption(label=m.display_name, value=str(m.id)) for m in allowed]
                )

            async def callback(self, select_interaction: discord.Interaction):
                target = vc.guild.get_member(int(self.values[0]))
                await vc.set_permissions(target, connect=False, view_channel=False)
                await select_interaction.response.send_message(
                    f"🚫 接続拒否 → {target.display_name}",
                    ephemeral=True
                )

        view = View()
        view.add_item(DenySelect())
        await interaction.response.send_message("拒否ユーザーを選択👇", view=view, ephemeral=True)


# ======================================================
# 延長（1/3/10日）※オーナーのチケットを消費（現行通り）
# ======================================================
class RoomAdd1DayButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="⏱ 1日延長（1枚）", style=discord.ButtonStyle.primary, custom_id="hotel_room_add_1d")

    async def callback(self, interaction: discord.Interaction):
        await _extend_days(interaction, need=1, days=1)


class RoomAdd3DayButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="⏱ 3日延長（3枚）", style=discord.ButtonStyle.primary, custom_id="hotel_room_add_3d")

    async def callback(self, interaction: discord.Interaction):
        await _extend_days(interaction, need=3, days=3)


class RoomAdd10DayButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="⏱ 10日延長（10枚）", style=discord.ButtonStyle.primary, custom_id="hotel_room_add_10d")

    async def callback(self, interaction: discord.Interaction):
        await _extend_days(interaction, need=10, days=10)


async def _extend_days(interaction: discord.Interaction, need: int, days: int):
    room, config = await _require_room_permission(interaction)
    if room is None:
        return

    vc: discord.VoiceChannel = interaction.channel
    guild_id = str(interaction.guild.id)
    owner_id = str(room["owner_id"])

    tickets = await interaction.client.db.get_tickets(owner_id, guild_id)
    if tickets < need:
        return await interaction.response.send_message(
            f"❌ チケットが不足しています。（{need}枚必要）",
            ephemeral=True
        )

    await interaction.client.db.remove_tickets(owner_id, guild_id, need)

    new_expire = room["expire_at"] + timedelta(days=days)
    await interaction.client.db.save_room(str(vc.id), guild_id, owner_id, new_expire)

    await interaction.response.send_message(
        f"⏱ **{days}日延長しました。**\n新しい削除予定：<t:{int(new_expire.timestamp())}:F>",
        ephemeral=True
    )

    await send_extend_log(interaction, vc, days=days, new_expire=new_expire)


async def send_extend_log(interaction, vc, days, new_expire):
    guild_id = str(interaction.guild.id)

    # 🔥 conn → pool
    async with interaction.client.db.pool.acquire() as conn:
        config = await conn.fetchrow(
            "SELECT * FROM hotel_settings WHERE guild_id=$1",
            guild_id
        )

    if not config:
        return

    log_channel = interaction.guild.get_channel(int(config["log_channel"]))
    if not log_channel:
        return

    embed = discord.Embed(
        title="⏱ ホテル延長ログ",
        color=0x3498DB,
        timestamp=datetime.utcnow()
    )
    embed.add_field(name="実行者", value=interaction.user.mention, inline=False)
    embed.add_field(name="延長日数", value=f"{days} 日", inline=True)
    embed.add_field(name="VC 名", value=vc.name, inline=True)
    embed.add_field(name="VC ID", value=str(vc.id), inline=False)
    embed.add_field(name="新しい削除予定", value=f"<t:{int(new_expire.timestamp())}:F>", inline=False)

    await log_channel.send(embed=embed)

# ======================================================
# サブ垢追加（現行の挙動を維持）
# ======================================================
class RoomAddSubRoleButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="サブ垢追加", style=discord.ButtonStyle.blurple, custom_id="hotel_room_add_sub")

    async def callback(self, interaction: discord.Interaction):
        room, config = await _require_room_permission(interaction)
        if room is None:
            return

        guild = interaction.guild
        vc: discord.VoiceChannel = interaction.channel

        sub_role_id = config.get("sub_role")
        if not sub_role_id:
            return await interaction.response.send_message("❌ サブ垢ロールが設定されていません。", ephemeral=True)

        sub_role = guild.get_role(int(sub_role_id))
        if not sub_role:
            return await interaction.response.send_message("❌ サブ垢ロールが設定されていません。", ephemeral=True)

        candidates = [m for m in guild.members if sub_role in m.roles and not m.bot]
        if not candidates:
            return await interaction.response.send_message("⚠ サブ垢ロール所持者がいません。", ephemeral=True)

        if len(candidates) == 1:
            t = candidates[0]
            await vc.set_permissions(t, view_channel=True, connect=True)
            return await interaction.response.send_message(
                f"👤 **{t.display_name}** をサブ垢として追加しました！",
                ephemeral=True
            )

        CHUNK = 25
        pages = [candidates[i:i + CHUNK] for i in range(0, len(candidates), CHUNK)]

        async def send_page(inter, index):
            page_members = pages[index]

            class SubSelect(discord.ui.Select):
                def __init__(self, members):
                    options = [discord.SelectOption(label=m.display_name, value=str(m.id)) for m in members]
                    super().__init__(
                        placeholder=f"サブ垢を選択（{index+1}/{len(pages)}ページ）",
                        options=options,
                        min_values=1,
                        max_values=1
                    )
                    self.map = {str(m.id): m for m in members}

                async def callback(self, inter2: discord.Interaction):
                    uid = self.values[0]
                    target = self.map[uid]
                    await vc.set_permissions(target, view_channel=True, connect=True)
                    await inter2.response.edit_message(
                        content=f"👤 **{target.display_name}** をサブ垢として追加しました！",
                        view=None
                    )

            class PrevButton(discord.ui.Button):
                def __init__(self):
                    super().__init__(label="⬅ 前", style=discord.ButtonStyle.gray)

                async def callback(self, i):
                    await send_page(i, index - 1)

            class NextButton(discord.ui.Button):
                def __init__(self):
                    super().__init__(label="次 ➡", style=discord.ButtonStyle.gray)

                async def callback(self, i):
                    await send_page(i, index + 1)

            view = discord.ui.View()
            view.add_item(SubSelect(page_members))
            if index > 0:
                view.add_item(PrevButton())
            if index < len(pages) - 1:
                view.add_item(NextButton())

            await inter.response.edit_message(content="追加するサブ垢を選択してください👇", view=view)

        view = discord.ui.View()
        first_page = pages[0]

        class SubSelect0(discord.ui.Select):
            def __init__(self, members):
                options = [discord.SelectOption(label=m.display_name, value=str(m.id)) for m in members]
                super().__init__(
                    placeholder=f"サブ垢を選択（1/{len(pages)}ページ）",
                    options=options,
                    min_values=1,
                    max_values=1
                )
                self.map = {str(m.id): m for m in members}

            async def callback(self, inter):
                uid = self.values[0]
                target = self.map[uid]
                await vc.set_permissions(target, view_channel=True, connect=True)
                await inter.response.edit_message(
                    content=f"👤 **{target.display_name}** をサブ垢として追加しました！",
                    view=None
                )

        view.add_item(SubSelect0(first_page))

        if len(pages) > 1:
            class NextStart(discord.ui.Button):
                def __init__(self):
                    super().__init__(label="次 ➡", style=discord.ButtonStyle.gray)

                async def callback(self, inter):
                    await send_page(inter, 1)

            view.add_item(NextStart())

        await interaction.response.send_message(
            "追加するサブ垢を選択してください👇",
            view=view,
            ephemeral=True
        )


# ======================================================
# 期限確認 / チケット確認（現行通り：チケット確認は押した人）
# ======================================================
class RoomCheckExpireButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="削除期限確認", style=discord.ButtonStyle.blurple, custom_id="hotel_room_check_expire")

    async def callback(self, interaction: discord.Interaction):
        room, config = await _require_room_permission(interaction)
        if room is None:
            return

        expire = room["expire_at"]
        left = expire - datetime.utcnow()
        hours = int(left.total_seconds() // 3600)
        minutes = int((left.total_seconds() % 3600) // 60)

        await interaction.response.send_message(f"⏳ 削除まで **{hours}時間 {minutes}分**", ephemeral=True)


class RoomCheckTicketsButton(discord.ui.Button):
    def __init__(self):
        super().__init__(label="チケット確認", style=discord.ButtonStyle.gray, custom_id="hotel_room_check_tickets")

    async def callback(self, interaction: discord.Interaction):
        room, config = await _require_room_permission(interaction)
        if room is None:
            return

        guild_id = str(interaction.guild.id)
        user_id = str(interaction.user.id)

        tickets = await interaction.client.db.get_tickets(user_id, guild_id)
        await interaction.response.send_message(f"🎫 所持チケット → **{tickets}枚**", ephemeral=True)

class ClearChatButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="🗑️ チャット履歴削除",
            style=discord.ButtonStyle.danger,
            custom_id="hotel:clear_chat"
        )

    async def callback(self, interaction: discord.Interaction):
        room, config = await _require_room_permission(interaction)
        if room is None:
            return

        await interaction.response.defer(ephemeral=True)

        # 実際にメッセージが流れている場所
        target = interaction.message.channel

        # purge が使えない場合のみ弾く
        if not hasattr(target, "purge"):
            await interaction.followup.send(
                "❌ この場所のチャットは削除できません。",
                ephemeral=True
            )
            return

        # --- 履歴全削除（以前と同じ挙動） ---
        await target.purge(limit=None)

        # --- 操作パネル再送 ---
        from .room_panel import HotelRoomControlPanel
        await target.send(
            "🏨 **ホテルルーム操作パネル**",
            view=HotelRoomControlPanel()
        )

        await interaction.followup.send(
            "🗑️ チャット履歴を削除しました。",
            ephemeral=True
        )
