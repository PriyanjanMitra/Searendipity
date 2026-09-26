from discord.ext import commands
import discord
import asyncio
import sans
import httpx
import json
import typing
from datetime import datetime
from dataclasses import dataclass

from .recruit import RecruitmentManager
from .guilds import GuildManager
import utility as util

class APITGTemplate:
    category: str
    tgid: int
    key: str

    def __init__(self, category: str = "", tgid: int = 0, key: str = ""):
        self.category = category
        self.tgid = tgid
        self.key = key

    @staticmethod
    def from_string(string: str) -> "APITGTemplate":
        parts = string.split(":", 2)
        category = parts[0]
        tgid = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        key = parts[2] if len(parts) > 2 else ""
        return APITGTemplate(category, tgid, key)

    def to_string(self) -> str:
        return f"{self.category}:{self.tgid}:{self.key}"

@dataclass
class APITemplates:
    wa: list[APITGTemplate]
    newfound: list[APITGTemplate]
    refound: list[APITGTemplate]

    @staticmethod
    def from_strings(wa: str, newfound: str, refound: str) -> "APITemplates":
        wa_list = [APITGTemplate.from_string(s) for s in wa.split(",") if s.strip()]
        newfound_list = [APITGTemplate.from_string(s) for s in newfound.split(",") if s.strip()]
        refound_list = [APITGTemplate.from_string(s) for s in refound.split(",") if s.strip()]
        return APITemplates(wa_list, newfound_list, refound_list)

    def to_strings(self) -> typing.Tuple[str, str, str]:
        wa = ",".join([t.to_string() for t in self.wa])
        newfound = ",".join([t.to_string() for t in self.newfound])
        refound = ",".join([t.to_string() for t in self.refound])
        return (wa, newfound, refound)

