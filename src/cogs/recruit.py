from discord.ext import commands
from collections import deque
import typing
import discord
import asyncio
import time
from dataclasses import dataclass
from datetime import datetime

from .template import TGTemplate, TemplateManager
from .guilds import GuildManager
from .stats import StatsTracker

WA_BACKLOG_SIZE = 250
BACKLOG_SIZE = 500
MAX_NATIONS_PER_TG = 8

class RecruiterView(discord.ui.View):
    def __init__(self, user: discord.User | discord.Member, url: str):
        super().__init__(timeout=None)
        button = discord.ui.Button(label='Click to Send TG', style=discord.ButtonStyle.link, url=url)
        self.add_item(button)
        self.user = user

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user == self.user:
            return True
        await interaction.response.send_message(f"This telegram dispatch was prepared for {self.user.mention}.", ephemeral=True)
        return False

@dataclass
class Queue:
    nations: deque

    @classmethod
    def create(cls, maxlen: int) -> "Queue":
        return cls(deque(maxlen=maxlen))

    def last_update(self) -> float:
        if self.nations:
            return self.nations[-1][1]
        return 0.0

class RecruitmentManager(commands.Cog):
    def __init__(self, bot: commands.Bot, nation: str):
        self.bot = bot
        self.nation = nation
        self.recruiters: dict[tuple[int, int], asyncio.Task] = {}
        self.wa_queue: dict[int, Queue] = {}
        self.newfound_queue: dict[int, Queue] = {}
        self.refound_queue: dict[int, Queue] = {}
        self.filtering_queue = deque(maxlen=100)

    @commands.Cog.listener()
    async def on_ready(self):
        self.update_backlog()
        self.bot.dispatch('backlog_ready')

    def update_backlog(self):
        for guild in self.bot.guilds:
            if guild.id not in self.wa_queue:
                self.wa_queue[guild.id] = Queue.create(WA_BACKLOG_SIZE)
            if guild.id not in self.newfound_queue:
                self.newfound_queue[guild.id] = Queue.create(BACKLOG_SIZE)
            if guild.id not in self.refound_queue:
                self.refound_queue[guild.id] = Queue.create(BACKLOG_SIZE)

    def _ensure_guild_queues(self, guild_id: int):
        if guild_id not in self.wa_queue:
            self.wa_queue[guild_id] = Queue.create(WA_BACKLOG_SIZE)
        if guild_id not in self.newfound_queue:
            self.newfound_queue[guild_id] = Queue.create(BACKLOG_SIZE)
        if guild_id not in self.refound_queue:
            self.refound_queue[guild_id] = Queue.create(BACKLOG_SIZE)

    def add_new_wa(self, nation: str):
        for guild_id, q in self.wa_queue.items():
            # WA joins receive a 2.5s priority bonus in queue sorting
            q.nations.append((nation, time.time() + 2.5))

    def add_newfound(self, nation: str):
        for guild_id, q in self.newfound_queue.items():
            q.nations.append((nation, time.time()))

    def add_refound(self, nation: str):
        for guild_id, q in self.refound_queue.items():
            q.nations.append((nation, time.time()))

    def pop_wa_nations(self, guild_id: int, max_count: int) -> list[str]:
        self._ensure_guild_queues(guild_id)
        result = []
        queue = self.wa_queue[guild_id]
        while queue.nations and len(result) < max_count:
            nation, _ = queue.nations.pop()
            result.append(nation)
        return result

    def pop_new_nations(self, guild_id: int, max_count: int) -> list[str]:
        self._ensure_guild_queues(guild_id)
        result = []
        queue = self.newfound_queue[guild_id]
        while queue.nations and len(result) < max_count:
            nation, _ = queue.nations.pop()
            result.append(nation)
        return result

    def pop_refound_nations(self, guild_id: int, max_count: int) -> list[str]:
        self._ensure_guild_queues(guild_id)
        result = []
        queue = self.refound_queue[guild_id]
        while queue.nations and len(result) < max_count:
            nation, _ = queue.nations.pop()
            result.append(nation)
        return result

    def sort_queues(self, guild_id: int) -> list[int]:
        self._ensure_guild_queues(guild_id)
        queues = [
            (0, self.wa_queue[guild_id].last_update()),
            (1, self.newfound_queue[guild_id].last_update()),
            (2, self.refound_queue[guild_id].last_update())
        ]
        queues.sort(reverse=True, key=lambda v: v[1])
        return [v[0] for v in queues]

    def check_puppet_filter(self, nation: str) -> bool:
        """Detect and filter out potential puppet cascades based on prefix similarity."""
        if not nation:
            return True

        puppet_likeliness = 0.0
        for other_nation in self.filtering_queue:
            common = 0
            for a, b in zip(nation, other_nation):
                if a == b:
                    common += 1
                else:
                    break
            ratio = common / len(nation)
            if ratio > puppet_likeliness:
                puppet_likeliness = ratio

        if puppet_likeliness < 0.60:
            self.filtering_queue.append(nation)
            return False
        else:
            print(f"[Recruiter] Skipping likely puppet '{nation}' (similarity: {puppet_likeliness:.2f})")
            return True

    def select_template(self, templates: list[TGTemplate], index: int) -> tuple[int, TGTemplate]:
        if not templates:
            raise ValueError("No templates available to select.")
        tg = templates[index % len(templates)]
        next_index = (index + 1) % len(templates)
        return (next_index, tg)

    def generate_telegram_link(self, template: TGTemplate, nations: list[str], container: str | None) -> str:
        recipients = ",".join(nations)
        identifier = f"searendipity_bot__ran_by_{self.nation}"
        if container:
            return f"https://www.nationstates.net/container={container}/page=compose_telegram?tgto={recipients}&message=%TEMPLATE-{template.tgid}%&generated_by={identifier}"
        return f"https://www.nationstates.net/page=compose_telegram?tgto={recipients}&message=%TEMPLATE-{template.tgid}%&generated_by={identifier}"

    async def send_recruitment_embed(self, channel: discord.abc.Messageable, target_type: str, template: TGTemplate, nations: list[str], container: str | None, user: discord.User | discord.Member):
        link = self.generate_telegram_link(template, nations, container)
        view = RecruiterView(user, link)

        embed = discord.Embed(
            title=f"📬 Dispatch Ready: {target_type}",
            description=f"**{len(nations)}** recipient(s) queued for template `{template.category}` (`%{template.tgid}%`).\nClick below to open the compose window.",
            color=0x2ec27e,
            timestamp=datetime.now()
        )
        embed.add_field(name="Recipients", value=", ".join([f"`{n}`" for n in nations]), inline=False)
        if container:
            embed.set_footer(text=f"Container: {container} | Searendipity")
        else:
            embed.set_footer(text="Default Browser Profile | Searendipity")

        msg = await channel.send(content=f"{user.mention}", embed=embed, view=view)
        try:
            await msg.add_reaction("✅")
        except Exception:
            pass

    async def recruit_task(self, ctx: commands.Context, interval: int, container: str | None) -> None:
        templates_cog: TemplateManager = self.bot.get_cog('TemplateManager')
        guilds_cog: GuildManager = self.bot.get_cog('GuildManager')
        stats_cog: StatsTracker = self.bot.get_cog('StatsTracker')

        guild_id = ctx.guild.id
        user_id = ctx.author.id
        key = (guild_id, user_id)

        user_template = templates_cog.user_templates.get(key)
        prefix = ctx.prefix or "!"
        if not user_template:
            await ctx.send(f"No templates configured! Use `{prefix}add` or `{prefix}setup` before recruiting.")
            return

        guild_cfg = guilds_cog.guilds.get(guild_id)
        do_wa = guild_cfg.recruit_wa if guild_cfg else True
        do_newfounds = guild_cfg.recruit_newfounds if guild_cfg else True
        do_refounds = guild_cfg.recruit_refounds if guild_cfg else True

        if len(user_template.wa) == 0:
            do_wa = False
        if len(user_template.newfound) == 0:
            do_newfounds = False
        if len(user_template.refound) == 0:
            do_refounds = False

        if not (do_wa or do_newfounds or do_refounds):
            await ctx.send("No active destination categories with configured templates found.")
            return

        conditions = [do_wa, do_newfounds, do_refounds]
        pop_operations = [self.pop_wa_nations, self.pop_new_nations, self.pop_refound_nations]
        user_templates_list = [user_template.wa, user_template.newfound, user_template.refound]
        labels = ["New WA Member", "Newly Founded", "Refounded"]
        indexes = [0, 0, 0]

        await ctx.send(
            f"🎯 {ctx.author.mention} started recruiting every **{interval}** seconds! Stand by for incoming nations..."
        )

        try:
            while True:
                await asyncio.sleep(interval)

                while True:
                    order = self.sort_queues(guild_id)
                    dispatched = False

                    for i in order:
                        if conditions[i] and user_templates_list[i]:
                            nations = pop_operations[i](guild_id, MAX_NATIONS_PER_TG)
                            if nations:
                                next_idx, tpl = self.select_template(user_templates_list[i], indexes[i])
                                indexes[i] = next_idx

                                sent_counts = [0, 0, 0]
                                sent_counts[i] = len(nations)

                                await self.send_recruitment_embed(ctx.channel, labels[i], tpl, nations, container, ctx.author)
                                dispatched = True

                                if stats_cog:
                                    stats_cog.update_stats(guild_id, user_id, *sent_counts)
                                break

                    if dispatched:
                        break

                    # Wait until a fresh recruit event arrives
                    try:
                        await asyncio.wait_for(self.bot.wait_for('new_recruit'), timeout=60.0)
                    except asyncio.TimeoutError:
                        pass
        except asyncio.CancelledError:
            pass

    @commands.command(
        name="recruit",
        help="Start manual recruitment: recruit [interval=60] [container]"
    )
    async def recruit(self, ctx: commands.Context, interval: int = 60, container: typing.Optional[str] = None):
        guilds: GuildManager = self.bot.get_cog('GuildManager')
        if not await guilds.check_recruit_permissions(ctx):
            return

        templates_cog: TemplateManager = self.bot.get_cog('TemplateManager')
        key = (ctx.guild.id, ctx.author.id)
        prefix = ctx.prefix or "!"
        if key not in templates_cog.user_templates:
            await ctx.send(f"You have no templates configured in this server. Use `{prefix}setup` or `{prefix}add` first.")
            return

        if key in self.recruiters:
            await ctx.send(f"You already have an active recruitment session running! Use `{prefix}stop` to end it.")
            return

        if interval < 30:
            await ctx.send("Recruitment cooldown cannot be less than 30 seconds to respect NS limits.")
            return

        task = asyncio.create_task(self.recruit_task(ctx, interval, container))
        self.recruiters[key] = task

    @commands.command(name="stop", help="Stop your active recruitment session: stop")
    async def stop(self, ctx: commands.Context):
        guilds: GuildManager = self.bot.get_cog('GuildManager')
        if not await guilds.check_recruit_permissions(ctx):
            return

        key = (ctx.guild.id, ctx.author.id)
        if key not in self.recruiters:
            await ctx.send("You don't have an active recruitment session running.")
            return

        task = self.recruiters.pop(key)
        task.cancel()
        await ctx.send("Your recruitment session has been stopped.")

    @commands.command(name="forcestop", help="Force stop another user's recruitment session (Admin only): forcestop <@User>")
    async def forcestop(self, ctx: commands.Context, user: discord.Member):
        guilds: GuildManager = self.bot.get_cog('GuildManager')
        if not await guilds.check_admin_permissions(ctx):
            return

        key = (ctx.guild.id, user.id)
        if key not in self.recruiters:
            await ctx.send(f"{user.display_name} does not have an active recruitment session.")
            return

        task = self.recruiters.pop(key)
        task.cancel()
        await ctx.send(f"Terminated recruitment session for {user.mention}.")

    @commands.command(name="queue", help="Check queue backlog: queue")
    async def queue(self, ctx: commands.Context):
        guilds: GuildManager = self.bot.get_cog('GuildManager')
        if not await guilds.check_recruit_permissions(ctx):
            return

        self._ensure_guild_queues(ctx.guild.id)
        wa_len = len(self.wa_queue[ctx.guild.id].nations)
        new_len = len(self.newfound_queue[ctx.guild.id].nations)
        ref_len = len(self.refound_queue[ctx.guild.id].nations)

        embed = discord.Embed(
            title=f"📊 Queue Backlog: {ctx.guild.name}",
            color=0x3584e4,
            timestamp=datetime.now()
        )
        embed.add_field(name="World Assembly (WA)", value=f"`{wa_len}` / {WA_BACKLOG_SIZE}", inline=True)
        embed.add_field(name="Newly Founded", value=f"`{new_len}` / {BACKLOG_SIZE}", inline=True)
        embed.add_field(name="Refounded", value=f"`{ref_len}` / {BACKLOG_SIZE}", inline=True)
        await ctx.send(embed=embed)

    @commands.command(name="timer", help="View recommended recruitment cooldown intervals: timer")
    async def timer(self, ctx: commands.Context):
        embed = discord.Embed(
            title="⏱️ NationStates Recruitment Cooldown Guidelines",
            description="Recruiting cooldowns are enforced by NationStates based on how old your sending nation is:",
            color=0xf6d32d
        )
        embed.add_field(name="Nations < 8 days old", value="**180 seconds** (3 minutes) cooldown", inline=False)
        embed.add_field(name="Nations 8 – 30 days old", value="**120 seconds** (2 minutes) cooldown", inline=False)
        embed.add_field(name="Nations > 30 days old", value="**60 seconds** (1 minute) cooldown", inline=False)
        embed.add_field(name="API Recruitment", value="Always strictly **180 seconds** per telegram", inline=False)
        await ctx.send(embed=embed)
