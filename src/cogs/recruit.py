from discord.ext import commands
from collections import deque
import typing
import discord
import time
from dataclasses import dataclass, field
from datetime import datetime

from .template import TGTemplate, TemplateManager
from .guilds import GuildManager
from .stats import StatsTracker

WA_BACKLOG_SIZE = 250
BACKLOG_SIZE = 500
MAX_NATIONS_PER_TG = 8

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

@dataclass
class RecruiterSession:
    guild_id: int
    user_id: int
    user: discord.User | discord.Member
    channel: discord.abc.Messageable
    interval: int  # Strict wait time in seconds
    container: str | None
    indexes: list[int] = field(default_factory=lambda: [0, 0, 0])
    current_nations: list[str] = field(default_factory=list)
    current_type_idx: int = 0
    current_template: TGTemplate | None = None
    is_sent: bool = False
    sent_at: float = 0.0
    last_message: discord.Message | None = None
    wa_queue: Queue = field(default_factory=lambda: Queue.create(WA_BACKLOG_SIZE))
    newfound_queue: Queue = field(default_factory=lambda: Queue.create(BACKLOG_SIZE))
    refound_queue: Queue = field(default_factory=lambda: Queue.create(BACKLOG_SIZE))

class BatchView(discord.ui.View):
    def __init__(self, session: RecruiterSession, manager: "RecruitmentManager"):
        super().__init__(timeout=None)
        self.session = session
        self.manager = manager

        # Dynamic link button to compose telegram
        tg_url = manager.generate_telegram_link(
            session.current_template,
            session.current_nations,
            session.container
        )
        link_button = discord.ui.Button(
            label="Click to Send TG",
            style=discord.ButtonStyle.link,
            url=tg_url,
            row=0
        )
        self.add_item(link_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.session.user_id:
            return True
        await interaction.response.send_message(
            f"This recruitment dispatch belongs to {self.session.user.mention}.",
            ephemeral=True
        )
        return False

    @discord.ui.button(label="Mark as Sent", style=discord.ButtonStyle.primary, emoji="✅", row=0)
    async def btn_mark_sent(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.session.is_sent:
            await interaction.response.send_message("This batch has already been marked as sent!", ephemeral=True)
            return

        self.session.is_sent = True
        self.session.sent_at = time.time()

        # Update stats since user confirmed telegram was sent
        stats_cog: StatsTracker = self.manager.bot.get_cog('StatsTracker')
        if stats_cog and self.session.current_nations:
            counts = [0, 0, 0]
            counts[self.session.current_type_idx] = len(self.session.current_nations)
            stats_cog.update_stats(self.session.guild_id, self.session.user_id, *counts)

        button.disabled = True
        button.label = "Sent!"

        ready_at = int(self.session.sent_at + self.session.interval)

        # Update message embed
        if self.session.last_message:
            try:
                emb = self.session.last_message.embeds[0]
                emb.color = 0xf6d32d  # Amber for active cooldown countdown
                emb.set_field_at(
                    1,
                    name="Status",
                    value=f"✅ **Sent!** Strict cooldown active.\nReady for next batch: <t:{ready_at}:R> (<t:{ready_at}:T>)",
                    inline=False
                )
                await interaction.response.edit_message(embed=emb, view=self)
                return
            except Exception:
                pass

        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Get Next List", style=discord.ButtonStyle.success, emoji="⏭️", row=0)
    async def btn_next_list(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Requirement 1: Check first if the previous list was sent
        if not self.session.is_sent:
            await interaction.response.send_message(
                "⚠️ **Check Failed:** You have not marked the current list as sent yet!\n"
                "Please click **Click to Send TG** to send your telegram, then click **Mark as Sent** before requesting the next list.",
                ephemeral=True
            )
            return

        # Requirement 2: Strict wait times
        now = time.time()
        elapsed = now - self.session.sent_at
        if elapsed < self.session.interval:
            remaining = int(self.session.interval - elapsed) + 1
            ready_at = int(self.session.sent_at + self.session.interval)
            await interaction.response.send_message(
                f"⏳ **Strict Cooldown Active!**\n"
                f"You must wait another **{remaining} seconds** (<t:{ready_at}:R>) before requesting the next list.",
                ephemeral=True
            )
            return

        # Fetch and deliver the next list manually
        dispatched = await self.manager.dispatch_next_batch(self.session)
        if dispatched:
            # Disable interactive buttons on previous message now that next batch is sent
            for item in self.children:
                if isinstance(item, discord.ui.Button) and not item.url:
                    item.disabled = True
            try:
                await interaction.response.edit_message(view=self)
            except Exception:
                pass
        else:
            await interaction.response.send_message(
                "📭 The nation queue is currently empty. Waiting for incoming events... Click **Get Next List** again once new nations arrive.",
                ephemeral=True
            )

    @discord.ui.button(label="Stop Session", style=discord.ButtonStyle.danger, emoji="⏹️", row=0)
    async def btn_stop_session(self, interaction: discord.Interaction, button: discord.ui.Button):
        key = (self.session.guild_id, self.session.user_id)
        session = self.manager.recruiters.pop(key, None)
        if session:
            self.manager.recycle_session_queues(session)

        for item in self.children:
            if isinstance(item, discord.ui.Button) and not item.url:
                item.disabled = True

        try:
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("🛑 Recruitment session stopped.", ephemeral=True)
        except Exception:
            if not interaction.response.is_done():
                await interaction.response.send_message("🛑 Recruitment session stopped.", ephemeral=True)

class RecruitmentManager(commands.Cog):
    def __init__(self, bot: commands.Bot, nation: str):
        self.bot = bot
        self.nation = nation
        self.recruiters: dict[tuple[int, int], RecruiterSession] = {}
        self.wa_queue: dict[int, Queue] = {}
        self.newfound_queue: dict[int, Queue] = {}
        self.refound_queue: dict[int, Queue] = {}
        self.rr_index: dict[tuple[int, int], int] = {}
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

    def _can_recruit_category(self, session: RecruiterSession, cat_idx: int) -> bool:
        """Check if a recruiter session is able and configured to recruit a specific category."""
        templates_cog: TemplateManager = self.bot.get_cog('TemplateManager')
        guilds_cog: GuildManager = self.bot.get_cog('GuildManager')

        key = (session.guild_id, session.user_id)
        if templates_cog:
            user_template = templates_cog.user_templates.get(key)
            if user_template:
                user_templates_list = [user_template.wa, user_template.newfound, user_template.refound]
                if not user_templates_list[cat_idx]:
                    return False

        if guilds_cog:
            guild_cfg = guilds_cog.guilds.get(session.guild_id)
            if guild_cfg:
                conditions = [guild_cfg.recruit_wa, guild_cfg.recruit_newfounds, guild_cfg.recruit_refounds]
                if not conditions[cat_idx]:
                    return False

        return True

    def _route_nation(self, cat_idx: int, nation: str, timestamp_offset: float = 0.0):
        ts = time.time() + timestamp_offset
        all_guild_ids = set(self.wa_queue.keys())
        for guild in getattr(self.bot, "guilds", []):
            all_guild_ids.add(guild.id)

        for guild_id in all_guild_ids:
            self._ensure_guild_queues(guild_id)

            # Find all active recruiters in this guild eligible for this category
            active_sessions = [
                s for s in self.recruiters.values()
                if s.guild_id == guild_id and self._can_recruit_category(s, cat_idx)
            ]

            if not active_sessions:
                # No active eligible recruiters -> push to guild backlog
                if cat_idx == 0:
                    self.wa_queue[guild_id].nations.append((nation, ts))
                elif cat_idx == 1:
                    self.newfound_queue[guild_id].nations.append((nation, ts))
                else:
                    self.refound_queue[guild_id].nations.append((nation, ts))
            else:
                # Round-Robin / Split queues across active recruiters
                rr_key = (guild_id, cat_idx)
                current_rr = self.rr_index.get(rr_key, 0)
                selected_session = active_sessions[current_rr % len(active_sessions)]
                self.rr_index[rr_key] = (current_rr + 1) % len(active_sessions)

                if cat_idx == 0:
                    selected_session.wa_queue.nations.append((nation, ts))
                elif cat_idx == 1:
                    selected_session.newfound_queue.nations.append((nation, ts))
                else:
                    selected_session.refound_queue.nations.append((nation, ts))

    def recycle_session_queues(self, session: RecruiterSession):
        """Return un-dispatched nations from a stopping session back to the guild backlog."""
        guild_id = session.guild_id
        self._ensure_guild_queues(guild_id)
        while session.wa_queue.nations:
            self.wa_queue[guild_id].nations.appendleft(session.wa_queue.nations.pop())
        while session.newfound_queue.nations:
            self.newfound_queue[guild_id].nations.appendleft(session.newfound_queue.nations.pop())
        while session.refound_queue.nations:
            self.refound_queue[guild_id].nations.appendleft(session.refound_queue.nations.pop())

    def pop_wa_for_session(self, session: RecruiterSession, max_count: int) -> list[str]:
        result = []
        while session.wa_queue.nations and len(result) < max_count:
            nation, _ = session.wa_queue.nations.pop()
            result.append(nation)
        self._ensure_guild_queues(session.guild_id)
        guild_q = self.wa_queue[session.guild_id]
        while guild_q.nations and len(result) < max_count:
            nation, _ = guild_q.nations.pop()
            result.append(nation)
        return result

    def pop_new_for_session(self, session: RecruiterSession, max_count: int) -> list[str]:
        result = []
        while session.newfound_queue.nations and len(result) < max_count:
            nation, _ = session.newfound_queue.nations.pop()
            result.append(nation)
        self._ensure_guild_queues(session.guild_id)
        guild_q = self.newfound_queue[session.guild_id]
        while guild_q.nations and len(result) < max_count:
            nation, _ = guild_q.nations.pop()
            result.append(nation)
        return result

    def pop_refound_for_session(self, session: RecruiterSession, max_count: int) -> list[str]:
        result = []
        while session.refound_queue.nations and len(result) < max_count:
            nation, _ = session.refound_queue.nations.pop()
            result.append(nation)
        self._ensure_guild_queues(session.guild_id)
        guild_q = self.refound_queue[session.guild_id]
        while guild_q.nations and len(result) < max_count:
            nation, _ = guild_q.nations.pop()
            result.append(nation)
        return result

    def sort_queues_for_session(self, session: RecruiterSession) -> list[int]:
        self._ensure_guild_queues(session.guild_id)
        wa_time = max(session.wa_queue.last_update(), self.wa_queue[session.guild_id].last_update())
        new_time = max(session.newfound_queue.last_update(), self.newfound_queue[session.guild_id].last_update())
        ref_time = max(session.refound_queue.last_update(), self.refound_queue[session.guild_id].last_update())

        queues = [
            (0, wa_time),
            (1, new_time),
            (2, ref_time)
        ]
        queues.sort(reverse=True, key=lambda v: v[1])
        return [v[0] for v in queues]

    def add_new_wa(self, nation: str):
        self._route_nation(0, nation, timestamp_offset=2.5)

    def add_newfound(self, nation: str):
        self._route_nation(1, nation, timestamp_offset=0.0)

    def add_refound(self, nation: str):
        self._route_nation(2, nation, timestamp_offset=0.0)

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
        tgid = template.tgid if template else 0
        if container:
            return f"https://www.nationstates.net/container={container}/page=compose_telegram?tgto={recipients}&message=%TEMPLATE-{tgid}%&generated_by={identifier}"
        return f"https://www.nationstates.net/page=compose_telegram?tgto={recipients}&message=%TEMPLATE-{tgid}%&generated_by={identifier}"

    async def dispatch_next_batch(self, session: RecruiterSession) -> bool:
        """Pops the next available nations from queue and sends the interactive dispatch embed."""
        templates_cog: TemplateManager = self.bot.get_cog('TemplateManager')
        guilds_cog: GuildManager = self.bot.get_cog('GuildManager')

        key = (session.guild_id, session.user_id)
        user_template = templates_cog.user_templates.get(key)
        if not user_template:
            await session.channel.send(f"{session.user.mention} No templates configured! Use `?add` or `?setup` first.")
            return False

        guild_cfg = guilds_cog.guilds.get(session.guild_id)
        do_wa = (guild_cfg.recruit_wa if guild_cfg else True) and len(user_template.wa) > 0
        do_newfounds = (guild_cfg.recruit_newfounds if guild_cfg else True) and len(user_template.newfound) > 0
        do_refounds = (guild_cfg.recruit_refounds if guild_cfg else True) and len(user_template.refound) > 0

        conditions = [do_wa, do_newfounds, do_refounds]
        pop_operations = [self.pop_wa_for_session, self.pop_new_for_session, self.pop_refound_for_session]
        user_templates_list = [user_template.wa, user_template.newfound, user_template.refound]
        labels = ["New WA Member", "Newly Founded", "Refounded"]

        order = self.sort_queues_for_session(session)

        for i in order:
            if conditions[i] and user_templates_list[i]:
                nations = pop_operations[i](session, MAX_NATIONS_PER_TG)
                if nations:
                    next_idx, tpl = self.select_template(user_templates_list[i], session.indexes[i])
                    session.indexes[i] = next_idx

                    session.current_nations = nations
                    session.current_type_idx = i
                    session.current_template = tpl
                    session.is_sent = False
                    session.sent_at = 0.0

                    view = BatchView(session, self)
                    embed = discord.Embed(
                        title=f"📬 Dispatch Ready: {labels[i]}",
                        description=(
                            f"**{len(nations)}** recipient(s) queued for template `{tpl.category}` (`%{tpl.tgid}%`).\n\n"
                            f"**Instructions:**\n"
                            f"1. Click **Click to Send TG** below to compose on NationStates.\n"
                            f"2. Click **Mark as Sent** once delivered to start your strict **{session.interval}s** cooldown.\n"
                            f"3. When the cooldown ends, click **Get Next List** to receive the next batch."
                        ),
                        color=0x2ec27e,
                        timestamp=datetime.now()
                    )
                    embed.add_field(name="Recipients", value=", ".join([f"`{n}`" for n in nations]), inline=False)
                    embed.add_field(name="Status", value="⏳ **Pending Dispatch** (Click *Mark as Sent* once delivered)", inline=False)

                    active_count = len([s for s in self.recruiters.values() if s.guild_id == session.guild_id])
                    parallel_str = f"⚡ Parallel Recruiters: {active_count} (Split)" if active_count > 1 else "Solo Recruiter"
                    container_str = f" | Container: {session.container}" if session.container else ""
                    embed.set_footer(text=f"{parallel_str} | Strict Cooldown: {session.interval}s{container_str}")

                    msg = await session.channel.send(content=f"{session.user.mention}", embed=embed, view=view)
                    session.last_message = msg
                    return True

        return False

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
        prefix = ctx.prefix or "?"
        if key not in templates_cog.user_templates:
            await ctx.send(f"You have no templates configured in this server. Use `{prefix}setup` or `{prefix}add` first.")
            return

        if key in self.recruiters:
            await ctx.send(f"You already have an active recruitment session running! Click **Stop Session** or use `{prefix}stop`.")
            return

        if interval < 30:
            await ctx.send("Recruitment cooldown cannot be less than 30 seconds to respect NS limits.")
            return

        session = RecruiterSession(
            guild_id=ctx.guild.id,
            user_id=ctx.author.id,
            user=ctx.author,
            channel=ctx.channel,
            interval=interval,
            container=container,
            indexes=[0, 0, 0]
        )
        self.recruiters[key] = session

        await ctx.send(f"🎯 {ctx.author.mention} started recruiting (strict wait time: **{interval}s**). Preparing your first list...")
        dispatched = await self.dispatch_next_batch(session)
        if not dispatched:
            await ctx.send("📭 The nation queue is currently empty. Stand by — as soon as nations are founded or join WA, click **Get Next List**.")

    @commands.command(name="stop", help="Stop your active recruitment session: stop")
    async def stop(self, ctx: commands.Context):
        guilds: GuildManager = self.bot.get_cog('GuildManager')
        if not await guilds.check_recruit_permissions(ctx):
            return

        key = (ctx.guild.id, ctx.author.id)
        if key not in self.recruiters:
            await ctx.send("You don't have an active recruitment session running.")
            return

        session = self.recruiters.pop(key)
        self.recycle_session_queues(session)
        if session.last_message:
            try:
                view = discord.ui.View.from_message(session.last_message)
                for item in view.children:
                    item.disabled = True
                await session.last_message.edit(view=view)
            except Exception:
                pass

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

        session = self.recruiters.pop(key)
        self.recycle_session_queues(session)
        if session.last_message:
            try:
                view = discord.ui.View.from_message(session.last_message)
                for item in view.children:
                    item.disabled = True
                await session.last_message.edit(view=view)
            except Exception:
                pass

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

        active_recruits = [s for s in self.recruiters.values() if s.guild_id == ctx.guild.id]

        embed = discord.Embed(
            title=f"📊 Queue Backlog: {ctx.guild.name}",
            color=0x3584e4,
            timestamp=datetime.now()
        )
        embed.add_field(name="World Assembly (WA)", value=f"`{wa_len}` / {WA_BACKLOG_SIZE}", inline=True)
        embed.add_field(name="Newly Founded", value=f"`{new_len}` / {BACKLOG_SIZE}", inline=True)
        embed.add_field(name="Refounded", value=f"`{ref_len}` / {BACKLOG_SIZE}", inline=True)

        if active_recruits:
            embed.add_field(
                name="Parallel Queueing",
                value=f"⚡ **{len(active_recruits)}** active recruiter(s) in this server (Round-Robin split).",
                inline=False
            )

        caller_key = (ctx.guild.id, ctx.author.id)
        if caller_key in self.recruiters:
            user_s = self.recruiters[caller_key]
            embed.add_field(
                name="Your Parallel Queue",
                value=(
                    f"• **WA Joins:** `{len(user_s.wa_queue.nations)}`\n"
                    f"• **Newly Founded:** `{len(user_s.newfound_queue.nations)}`\n"
                    f"• **Refounded:** `{len(user_s.refound_queue.nations)}`"
                ),
                inline=False
            )

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
