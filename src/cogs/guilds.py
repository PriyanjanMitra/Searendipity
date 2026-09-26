from discord.ext import commands
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

    async def check_recruit_permissions(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            await ctx.send("This command can only be used in a server!")
            return False

        if ctx.guild.id not in self.guilds:
            prefix = ctx.prefix or "!"
            await ctx.send(f"This server is not configured yet. Have the server owner run `{prefix}config` first.")
            return False

        guild_cfg = self.guilds[ctx.guild.id]
        author = ctx.author
        if isinstance(author, discord.Member):
            if author.id == ctx.guild.owner_id:
                return True
            if author.get_role(guild_cfg.admin_role) is not None:
                return True
            if author.get_role(guild_cfg.recruit_role) is not None:
                return True

        await ctx.send("You do not have permission to use recruitment commands in this server!")
        return False

    async def check_admin_permissions(self, ctx: commands.Context) -> bool:
        if not ctx.guild:
            await ctx.send("This command can only be used in a server!")
            return False

        if ctx.guild.id not in self.guilds:
            prefix = ctx.prefix or "!"
            await ctx.send(f"This server is not configured yet. Have the server owner run `{prefix}config` first.")
            return False

        guild_cfg = self.guilds[ctx.guild.id]
        author = ctx.author
        if isinstance(author, discord.Member):
            if author.id == ctx.guild.owner_id:
                return True
            if author.get_role(guild_cfg.admin_role) is not None:
                return True

        await ctx.send("You must be an administrator to use this command!")
        return False

    @commands.command(
        name="config",
        help="Configure recruitment settings: config <@AdminRole> <@RecruitRole> [recruit_wa] [recruit_newfounds] [recruit_refounds]"
    )
    async def config(
        self,
        ctx: commands.Context,
        admin_role: discord.Role,
        recruit_role: discord.Role,
        recruit_wa: bool = True,
        recruit_newfounds: bool = True,
        recruit_refounds: bool = True
    ):
        if not ctx.guild:
            await ctx.send("This command must be run in a server.")
            return

        if ctx.author.id != ctx.guild.owner_id:
            await ctx.send("Only the server owner can configure the bot.")
            return

        guild = Guild(admin_role.id, recruit_role.id, recruit_wa, recruit_newfounds, recruit_refounds)
        self.sync(ctx.guild.id, guild)
        self.guilds[ctx.guild.id] = guild

        recruiter = self.bot.get_cog('RecruitmentManager')
        if recruiter:
            recruiter.update_backlog()

        await ctx.send("Server recruitment configuration updated successfully!")