class APIRecruiter(commands.Cog):
    RECRUITMENT_DELAY = 180  # NationStates mandatory API recruitment cooldown in seconds

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.guild: typing.Optional[int] = None
        self.client_key: typing.Optional[str] = None
        self.recruitment_task: typing.Optional[asyncio.Task] = None
        self.start_time: datetime = datetime.now()
        self.sent_count: int = 0
        self.templates: APITemplates = APITemplates([], [], [])
        self.load()

    @commands.Cog.listener()
    async def on_backlog_ready(self):
        if self.guild and self.client_key and not self.recruitment_task:
            print("[APIRecruiter] Configuration detected, auto-starting API recruitment loop...")
            self.recruitment_task = asyncio.create_task(self.telegram_loop())

    def load(self):
        try:
            with open("api.json", "r") as f:
                data = json.load(f)
            self.guild = data.get("guild")
            self.client_key = data.get("client_key")
            self.templates = APITemplates.from_strings(
                data.get("wa", ""),
                data.get("newfound", ""),
                data.get("refound", "")
            )
        except Exception:
            pass

    def sync(self):
        data = {}
        if self.guild:
            data["guild"] = self.guild
        if self.client_key:
            data["client_key"] = self.client_key

        wa, newfound, refound = self.templates.to_strings()
        data["wa"] = wa
        data["newfound"] = newfound
        data["refound"] = refound

        try:
            with open("api.json", "w") as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"[APIRecruiter] Failed to save api.json: {e}")

    async def check_owner(self, ctx: commands.Context) -> bool:
        if ctx.author.id != self.bot.owner_id:
            await ctx.send("Only the bot administrator can manage API recruitment.")
            return False
        return True

    @commands.command(name="apiguild", help="Set this server as the source queue for API recruitment: apiguild")
    async def apiguild(self, ctx: commands.Context):
        if not await self.check_owner(ctx):
            return
        if not ctx.guild:
            await ctx.send("This command must be run in a server.")
            return

        self.guild = ctx.guild.id
        self.sync()
        await ctx.send(f"API recruitment bound to server **{ctx.guild.name}** (`{self.guild}`).")

    @commands.command(name="apiclient", help="Set NationStates API Client Key: apiclient <key>")
    async def apiclient(self, ctx: commands.Context, client_key: str):
        if not await self.check_owner(ctx):
            return

        self.client_key = client_key.strip()
        self.sync()
        await ctx.send("API Client Key updated and saved successfully.")

    @commands.command(name="apistart", help="Start automated API recruitment: apistart")
    async def apistart(self, ctx: commands.Context):
        if not await self.check_owner(ctx):
            return

        prefix = ctx.prefix or "!"
        if not self.guild:
            await ctx.send(f"Please set an API server first using `{prefix}apiguild`.")
            return
        if not self.client_key:
            await ctx.send(f"Please set your API Client Key first using `{prefix}apiclient`.")
            return
        if self.recruitment_task and not self.recruitment_task.done():
            await ctx.send("API recruitment is already running.")
            return

        self.recruitment_task = asyncio.create_task(self.telegram_loop())
        await ctx.send("API recruitment loop started successfully.")

    @commands.command(name="apistop", help="Stop automated API recruitment: apistop")
    async def apistop(self, ctx: commands.Context):
        if not await self.check_owner(ctx):
            return

        if not self.recruitment_task or self.recruitment_task.done():
            await ctx.send("API recruitment is not running.")
            return

        self.recruitment_task.cancel()
        self.recruitment_task = None
        await ctx.send("API recruitment loop stopped.")

    @commands.command(name="apirestart", help="Restart automated API recruitment: apirestart")
    async def apirestart(self, ctx: commands.Context):
        if not await self.check_owner(ctx):
            return

        if self.recruitment_task and not self.recruitment_task.done():
            self.recruitment_task.cancel()

        self.recruitment_task = asyncio.create_task(self.telegram_loop())
        await ctx.send("API recruitment loop restarted.")

    @commands.command(name="apistatus", help="Show current status of automated API recruitment: apistatus")
    async def apistatus(self, ctx: commands.Context):
        if not await self.check_owner(ctx):
            return

        is_running = bool(self.recruitment_task and not self.recruitment_task.done())
        guild_name = "None"
        if self.guild:
            g = self.bot.get_guild(self.guild)
            guild_name = g.name if g else str(self.guild)

        embed = discord.Embed(
            title="🤖 Automated API Recruitment Status",
            color=0x2ec27e if is_running else 0xe01b24,
            timestamp=datetime.now()
        )
        embed.add_field(name="Status", value="🟢 **Active**" if is_running else "🔴 **Stopped**", inline=True)
        embed.add_field(name="Server Bound", value=f"`{guild_name}`", inline=True)
        embed.add_field(name="Telegrams Sent", value=f"`{self.sent_count:,}`", inline=True)

        embed.add_field(name="WA Templates", value=str(len(self.templates.wa)), inline=True)
        embed.add_field(name="Newfound Templates", value=str(len(self.templates.newfound)), inline=True)
        embed.add_field(name="Refound Templates", value=str(len(self.templates.refound)), inline=True)

        if is_running:
            embed.add_field(name="Started At", value=f"<t:{int(self.start_time.timestamp())}:R>", inline=False)

        await ctx.send(embed=embed)

    @commands.command(name="apitemplates", help="List registered API recruitment templates: apitemplates")
    async def apitemplates(self, ctx: commands.Context):
        if not await self.check_owner(ctx):
            return

        embed = discord.Embed(title="🔑 Registered API Recruitment Templates", color=0x3584e4)

        if self.templates.wa:
            desc = "\n".join([f"• **{t.category}**: `%{t.tgid}%` (key: `{t.key}`) — [Link](https://www.nationstates.net/tgcategory={t.category}/page=tg/tgid={t.tgid})" for t in self.templates.wa])
            embed.add_field(name="World Assembly (WA)", value=desc, inline=False)

        if self.templates.newfound:
            desc = "\n".join([f"• **{t.category}**: `%{t.tgid}%` (key: `{t.key}`) — [Link](https://www.nationstates.net/tgcategory={t.category}/page=tg/tgid={t.tgid})" for t in self.templates.newfound])
            embed.add_field(name="Newly Founded", value=desc, inline=False)

        if self.templates.refound:
            desc = "\n".join([f"• **{t.category}**: `%{t.tgid}%` (key: `{t.key}`) — [Link](https://www.nationstates.net/tgcategory={t.category}/page=tg/tgid={t.tgid})" for t in self.templates.refound])
            embed.add_field(name="Refounded", value=desc, inline=False)

        prefix = ctx.prefix or "!"
        if not embed.fields:
            await ctx.send(f"No API templates registered yet. Use `{prefix}apiadd` or `{prefix}apisetup`.")
            return

        try:
            await ctx.author.send(embed=embed)
            if ctx.guild:
                await ctx.send("📬 API templates sent to your DMs for security.")
        except Exception:
            await ctx.send(embed=embed)

    @commands.command(name="apiadd", help="Add an API template: apiadd <wa|newfound|refound> <category> <tgid> <key>")
    async def apiadd(self, ctx: commands.Context, destination: str, category: str, tgid: str, key: str):
        if not await self.check_owner(ctx):
            return

        dest = destination.lower().strip()
        if dest not in ("wa", "newfound", "refound"):
            await ctx.send("Destination must be one of `wa`, `newfound`, or `refound`.")
            return

        numeric_id = util.parse_template_id(tgid)
        if numeric_id is None:
            await ctx.send("Invalid Template ID! Provide a numeric ID or `%TEMPLATE-12345%`.")
            return

        clean_cat = category.strip().replace(":", "-")
        tpl = APITGTemplate(category=clean_cat, tgid=numeric_id, key=key.strip())

        if dest == "wa":
            self.templates.wa.append(tpl)
        elif dest == "newfound":
            self.templates.newfound.append(tpl)
        elif dest == "refound":
            self.templates.refound.append(tpl)

        self.sync()
        await ctx.send(f"Added API **{dest.upper()}** template `{clean_cat}` (`{numeric_id}`).")

    @commands.command(name="apisetup", help="Set generic API template across destinations: apisetup <tgid> <key>")
    async def apisetup(self, ctx: commands.Context, tgid: str, key: str):
        if not await self.check_owner(ctx):
            return

        numeric_id = util.parse_template_id(tgid)
        if numeric_id is None:
            await ctx.send("Invalid Template ID! Provide a numeric ID or `%TEMPLATE-12345%`.")
            return

        for lst in (self.templates.wa, self.templates.newfound, self.templates.refound):
            lst.append(APITGTemplate(category="generic", tgid=numeric_id, key=key.strip()))

        self.sync()
        await ctx.send(f"Configured generic API template `{numeric_id}` for WA, newfounds, and refounds.")

    @commands.command(name="apiremove", help="Remove API templates by category: apiremove <category>")
    async def apiremove(self, ctx: commands.Context, category: str):
        if not await self.check_owner(ctx):
            return

        clean_cat = category.strip()
        removed = 0
        for target_list in [self.templates.wa, self.templates.newfound, self.templates.refound]:
            to_del = [t for t in target_list if t.category == clean_cat]
            for t in to_del:
                target_list.remove(t)
                removed += 1

        self.sync()
        await ctx.send(f"Removed {removed} API template(s) matching category `{clean_cat}`.")

    @commands.command(name="apiclear", help="Clear all registered API templates: apiclear")
    async def apiclear(self, ctx: commands.Context):
        if not await self.check_owner(ctx):
            return

        self.templates = APITemplates([], [], [])
        self.sync()
        await ctx.send("All API templates have been cleared.")

    async def telegram_loop(self):
        recruit: RecruitmentManager = self.bot.get_cog('RecruitmentManager')
        guilds: GuildManager = self.bot.get_cog('GuildManager')

        limiter = sans.TelegramLimiter(recruitment=True)
        self.start_time = datetime.now()

        print("[APIRecruiter] Background API recruitment loop started.")

        try:
            async with sans.AsyncClient() as client:
                while True:
                    if not self.guild:
                        await asyncio.sleep(10)
                        continue

                    guild_cfg = guilds.guilds.get(self.guild) if guilds else None
                    do_wa = guild_cfg.recruit_wa if guild_cfg else True
                    do_newfounds = guild_cfg.recruit_newfounds if guild_cfg else True
                    do_refounds = guild_cfg.recruit_refounds if guild_cfg else True

                    if len(self.templates.wa) == 0:
                        do_wa = False
                    if len(self.templates.newfound) == 0:
                        do_newfounds = False
                    if len(self.templates.refound) == 0:
                        do_refounds = False

                    conditions = [do_wa, do_newfounds, do_refounds]
                    pop_operations = [recruit.pop_wa_nations, recruit.pop_new_nations, recruit.pop_refound_nations]
                    template_groups = [self.templates.wa, self.templates.newfound, self.templates.refound]
                    categories = ["wa", "newfound", "refound"]
                    indexes = [0, 0, 0]

                    order = recruit.sort_queues(self.guild)
                    dispatched = False

                    for i in order:
                        if conditions[i] and template_groups[i]:
                            nations = pop_operations[i](self.guild, 1)
                            if nations:
                                target = nations[0]
                                next_idx, template = recruit.select_template(template_groups[i], indexes[i])
                                indexes[i] = next_idx

                                try:
                                    print(f"[APIRecruiter] Sending API telegram {template.tgid} to '{target}'...")
                                    tg_query = sans.Telegram(
                                        client=self.client_key,
                                        tgid=str(template.tgid),
                                        key=template.key,
                                        to=target
                                    )
                                    response = await client.get(tg_query, auth=limiter)
                                    self.sent_count += 1
                                    print(f"[APIRecruiter] Dispatched telegram {template.tgid} to {target} (status: {response.status_code})")
                                except httpx.ReadTimeout:
                                    print(f"[APIRecruiter] Request timed out sending to {target}, skipping target.")
                                except Exception as err:
                                    print(f"[APIRecruiter] Error sending telegram to {target}: {err}")

                                dispatched = True
                                # NS mandatory rate limit pause
                                await asyncio.sleep(self.RECRUITMENT_DELAY)
                                break

                    if dispatched:
                        continue

                    # Queue is empty: wait for next incoming recruit event
                    try:
                        await asyncio.wait_for(self.bot.wait_for('new_recruit'), timeout=60.0)
                    except asyncio.TimeoutError:
                        pass
        except asyncio.CancelledError:
            print("[APIRecruiter] API recruitment loop canceled.")
