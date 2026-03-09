# cogs/hotel/room_panel.py
import discord

from .room_buttons import (
    RoomAddMemberLimitButton,
    RoomRenameButton,
    RoomAllowMemberButton,
    RoomDenyMemberButton,
    RoomAdd1DayButton,
    RoomAdd3DayButton,
    RoomAdd10DayButton,
    RoomAddSubRoleButton,
    RoomCheckExpireButton,
    RoomCheckTicketsButton,
    ClearChatButton,
)


class HotelRoomControlPanel(discord.ui.View):
    """
    永続化対応：状態を保持しない View
    - owner_id / role_id は保持しない
    - 各ボタンが押された瞬間に DB から room/config を取得して処理
    """
    def __init__(self):
        super().__init__(timeout=None)

        self.add_item(RoomAddMemberLimitButton())
        self.add_item(RoomRenameButton())
        self.add_item(RoomAllowMemberButton())
        self.add_item(RoomDenyMemberButton())
        self.add_item(RoomAdd1DayButton())
        self.add_item(RoomAdd3DayButton())
        self.add_item(RoomAdd10DayButton())
        self.add_item(RoomAddSubRoleButton())
        self.add_item(RoomCheckExpireButton())
        self.add_item(RoomCheckTicketsButton())
        self.add_item(ClearChatButton())

