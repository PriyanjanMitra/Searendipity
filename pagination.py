# pagination.py - Interactive Discord embed pagination view
import discord
from discord.ext import commands
from typing import Callable, Optional, Tuple, Awaitable

class Pagination(discord.ui.View):
    def __init__(self, ctx: commands.Context, get_page: Callable[[int], Awaitable[Tuple[discord.Embed, int]]]):
        super().__init__(timeout=120)
        self.ctx = ctx
        self.get_page = get_page
        self.total_pages: Optional[int] = None
        self.index = 1
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user == self.ctx.author:
            return True
        else:
            emb = discord.Embed(
                description="Only the author of the command can perform this action.",
                color=discord.Color.red()
            )
            await interaction.response.send_message(embed=emb, ephemeral=True)
            return False

    async def navigate(self) -> None:
        emb, self.total_pages = await self.get_page(self.index)
        if self.total_pages <= 1:
            self.message = await self.ctx.send(embed=emb)
        else:
            self.update_buttons()
            self.message = await self.ctx.send(embed=emb, view=self)

    async def edit_page(self, interaction: discord.Interaction) -> None:
        emb, self.total_pages = await self.get_page(self.index)
        self.update_buttons()
        await interaction.response.edit_message(embed=emb, view=self)

    def update_buttons(self) -> None:
        assert self.total_pages is not None
        # Button 0 is prev, Button 1 is next, Button 2 is jump
        if self.index > self.total_pages // 2:
            self.children[2].emoji = "⏮️"  # Jump to beginning
        else:
            self.children[2].emoji = "⏭️"  # Jump to end
        self.children[0].disabled = (self.index == 1)
        self.children[1].disabled = (self.index == self.total_pages)

    @discord.ui.button(emoji="◀️", style=discord.ButtonStyle.blurple)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index -= 1
        await self.edit_page(interaction)

    @discord.ui.button(emoji="▶️", style=discord.ButtonStyle.blurple)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        self.index += 1
        await self.edit_page(interaction)

    @discord.ui.button(emoji="⏭️", style=discord.ButtonStyle.blurple)
    async def jump(self, interaction: discord.Interaction, button: discord.ui.Button) -> None:
        assert self.total_pages is not None
        if self.index <= self.total_pages // 2:
            self.index = self.total_pages
        else:
            self.index = 1
        await self.edit_page(interaction)

    async def on_timeout(self) -> None:
        if self.message:
            try:
                await self.message.edit(view=None)
            except Exception:
                pass

    @staticmethod
    def compute_total_pages(total_results: int, results_per_page: int) -> int:
        if total_results <= 0:
            return 1
        return ((total_results - 1) // results_per_page) + 1
