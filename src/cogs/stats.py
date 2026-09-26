from discord.ext import commands
from dataclasses import dataclass
from datetime import date, timedelta
import typing
import discord

from .db import Database
from .guilds import GuildManager
from pagination import Pagination

@dataclass
class Stats:
    wa_sent: int
    newfound_sent: int
    refound_sent: int

    @property
    def total(self) -> int:
        return self.wa_sent + self.newfound_sent + self.refound_sent

class StatsTracker(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.stat_map: dict[tuple[int, int, date], Stats] = {}
        self.load()

    def load(self):
        database: Database = self.bot.get_cog('Database')
        if not database:
            return
        cursor = database.db.cursor()
        cursor.execute("SELECT guild_id, user_id, year, month, day, wa_sent, newfound_sent, refound_sent FROM stats")
        data = cursor.fetchall()

        for row in data:
            entry_date = date(row[2], row[3], row[4])
            self.stat_map[(row[0], row[1], entry_date)] = Stats(row[5], row[6], row[7])
        cursor.close()

    def sync(self, guild_id: int, user_id: int, today: date):
        database: Database = self.bot.get_cog('Database')
        cursor = database.db.cursor()

        stat = self.stat_map[(guild_id, user_id, today)]
        unique_id = f"{guild_id}-{user_id}-{today.year}-{today.month}-{today.day}"
        data = (
            unique_id,
            guild_id,
            user_id,
            today.year,
            today.month,
            today.day,
            stat.wa_sent,
            stat.newfound_sent,
            stat.refound_sent
        )
        cursor.execute("INSERT OR REPLACE INTO stats VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", data)
        database.db.commit()
        cursor.close()

    def update_stats(self, guild_id: int, user_id: int, update_wa: int, update_newfound: int, update_refound: int):
        today = date.today()
        key = (guild_id, user_id, today)
        stat = self.stat_map.get(key)

        if stat is None:
            self.stat_map[key] = Stats(update_wa, update_newfound, update_refound)
        else:
            stat.wa_sent += update_wa
            stat.newfound_sent += update_newfound
            stat.refound_sent += update_refound

        self.sync(guild_id, user_id, today)

    @commands.command(name="stats", help="Show recruitment leaderboard: stats [since_days]")
    async def stats(self, ctx: commands.Context, since: typing.Optional[int] = None):
        guilds: GuildManager = self.bot.get_cog('GuildManager')
        if not await guilds.check_recruit_permissions(ctx):
            return

        start_day = None
        if since is not None and since > 0:
            start_day = date.today() - timedelta(days=since)

        recruiter_totals: dict[str, list[int]] = {}

        for (guild_id, user_id, day), stat in self.stat_map.items():
            if guild_id != ctx.guild.id:
                continue
            if start_day is not None and day < start_day:
                continue

            member = ctx.guild.get_member(user_id)
            name = member.display_name if member else f"User ID {user_id}"

            if name not in recruiter_totals:
                recruiter_totals[name] = [0, 0, 0, 0]  # [total, wa, newfound, refound]

            recruiter_totals[name][0] += stat.total
            recruiter_totals[name][1] += stat.wa_sent
            recruiter_totals[name][2] += stat.newfound_sent
            recruiter_totals[name][3] += stat.refound_sent

        recruiters = [
            (name, counts[0], counts[1], counts[2], counts[3])
            for name, counts in recruiter_totals.items()
        ]
        recruiters.sort(key=lambda item: item[1], reverse=True)

        if not recruiters:
            if start_day:
                msg = f"No recruitment telegrams have been sent in **{ctx.guild.name}** since {start_day.strftime('%b %d, %Y')}."
            else:
                msg = f"No recruitment telegrams recorded yet for **{ctx.guild.name}**."
            await ctx.send(msg)
            return

        PER_PAGE = 10
        title_suffix = f"Since {start_day.strftime('%b %d, %Y')}" if start_day else "All-Time"

        async def get_page(page: int):
            emb = discord.Embed(
                title=f"🏆 Recruitment Leaderboard — {ctx.guild.name}",
                description=f"Showing stats: **{title_suffix}**\n\n",
                color=0x9141ac
            )
            offset = (page - 1) * PER_PAGE
            page_slice = recruiters[offset:offset + PER_PAGE]

            for rank, (name, total, wa, new, ref) in enumerate(page_slice, start=offset + 1):
                emb.description += f"**#{rank}** `{name}` — **{total:,}** total (`{wa:,}` WA, `{new:,}` new, `{ref:,}` refound)\n"

            total_pages = Pagination.compute_total_pages(len(recruiters), PER_PAGE)
            emb.set_footer(text=f"Page {page} of {total_pages} | Searendipity")
            return emb, total_pages

        await Pagination(ctx, get_page).navigate()
