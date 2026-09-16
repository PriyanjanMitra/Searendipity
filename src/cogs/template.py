from dataclasses import dataclass
from discord.ext import commands
from discord import app_commands
import typing
import discord
from .db import Database
from .guilds import GuildManager
import utility as util

class TGTemplate:
    category: str  # The label for this telegram template (e.g. "generic", "wa_invite", "greeting_a")
    tgid: int      # The numeric NationStates Template ID

    def __init__(self, category: str = "", tgid: int = 0):
        self.category = category
        self.tgid = tgid

    @staticmethod
    def from_string(string: str) -> "TGTemplate":
        split = string.split(":", 1)
        category = split[0]
        tgid = int(split[1]) if len(split) > 1 and split[1].isdigit() else 0
        return TGTemplate(category, tgid)

    def to_string(self) -> str:
        return f"{self.category}:{self.tgid}"

@dataclass
class UserTemplates:
    wa: list[TGTemplate]         # Templates for new WA members
    newfound: list[TGTemplate]   # Templates for newfounds
    refound: list[TGTemplate]    # Templates for refounds

    @staticmethod
    def from_strings(wa: str, newfound: str, refound: str) -> "UserTemplates":
        wa_list = [TGTemplate.from_string(s) for s in wa.split(",") if s.strip()]
        newfound_list = [TGTemplate.from_string(s) for s in newfound.split(",") if s.strip()]
        refound_list = [TGTemplate.from_string(s) for s in refound.split(",") if s.strip()]
        return UserTemplates(wa_list, newfound_list, refound_list)

    def to_strings(self) -> typing.Tuple[str, str, str]:
        wa = ",".join([t.to_string() for t in self.wa])
        newfound = ",".join([t.to_string() for t in self.newfound])
        refound = ",".join([t.to_string() for t in self.refound])
        return (wa, newfound, refound)

