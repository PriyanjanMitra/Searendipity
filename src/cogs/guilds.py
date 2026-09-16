from discord.ext import commands
from discord import app_commands
from dataclasses import dataclass
import discord
from .db import Database

# Stores recruitment settings for a guild.
@dataclass
class Guild:
    admin_role: int         # Role ID that can administrate the recruitment bot
    recruit_role: int       # Role ID that can run recruitment
    recruit_wa: bool        # Whether to recruit new WA members
    recruit_newfounds: bool # Whether to recruit newly founded nations
    recruit_refounds: bool  # Whether to recruit refounded nations

class GuildManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guilds: dict[int, Guild] = {}
        self.load()

    def load(self):
        database: Database = self.bot.get_cog('Database')
        if not database:
            return
        cursor = database.db.cursor()
        cursor.execute("SELECT guild_id, admin_role_id, recruit_role_id, recruit_wa, recruit_newfounds, recruit_refounds FROM guilds")
        data = cursor.fetchall()

        for row in data:
            self.guilds[row[0]] = Guild(
                admin_role=row[1],
                recruit_role=row[2],
                recruit_wa=bool(row[3]),
                recruit_newfounds=bool(row[4]),
                recruit_refounds=bool(row[5])
            )
        cursor.close()

    def sync(self, guild_id: int, guild: Guild):
        database: Database = self.bot.get_cog('Database')
        cursor = database.db.cursor()
        data = (
            guild_id,
            guild.admin_role,
            guild.recruit_role,
            int(guild.recruit_wa),
            int(guild.recruit_newfounds),
            int(guild.recruit_refounds)
        )
        cursor.execute("INSERT OR REPLACE INTO guilds VALUES (?, ?, ?, ?, ?, ?)", data)
        database.db.commit()
        cursor.close()

    async def check_recruit_permissions(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server!", ephemeral=True)
            return False

        if interaction.guild.id not in self.guilds:
            await interaction.response.send_message("This server is not configured yet. Have the server owner run `/config` first.", ephemeral=True)
            return False

        guild_cfg = self.guilds[interaction.guild.id]
        user = interaction.user
        if isinstance(user, discord.Member):
            if user.id == interaction.guild.owner_id:
                return True
            if user.get_role(guild_cfg.admin_role) is not None:
                return True
            if user.get_role(guild_cfg.recruit_role) is not None:
                return True

        await interaction.response.send_message("You do not have permission to use recruitment commands in this server!", ephemeral=True)
        return False

    async def check_admin_permissions(self, interaction: discord.Interaction) -> bool:
        if not interaction.guild:
            await interaction.response.send_message("This command can only be used in a server!", ephemeral=True)
            return False

        if interaction.guild.id not in self.guilds:
            await interaction.response.send_message("This server is not configured yet. Have the server owner run `/config` first.", ephemeral=True)
            return False

        guild_cfg = self.guilds[interaction.guild.id]
        user = interaction.user
        if isinstance(user, discord.Member):
            if user.id == interaction.guild.owner_id:
                return True
            if user.get_role(guild_cfg.admin_role) is not None:
                return True

        await interaction.response.send_message("You must be an administrator to use this command!", ephemeral=True)
        return False

    @app_commands.command(name="config", description="Configure Searendipity recruitment settings for this server.")
    @app_commands.describe(
        admin_role="Role allowed to manage bot settings and stop other sessions",
        recruit_role="Role allowed to run recruitment sessions",
        recruit_wa="Whether to queue new World Assembly admissions",
        recruit_newfounds="Whether to queue newly founded nations",
        recruit_refounds="Whether to queue refounded nations"
    )
    async def config(
        self,
        interaction: discord.Interaction,
        admin_role: discord.Role,
        recruit_role: discord.Role,
        recruit_wa: bool = True,
        recruit_newfounds: bool = True,
        recruit_refounds: bool = True
    ):
        if not interaction.guild:
            await interaction.response.send_message("This command must be run in a server.", ephemeral=True)
            return

        if interaction.user.id != interaction.guild.owner_id:
            await interaction.response.send_message("Only the server owner can configure the bot.", ephemeral=True)
            return

        guild = Guild(admin_role.id, recruit_role.id, recruit_wa, recruit_newfounds, recruit_refounds)
        self.sync(interaction.guild.id, guild)
        self.guilds[interaction.guild.id] = guild

        recruiter = self.bot.get_cog('RecruitmentManager')
        if recruiter:
            recruiter.update_backlog()

        await interaction.response.send_message("Server recruitment configuration updated successfully!", ephemeral=True)
