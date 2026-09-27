import discord
from discord import ui
from discord.ext import commands
import typing
import asyncio
from datetime import datetime, date

from .guilds import GuildManager, Guild
from .template import TemplateManager, TGTemplate, UserTemplates
from .recruit import RecruitmentManager, WA_BACKLOG_SIZE, BACKLOG_SIZE, RecruiterSession
from .stats import StatsTracker
from .api import APIRecruiter, APITGTemplate, APITemplates
import utility as util
from pagination import Pagination

# ==========================================
# Modals for User Input
# ==========================================

class RecruitModal(ui.Modal, title="Start Recruitment Session"):
    interval = ui.TextInput(
        label="Cooldown Interval (seconds)",
        default="60",
        placeholder="Minimum 30s (recommended: 60-180)",
        min_length=2,
        max_length=4
    )
    container = ui.TextInput(
        label="Browser Container Name (Optional)",
        required=False,
        placeholder="e.g. MyNationContainer for Containerise",
        max_length=50
    )

    def __init__(self, gui_cog: "GuiManager"):
        super().__init__()
        self.gui_cog = gui_cog

    async def on_submit(self, interaction: discord.Interaction):
        try:
            sec = int(self.interval.value.strip())
            if sec < 30:
                await interaction.response.send_message("Cooldown interval cannot be less than 30 seconds.", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message("Invalid interval number.", ephemeral=True)
            return

        container_name = self.container.value.strip() if self.container.value else None
        recruiter: RecruitmentManager = self.gui_cog.bot.get_cog("RecruitmentManager")
        templates_cog: TemplateManager = self.gui_cog.bot.get_cog("TemplateManager")

        key = (interaction.guild.id, interaction.user.id)
        if key not in templates_cog.user_templates:
            await interaction.response.send_message("You have no templates configured! Click **➕ Add Template** or **⚡ Quick Setup** first.", ephemeral=True)
            return

        if key in recruiter.recruiters:
            await interaction.response.send_message("You already have an active recruitment session running! Click **⏹️ Stop Recruiting** first.", ephemeral=True)
            return

        session = RecruiterSession(
            guild_id=interaction.guild.id,
            user_id=interaction.user.id,
            user=interaction.user,
            channel=interaction.channel,
            interval=sec,
            container=container_name,
            indexes=[0, 0, 0]
        )
        recruiter.recruiters[key] = session

        await interaction.response.send_message(
            f"🎯 Recruitment session started (strict wait time: **{sec}s**)! Preparing your first list...",
            ephemeral=True
        )

        dispatched = await recruiter.dispatch_next_batch(session)
        if not dispatched:
            await interaction.followup.send(
                "📭 The nation queue is currently empty. As soon as nations are founded or join WA, click **Get Next List**.",
                ephemeral=True
            )

class AddTemplateModal(ui.Modal, title="Add Telegram Template"):
    destination = ui.TextInput(
        label="Destination (wa, newfound, refound)",
        placeholder="wa, newfound, or refound",
        min_length=2,
        max_length=10
    )
    category = ui.TextInput(
        label="Category Label",
        placeholder="e.g. standard_wa or intro_greeting",
        max_length=30
    )
    tgid = ui.TextInput(
        label="NationStates Template ID",
        placeholder="e.g. %TEMPLATE-12345% or 12345",
        max_length=30
    )

    def __init__(self, gui_cog: "GuiManager"):
        super().__init__()
        self.gui_cog = gui_cog

    async def on_submit(self, interaction: discord.Interaction):
        dest = self.destination.value.strip().lower()
        if dest not in ("wa", "newfound", "refound"):
            await interaction.response.send_message("Destination must be one of `wa`, `newfound`, or `refound`.", ephemeral=True)
            return

        numeric_id = util.parse_template_id(self.tgid.value.strip())
        if numeric_id is None:
            await interaction.response.send_message("Invalid Template ID. Provide numbers or `%TEMPLATE-12345%`.", ephemeral=True)
            return

        templates_cog: TemplateManager = self.gui_cog.bot.get_cog("TemplateManager")
        key = (interaction.guild.id, interaction.user.id)
        if key not in templates_cog.user_templates:
            templates_cog.user_templates[key] = UserTemplates([], [], [])

        tpls = templates_cog.user_templates[key]
        clean_cat = self.category.value.strip().replace(":", "-")
        tpl = TGTemplate(category=clean_cat, tgid=numeric_id)

        if dest == "wa":
            tpls.wa.append(tpl)
        elif dest == "newfound":
            tpls.newfound.append(tpl)
        elif dest == "refound":
            tpls.refound.append(tpl)

        templates_cog.sync(interaction.guild.id, interaction.user.id, tpls)
        await interaction.response.send_message(f"✅ Added **{dest.upper()}** template `{clean_cat}` with ID `{numeric_id}`!", ephemeral=True)

class QuickSetupModal(ui.Modal, title="Quick Generic Template Setup"):
    tgid = ui.TextInput(
        label="Template ID (applied to WA, New, Refound)",
        placeholder="e.g. %TEMPLATE-12345% or 12345",
        max_length=30
    )

    def __init__(self, gui_cog: "GuiManager"):
        super().__init__()
        self.gui_cog = gui_cog

    async def on_submit(self, interaction: discord.Interaction):
        numeric_id = util.parse_template_id(self.tgid.value.strip())
        if numeric_id is None:
            await interaction.response.send_message("Invalid Template ID. Provide numbers or `%TEMPLATE-12345%`.", ephemeral=True)
            return

        templates_cog: TemplateManager = self.gui_cog.bot.get_cog("TemplateManager")
        key = (interaction.guild.id, interaction.user.id)
        if key not in templates_cog.user_templates:
            templates_cog.user_templates[key] = UserTemplates([], [], [])

        tpls = templates_cog.user_templates[key]
        for lst in (tpls.wa, tpls.newfound, tpls.refound):
            lst.append(TGTemplate(category="generic", tgid=numeric_id))

        templates_cog.sync(interaction.guild.id, interaction.user.id, tpls)
        await interaction.response.send_message(f"⚡ Configured generic template `{numeric_id}` for WA, newfound, and refound destinations!", ephemeral=True)

class ServerConfigModal(ui.Modal, title="Server Recruitment Configuration"):
    admin_role = ui.TextInput(
        label="Admin Role (Name or ID)",
        placeholder="e.g. Administrator or 123456789"
    )
    recruit_role = ui.TextInput(
        label="Recruiter Role (Name or ID)",
        placeholder="e.g. Recruiter or 987654321"
    )
    wa_toggle = ui.TextInput(
        label="Recruit WA? (yes/no)",
        default="yes",
        max_length=5
    )
    newfound_toggle = ui.TextInput(
        label="Recruit Newly Founded? (yes/no)",
        default="yes",
        max_length=5
    )
    refound_toggle = ui.TextInput(
        label="Recruit Refounded? (yes/no)",
        default="yes",
        max_length=5
    )

    def __init__(self, gui_cog: "GuiManager"):
        super().__init__()
        self.gui_cog = gui_cog

    def find_role(self, guild: discord.Guild, query: str) -> typing.Optional[discord.Role]:
        query = query.strip().lower()
        if query.isdigit():
            role = guild.get_role(int(query))
            if role:
                return role
        for r in guild.roles:
            if r.name.lower() == query:
                return r
        return None

    async def on_submit(self, interaction: discord.Interaction):
        admin = self.find_role(interaction.guild, self.admin_role.value)
        if not admin:
            await interaction.response.send_message(f"Could not find admin role: `{self.admin_role.value}`.", ephemeral=True)
            return

        recruit = self.find_role(interaction.guild, self.recruit_role.value)
        if not recruit:
            await interaction.response.send_message(f"Could not find recruiter role: `{self.recruit_role.value}`.", ephemeral=True)
            return

        wa_val = self.wa_toggle.value.strip().lower() in ("yes", "y", "true", "1")
        new_val = self.newfound_toggle.value.strip().lower() in ("yes", "y", "true", "1")
        ref_val = self.refound_toggle.value.strip().lower() in ("yes", "y", "true", "1")

        guild_manager: GuildManager = self.gui_cog.bot.get_cog("GuildManager")
        new_guild = Guild(
            admin_role=admin.id,
            recruit_role=recruit.id,
            recruit_wa=wa_val,
            recruit_newfounds=new_val,
            recruit_refounds=ref_val
        )
        guild_manager.sync(interaction.guild.id, new_guild)
        guild_manager.guilds[interaction.guild.id] = new_guild

        recruiter: RecruitmentManager = self.gui_cog.bot.get_cog("RecruitmentManager")
        if recruiter:
            recruiter.update_backlog()

        await interaction.response.send_message("🛠️ Server recruitment configuration updated successfully!", ephemeral=True)

class ForceStopModal(ui.Modal, title="Force Stop Recruiter Session"):
    target_user = ui.TextInput(
        label="Member Name, Tag, or User ID",
        placeholder="e.g. Username or 123456789"
    )

    def __init__(self, gui_cog: "GuiManager"):
        super().__init__()
        self.gui_cog = gui_cog

    async def on_submit(self, interaction: discord.Interaction):
        query = self.target_user.value.strip().lower()
        member = None
        if query.isdigit():
            member = interaction.guild.get_member(int(query))
        if not member:
            for m in interaction.guild.members:
                if m.name.lower() == query or m.display_name.lower() == query or str(m).lower() == query:
                    member = m
                    break

        if not member:
            await interaction.response.send_message(f"Could not find member `{self.target_user.value}`.", ephemeral=True)
            return

        recruiter: RecruitmentManager = self.gui_cog.bot.get_cog("RecruitmentManager")
        key = (interaction.guild.id, member.id)
        if key not in recruiter.recruiters:
            await interaction.response.send_message(f"{member.display_name} does not have an active recruitment session.", ephemeral=True)
            return

        session = recruiter.recruiters.pop(key)
        if session.last_message:
            try:
                view = discord.ui.View.from_message(session.last_message)
                for item in view.children:
                    if isinstance(item, discord.ui.Button) and not item.url:
                        item.disabled = True
                await session.last_message.edit(view=view)
            except Exception:
                pass
        await interaction.response.send_message(f"🛑 Successfully stopped recruitment session for {member.mention}!", ephemeral=True)

class APIClientModal(ui.Modal, title="Set API Client Key"):
    client_key = ui.TextInput(
        label="NationStates API Client Key",
        placeholder="Paste your client key obtained from NS moderators"
    )

    def __init__(self, gui_cog: "GuiManager"):
        super().__init__()
        self.gui_cog = gui_cog

    async def on_submit(self, interaction: discord.Interaction):
        api_cog: APIRecruiter = self.gui_cog.bot.get_cog("APIRecruiter")
        api_cog.client_key = self.client_key.value.strip()
        api_cog.sync()
        await interaction.response.send_message("🔑 API Client Key updated and saved successfully.", ephemeral=True)

class APIAddTemplateModal(ui.Modal, title="Add API Telegram Template"):
    destination = ui.TextInput(
        label="Destination (wa, newfound, refound)",
        placeholder="wa, newfound, or refound"
    )
    category = ui.TextInput(
        label="Category Label",
        placeholder="e.g. api_wa"
    )
    tgid = ui.TextInput(
        label="Template ID",
        placeholder="e.g. %TEMPLATE-12345% or 12345"
    )
    key = ui.TextInput(
        label="Secret Key",
        placeholder="Secret key generated by NS when sending to tag:api"
    )

    def __init__(self, gui_cog: "GuiManager"):
        super().__init__()
        self.gui_cog = gui_cog

    async def on_submit(self, interaction: discord.Interaction):
        dest = self.destination.value.strip().lower()
        if dest not in ("wa", "newfound", "refound"):
            await interaction.response.send_message("Destination must be wa, newfound, or refound.", ephemeral=True)
            return

        numeric_id = util.parse_template_id(self.tgid.value.strip())
        if numeric_id is None:
            await interaction.response.send_message("Invalid Template ID.", ephemeral=True)
            return

        api_cog: APIRecruiter = self.gui_cog.bot.get_cog("APIRecruiter")
        clean_cat = self.category.value.strip().replace(":", "-")
        tpl = APITGTemplate(category=clean_cat, tgid=numeric_id, key=self.key.value.strip())

        if dest == "wa":
            api_cog.templates.wa.append(tpl)
        elif dest == "newfound":
            api_cog.templates.newfound.append(tpl)
        elif dest == "refound":
            api_cog.templates.refound.append(tpl)

        api_cog.sync()
        await interaction.response.send_message(f"✅ Added API **{dest.upper()}** template `{clean_cat}` (`{numeric_id}`)!", ephemeral=True)

class APISetupModal(ui.Modal, title="Quick Generic API Template Setup"):
    tgid = ui.TextInput(
        label="Template ID (applied to WA, New, Refound)",
        placeholder="e.g. %TEMPLATE-12345% or 12345"
    )
    key = ui.TextInput(
        label="Secret Key",
        placeholder="Secret key generated by NS when sending to tag:api"
    )

    def __init__(self, gui_cog: "GuiManager"):
        super().__init__()
        self.gui_cog = gui_cog

    async def on_submit(self, interaction: discord.Interaction):
        numeric_id = util.parse_template_id(self.tgid.value.strip())
        if numeric_id is None:
            await interaction.response.send_message("Invalid Template ID.", ephemeral=True)
            return

        api_cog: APIRecruiter = self.gui_cog.bot.get_cog("APIRecruiter")
        for lst in (api_cog.templates.wa, api_cog.templates.newfound, api_cog.templates.refound):
            lst.append(APITGTemplate(category="generic", tgid=numeric_id, key=self.key.value.strip()))

        api_cog.sync()
        await interaction.response.send_message(f"⚡ Configured generic API template `{numeric_id}` for WA, newfound, and refound destinations!", ephemeral=True)

# ==========================================
# Views (Interactive Buttons)
# ==========================================

class ControlPanelView(ui.View):
    def __init__(self, gui_cog: "GuiManager"):
        super().__init__(timeout=None)
        self.gui_cog = gui_cog

    # Row 0: Recruitment Controls
    @ui.button(label="Start Recruiting", style=discord.ButtonStyle.success, emoji="▶️", row=0)
    async def btn_recruit(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(RecruitModal(self.gui_cog))

    @ui.button(label="Stop Recruiting", style=discord.ButtonStyle.danger, emoji="⏹️", row=0)
    async def btn_stop(self, interaction: discord.Interaction, button: ui.Button):
        recruiter: RecruitmentManager = self.gui_cog.bot.get_cog("RecruitmentManager")
        key = (interaction.guild.id, interaction.user.id)
        if key not in recruiter.recruiters:
            await interaction.response.send_message("You do not have an active recruitment session running.", ephemeral=True)
            return
        session = recruiter.recruiters.pop(key)
        if session.last_message:
            try:
                view = discord.ui.View.from_message(session.last_message)
                for item in view.children:
                    if isinstance(item, discord.ui.Button) and not item.url:
                        item.disabled = True
                await session.last_message.edit(view=view)
            except Exception:
                pass
        await interaction.response.send_message("🛑 Your recruitment session has been stopped.", ephemeral=True)

    @ui.button(label="View Queue", style=discord.ButtonStyle.secondary, emoji="📊", row=0)
    async def btn_queue(self, interaction: discord.Interaction, button: ui.Button):
        recruiter: RecruitmentManager = self.gui_cog.bot.get_cog("RecruitmentManager")
        recruiter._ensure_guild_queues(interaction.guild.id)
        wa_len = len(recruiter.wa_queue[interaction.guild.id].nations)
        new_len = len(recruiter.newfound_queue[interaction.guild.id].nations)
        ref_len = len(recruiter.refound_queue[interaction.guild.id].nations)

        embed = discord.Embed(
            title=f"📊 Queue Backlog — {interaction.guild.name}",
            color=0x3584e4,
            timestamp=datetime.now()
        )
        embed.add_field(name="World Assembly (WA)", value=f"`{wa_len}` / {WA_BACKLOG_SIZE}", inline=True)
        embed.add_field(name="Newly Founded", value=f"`{new_len}` / {BACKLOG_SIZE}", inline=True)
        embed.add_field(name="Refounded", value=f"`{ref_len}` / {BACKLOG_SIZE}", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Cooldown Guide", style=discord.ButtonStyle.secondary, emoji="⏱️", row=0)
    async def btn_timer(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(
            title="⏱️ NationStates Recruitment Cooldown Guidelines",
            description="Recruiting cooldowns are enforced by NationStates based on how old your sending nation is:",
            color=0xf6d32d
        )
        embed.add_field(name="Nations < 8 days old", value="**180 seconds** (3 minutes) cooldown", inline=False)
        embed.add_field(name="Nations 8 – 30 days old", value="**120 seconds** (2 minutes) cooldown", inline=False)
        embed.add_field(name="Nations > 30 days old", value="**60 seconds** (1 minute) cooldown", inline=False)
        embed.add_field(name="API Recruitment", value="Always strictly **180 seconds** per telegram", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    # Row 1: Template Management
    @ui.button(label="My Templates", style=discord.ButtonStyle.primary, emoji="📋", row=1)
    async def btn_templates(self, interaction: discord.Interaction, button: ui.Button):
        templates_cog: TemplateManager = self.gui_cog.bot.get_cog("TemplateManager")
        key = (interaction.guild.id, interaction.user.id)
        if key not in templates_cog.user_templates:
            await interaction.response.send_message("You have no templates configured! Click **➕ Add Template** or **⚡ Quick Setup**.", ephemeral=True)
            return

        tpls = templates_cog.user_templates[key]
        embed = discord.Embed(title=f"Telegram Templates for {interaction.user.display_name}", color=0x3584e4)

        if tpls.wa:
            desc = "\n".join([f"• **{t.category}**: `%{t.tgid}%` — [View Stats](https://www.nationstates.net/tgcategory={t.category}/page=tg/tgid={t.tgid})" for t in tpls.wa])
            embed.add_field(name="World Assembly (WA)", value=desc, inline=False)

        if tpls.newfound:
            desc = "\n".join([f"• **{t.category}**: `%{t.tgid}%` — [View Stats](https://www.nationstates.net/tgcategory={t.category}/page=tg/tgid={t.tgid})" for t in tpls.newfound])
            embed.add_field(name="Newly Founded", value=desc, inline=False)

        if tpls.refound:
            desc = "\n".join([f"• **{t.category}**: `%{t.tgid}%` — [View Stats](https://www.nationstates.net/tgcategory={t.category}/page=tg/tgid={t.tgid})" for t in tpls.refound])
            embed.add_field(name="Refounded", value=desc, inline=False)

        if not embed.fields:
            await interaction.response.send_message("No templates saved. Use **➕ Add Template** or **⚡ Quick Setup**.", ephemeral=True)
            return

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Add Template", style=discord.ButtonStyle.secondary, emoji="➕", row=1)
    async def btn_add_tpl(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(AddTemplateModal(self.gui_cog))

    @ui.button(label="Quick Setup", style=discord.ButtonStyle.secondary, emoji="⚡", row=1)
    async def btn_quick_setup(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(QuickSetupModal(self.gui_cog))

    @ui.button(label="Clear Templates", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def btn_clear_tpls(self, interaction: discord.Interaction, button: ui.Button):
        templates_cog: TemplateManager = self.gui_cog.bot.get_cog("TemplateManager")
        key = (interaction.guild.id, interaction.user.id)
        if key in templates_cog.user_templates:
            del templates_cog.user_templates[key]

        database = self.gui_cog.bot.get_cog("Database")
        cursor = database.db.cursor()
        cursor.execute("DELETE FROM user_templates WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, interaction.user.id))
        database.db.commit()
        cursor.close()

        await interaction.response.send_message("🗑️ All your templates in this server have been cleared.", ephemeral=True)

    # Row 2: Statistics & Leaderboard
    @ui.button(label="Recruiter Leaderboard", style=discord.ButtonStyle.primary, emoji="🏆", row=2)
    async def btn_stats(self, interaction: discord.Interaction, button: ui.Button):
        stats_cog: StatsTracker = self.gui_cog.bot.get_cog("StatsTracker")
        recruiter_totals: dict[str, list[int]] = {}

        for (guild_id, user_id, day), stat in stats_cog.stat_map.items():
            if guild_id != interaction.guild.id:
                continue
            member = interaction.guild.get_member(user_id)
            name = member.display_name if member else f"User ID {user_id}"

            if name not in recruiter_totals:
                recruiter_totals[name] = [0, 0, 0, 0]

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
            await interaction.response.send_message("No recruitment telegrams recorded yet for this server.", ephemeral=True)
            return

        PER_PAGE = 10
        total_pages = Pagination.compute_total_pages(len(recruiters), PER_PAGE)

        emb = discord.Embed(
            title=f"🏆 Recruitment Leaderboard — {interaction.guild.name}",
            description="Showing all-time server recruitment statistics:\n\n",
            color=0x9141ac
        )
        for rank, (name, total, wa, new, ref) in enumerate(recruiters[:PER_PAGE], start=1):
            emb.description += f"**#{rank}** `{name}` — **{total:,}** total (`{wa:,}` WA, `{new:,}` new, `{ref:,}` refound)\n"

        emb.set_footer(text=f"Page 1 of {total_pages} | Searendipity")
        await interaction.response.send_message(embed=emb, ephemeral=True)

    # Row 3: Admin & API
    @ui.button(label="Server Config", style=discord.ButtonStyle.secondary, emoji="⚙️", row=3)
    async def btn_config(self, interaction: discord.Interaction, button: ui.Button):
        guilds_cog: GuildManager = self.gui_cog.bot.get_cog("GuildManager")
        if interaction.user.id != interaction.guild.owner_id:
            cfg = guilds_cog.guilds.get(interaction.guild.id)
            if not cfg or interaction.user.get_role(cfg.admin_role) is None:
                await interaction.response.send_message("Only the server owner or administrators can configure recruitment settings.", ephemeral=True)
                return
        await interaction.response.send_modal(ServerConfigModal(self.gui_cog))

    @ui.button(label="Force Stop User", style=discord.ButtonStyle.danger, emoji="🛑", row=3)
    async def btn_forcestop(self, interaction: discord.Interaction, button: ui.Button):
        guilds_cog: GuildManager = self.gui_cog.bot.get_cog("GuildManager")
        if interaction.user.id != interaction.guild.owner_id:
            cfg = guilds_cog.guilds.get(interaction.guild.id)
            if not cfg or interaction.user.get_role(cfg.admin_role) is None:
                await interaction.response.send_message("Only administrators can force-stop another user's session.", ephemeral=True)
                return
        await interaction.response.send_modal(ForceStopModal(self.gui_cog))

    @ui.button(label="API Recruiter", style=discord.ButtonStyle.secondary, emoji="🤖", row=3)
    async def btn_api_panel(self, interaction: discord.Interaction, button: ui.Button):
        if interaction.user.id != self.gui_cog.bot.owner_id:
            await interaction.response.send_message("Only the bot administrator can manage API recruitment.", ephemeral=True)
            return

        api_cog: APIRecruiter = self.gui_cog.bot.get_cog("APIRecruiter")
        is_running = bool(api_cog.recruitment_task and not api_cog.recruitment_task.done())
        embed = discord.Embed(
            title="🤖 Automated API Recruitment Control Panel",
            description="Manage background automated NationStates API recruitment.",
            color=0x2ec27e if is_running else 0xe01b24
        )
        embed.add_field(name="Status", value="🟢 **Active**" if is_running else "🔴 **Stopped**", inline=True)
        embed.add_field(name="Server Bound", value=str(api_cog.guild or "None"), inline=True)
        embed.add_field(name="Telegrams Sent", value=f"`{api_cog.sent_count:,}`", inline=True)
        embed.add_field(name="WA Templates", value=str(len(api_cog.templates.wa)), inline=True)
        embed.add_field(name="Newfound Templates", value=str(len(api_cog.templates.newfound)), inline=True)
        embed.add_field(name="Refound Templates", value=str(len(api_cog.templates.refound)), inline=True)

        await interaction.response.send_message(embed=embed, view=APIPanelView(self.gui_cog), ephemeral=True)

class APIPanelView(ui.View):
    def __init__(self, gui_cog: "GuiManager"):
        super().__init__(timeout=None)
        self.gui_cog = gui_cog

    @ui.button(label="Bind This Server", style=discord.ButtonStyle.primary, emoji="🔗", row=0)
    async def btn_bind(self, interaction: discord.Interaction, button: ui.Button):
        api_cog: APIRecruiter = self.gui_cog.bot.get_cog("APIRecruiter")
        api_cog.guild = interaction.guild.id
        api_cog.sync()
        await interaction.response.send_message(f"✅ Bound API recruitment to **{interaction.guild.name}** (`{interaction.guild.id}`).", ephemeral=True)

    @ui.button(label="Set Client Key", style=discord.ButtonStyle.secondary, emoji="🔑", row=0)
    async def btn_key(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(APIClientModal(self.gui_cog))

    @ui.button(label="Add API Template", style=discord.ButtonStyle.secondary, emoji="➕", row=1)
    async def btn_add_tpl(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(APIAddTemplateModal(self.gui_cog))

    @ui.button(label="Quick API Setup", style=discord.ButtonStyle.secondary, emoji="⚡", row=1)
    async def btn_quick_setup(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.send_modal(APISetupModal(self.gui_cog))

    @ui.button(label="View API Templates", style=discord.ButtonStyle.primary, emoji="📋", row=1)
    async def btn_view_tpls(self, interaction: discord.Interaction, button: ui.Button):
        api_cog: APIRecruiter = self.gui_cog.bot.get_cog("APIRecruiter")
        embed = discord.Embed(title="🔑 Registered API Recruitment Templates", color=0x3584e4)

        if api_cog.templates.wa:
            desc = "\n".join([f"• **{t.category}**: `%{t.tgid}%` (key: `{t.key}`) — [Link](https://www.nationstates.net/tgcategory={t.category}/page=tg/tgid={t.tgid})" for t in api_cog.templates.wa])
            embed.add_field(name="World Assembly (WA)", value=desc, inline=False)
        if api_cog.templates.newfound:
            desc = "\n".join([f"• **{t.category}**: `%{t.tgid}%` (key: `{t.key}`) — [Link](https://www.nationstates.net/tgcategory={t.category}/page=tg/tgid={t.tgid})" for t in api_cog.templates.newfound])
            embed.add_field(name="Newly Founded", value=desc, inline=False)
        if api_cog.templates.refound:
            desc = "\n".join([f"• **{t.category}**: `%{t.tgid}%` (key: `{t.key}`) — [Link](https://www.nationstates.net/tgcategory={t.category}/page=tg/tgid={t.tgid})" for t in api_cog.templates.refound])
            embed.add_field(name="Refounded", value=desc, inline=False)

        if not embed.fields:
            await interaction.response.send_message("No API templates registered yet.", ephemeral=True)
            return
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label="Start API Loop", style=discord.ButtonStyle.success, emoji="▶️", row=2)
    async def btn_start_api(self, interaction: discord.Interaction, button: ui.Button):
        api_cog: APIRecruiter = self.gui_cog.bot.get_cog("APIRecruiter")
        if not api_cog.guild:
            await interaction.response.send_message("Please click **Bind This Server** first.", ephemeral=True)
            return
        if not api_cog.client_key:
            await interaction.response.send_message("Please click **Set Client Key** first.", ephemeral=True)
            return
        if api_cog.recruitment_task and not api_cog.recruitment_task.done():
            await interaction.response.send_message("API recruitment is already running.", ephemeral=True)
            return

        api_cog.recruitment_task = asyncio.create_task(api_cog.telegram_loop())
        await interaction.response.send_message("🟢 Automated API recruitment loop started successfully!", ephemeral=True)

    @ui.button(label="Stop API Loop", style=discord.ButtonStyle.danger, emoji="⏹️", row=2)
    async def btn_stop_api(self, interaction: discord.Interaction, button: ui.Button):
        api_cog: APIRecruiter = self.gui_cog.bot.get_cog("APIRecruiter")
        if not api_cog.recruitment_task or api_cog.recruitment_task.done():
            await interaction.response.send_message("API recruitment is not running.", ephemeral=True)
            return
        api_cog.recruitment_task.cancel()
        api_cog.recruitment_task = None
        await interaction.response.send_message("🔴 Automated API recruitment loop stopped.", ephemeral=True)

# ==========================================
# GuiManager Cog & ?start Command
# ==========================================

class GuiManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def create_dashboard_embed(self, guild: discord.Guild, user: discord.User | discord.Member) -> discord.Embed:
        recruiter: RecruitmentManager = self.bot.get_cog("RecruitmentManager")
        templates_cog: TemplateManager = self.bot.get_cog("TemplateManager")

        recruiter._ensure_guild_queues(guild.id)
        wa_len = len(recruiter.wa_queue[guild.id].nations)
        new_len = len(recruiter.newfound_queue[guild.id].nations)
        ref_len = len(recruiter.refound_queue[guild.id].nations)

        user_key = (guild.id, user.id)
        is_recruiting = user_key in recruiter.recruiters

        tpl_count_str = "None configured"
        if user_key in templates_cog.user_templates:
            tpls = templates_cog.user_templates[user_key]
            tpl_count_str = f"{len(tpls.wa)} WA, {len(tpls.newfound)} New, {len(tpls.refound)} Refound"

        embed = discord.Embed(
            title="🌊 Searendipity Recruitment Control Panel",
            description=f"Welcome, {user.mention}! Use the buttons below to manage templates, monitor live nation queues, and start recruiting.",
            color=0x1c71d8,
            timestamp=datetime.now()
        )
        embed.add_field(
            name="📡 Live Queues",
            value=f"• **WA Joins:** `{wa_len}`\n• **Newfounds:** `{new_len}`\n• **Refounds:** `{ref_len}`",
            inline=True
        )
        embed.add_field(
            name="👤 Your Status",
            value=f"• **Session:** {'🟢 Active' if is_recruiting else '⚪ Idle'}\n• **Templates:** {tpl_count_str}",
            inline=True
        )
        embed.set_footer(text=f"Nation: {recruiter.nation} | Server: {guild.name}")
        return embed

    @commands.command(name="start", aliases=["panel", "gui", "menu", "dashboard"])
    async def start(self, ctx: commands.Context):
        """Open the interactive graphical recruitment dashboard."""
        if not ctx.guild:
            await ctx.send("The control panel can only be opened inside a Discord server.")
            return

        embed = self.create_dashboard_embed(ctx.guild, ctx.author)
        view = ControlPanelView(self)
        await ctx.send(embed=embed, view=view)