class TemplateManager(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.user_templates: dict[tuple[int, int], UserTemplates] = {}
        self.load()

    def load(self):
        database: Database = self.bot.get_cog('Database')
        if not database:
            return
        cursor = database.db.cursor()
        cursor.execute("SELECT guild_id, user_id, wa, newfound, refound FROM user_templates")
        data = cursor.fetchall()

        for row in data:
            self.user_templates[(row[0], row[1])] = UserTemplates.from_strings(row[2], row[3], row[4])
        cursor.close()

    def sync(self, guild_id: int, user_id: int, templates: UserTemplates):
        database: Database = self.bot.get_cog('Database')
        cursor = database.db.cursor()

        wa, newfounds, refounds = templates.to_strings()
        unique_id = f"{guild_id}-{user_id}"
        data = (unique_id, guild_id, user_id, wa, newfounds, refounds)
        cursor.execute("INSERT OR REPLACE INTO user_templates VALUES (?, ?, ?, ?, ?, ?)", data)
        database.db.commit()
        cursor.close()

    @app_commands.command(name="templates", description="List your registered recruitment telegram templates in this server.")
    async def templates(self, interaction: discord.Interaction):
        guilds: GuildManager = self.bot.get_cog('GuildManager')
        if not await guilds.check_recruit_permissions(interaction):
            return

        key = (interaction.guild.id, interaction.user.id)
        if key not in self.user_templates:
            await interaction.response.send_message("You do not have any templates configured in this server. Use `/setup` or `/add` to register one.", ephemeral=True)
            return

        user_tpls = self.user_templates[key]
        embed = discord.Embed(title=f"Telegram Templates for {interaction.user.display_name}", color=0x3584e4)

        if user_tpls.wa:
            desc = "\n".join([f"• **{t.category}**: `%{t.tgid}%` — [View Stats](https://www.nationstates.net/tgcategory={t.category}/page=tg/tgid={t.tgid})" for t in user_tpls.wa])
            embed.add_field(name="World Assembly (WA)", value=desc, inline=False)

        if user_tpls.newfound:
            desc = "\n".join([f"• **{t.category}**: `%{t.tgid}%` — [View Stats](https://www.nationstates.net/tgcategory={t.category}/page=tg/tgid={t.tgid})" for t in user_tpls.newfound])
            embed.add_field(name="Newly Founded", value=desc, inline=False)

        if user_tpls.refound:
            desc = "\n".join([f"• **{t.category}**: `%{t.tgid}%` — [View Stats](https://www.nationstates.net/tgcategory={t.category}/page=tg/tgid={t.tgid})" for t in user_tpls.refound])
            embed.add_field(name="Refounded", value=desc, inline=False)

        if not embed.fields:
            await interaction.response.send_message("You have no templates saved. Register one using `/add` or `/setup`.", ephemeral=True)
            return

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="add", description="Add a new template to a specific recruitment category.")
    @app_commands.describe(
        destination="Target category: wa, newfound, or refound",
        category="Label name for this template (e.g. standard_wa)",
        tgid="NationStates template ID (e.g. %TEMPLATE-12345% or 12345)"
    )
    @app_commands.choices(destination=[
        app_commands.Choice(name="World Assembly (WA)", value="wa"),
        app_commands.Choice(name="Newly Founded", value="newfound"),
        app_commands.Choice(name="Refounded", value="refound")
    ])
    async def add(self, interaction: discord.Interaction, destination: app_commands.Choice[str], category: str, tgid: str):
        guilds: GuildManager = self.bot.get_cog('GuildManager')
        if not await guilds.check_recruit_permissions(interaction):
            return

        numeric_id = util.parse_template_id(tgid)
        if numeric_id is None:
            await interaction.response.send_message("Invalid Template ID! Provide a numeric ID or `%TEMPLATE-12345%` format.", ephemeral=True)
            return

        key = (interaction.guild.id, interaction.user.id)
        if key not in self.user_templates:
            self.user_templates[key] = UserTemplates([], [], [])

        tpls = self.user_templates[key]
        clean_cat = category.strip().replace(":", "-")
        tpl = TGTemplate(category=clean_cat, tgid=numeric_id)

        dest = destination.value
        if dest == "wa":
            tpls.wa.append(tpl)
        elif dest == "newfound":
            tpls.newfound.append(tpl)
        elif dest == "refound":
            tpls.refound.append(tpl)

        self.sync(interaction.guild.id, interaction.user.id, tpls)
        await interaction.response.send_message(f"Added **{dest.upper()}** template `{clean_cat}` with ID `{numeric_id}` successfully!", ephemeral=True)

    @app_commands.command(name="setup", description="Register a generic template across all three destinations (WA, newfound, refound).")
    @app_commands.describe(tgid="NationStates template ID (e.g. %TEMPLATE-12345% or 12345)")
    async def setup(self, interaction: discord.Interaction, tgid: str):
        guilds: GuildManager = self.bot.get_cog('GuildManager')
        if not await guilds.check_recruit_permissions(interaction):
            return

        numeric_id = util.parse_template_id(tgid)
        if numeric_id is None:
            await interaction.response.send_message("Invalid Template ID! Provide a numeric ID or `%TEMPLATE-12345%` format.", ephemeral=True)
            return

        key = (interaction.guild.id, interaction.user.id)
        if key not in self.user_templates:
            self.user_templates[key] = UserTemplates([], [], [])

        tpls = self.user_templates[key]
        for lst in (tpls.wa, tpls.newfound, tpls.refound):
            lst.append(TGTemplate(category="generic", tgid=numeric_id))

        self.sync(interaction.guild.id, interaction.user.id, tpls)
        await interaction.response.send_message(f"Generic template with ID `{numeric_id}` configured for all destinations!", ephemeral=True)

    @app_commands.command(name="remove", description="Remove all templates matching a specific category name.")
    @app_commands.describe(category="Category name to remove")
    async def remove(self, interaction: discord.Interaction, category: str):
        guilds: GuildManager = self.bot.get_cog('GuildManager')
        if not await guilds.check_recruit_permissions(interaction):
            return

        key = (interaction.guild.id, interaction.user.id)
        if key not in self.user_templates:
            await interaction.response.send_message("You have no templates configured in this server.", ephemeral=True)
            return

        tpls = self.user_templates[key]
        clean_cat = category.strip()
        removed = 0

        for target_list in [tpls.wa, tpls.newfound, tpls.refound]:
            to_del = [t for t in target_list if t.category == clean_cat]
            for t in to_del:
                target_list.remove(t)
                removed += 1

        self.sync(interaction.guild.id, interaction.user.id, tpls)
        await interaction.response.send_message(f"Removed {removed} template(s) matching category `{clean_cat}`.", ephemeral=True)

    @app_commands.command(name="clear", description="Clear all your registered templates in this server.")
    async def clear(self, interaction: discord.Interaction):
        guilds: GuildManager = self.bot.get_cog('GuildManager')
        if not await guilds.check_recruit_permissions(interaction):
            return

        key = (interaction.guild.id, interaction.user.id)
        if key in self.user_templates:
            del self.user_templates[key]

        database: Database = self.bot.get_cog('Database')
        cursor = database.db.cursor()
        cursor.execute("DELETE FROM user_templates WHERE guild_id = ? AND user_id = ?", (interaction.guild.id, interaction.user.id))
        database.db.commit()
        cursor.close()

        await interaction.response.send_message("All your templates in this server have been cleared.", ephemeral=True)
