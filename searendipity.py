#!/usr/bin/env python3
"""
Searendipity: The serendipitous NationStates recruitment and analytics suite.
Discord manual & API recruitment bot using prefix commands (default: ! or ?).
"""

import discord
import sqlite3
import sans
import argparse
import sys
import asyncio
from discord.ext import commands
from dotenv import dotenv_values

import utility as util
from src.cogs.db import Database
from src.cogs.guilds import GuildManager
from src.cogs.template import TemplateManager
from src.cogs.nation import NationListener
from src.cogs.recruit import RecruitmentManager
from src.cogs.stats import StatsTracker
from src.cogs.api import APIRecruiter

VERSION = "0.1.0"

class SearendipityBot(commands.Bot):
    def __init__(self, connection: sqlite3.Connection, nation: str, owner_id: int, prefixes: list[str]):
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True  # Required for reading prefix commands (! or ?)

        super().__init__(
            command_prefix=commands.when_mentioned_or(*prefixes),
            intents=intents,
            help_command=commands.DefaultHelpCommand(dm_help=False)
        )

        self.db_connection = connection
        self.nation = util.format_nation_or_region(nation)
        self.owner_id = owner_id
        self.prefixes = prefixes

    async def setup_hook(self):
        try:
            loop = asyncio.get_running_loop()
            loop.set_task_factory(asyncio.eager_task_factory)
        except Exception:
            pass

        await self.add_cog(Database(self, self.db_connection))
        await self.add_cog(GuildManager(self))
        await self.add_cog(TemplateManager(self))
        await self.add_cog(RecruitmentManager(self, self.nation))
        await self.add_cog(NationListener(self))
        await self.add_cog(StatsTracker(self))
        await self.add_cog(APIRecruiter(self))

    async def on_ready(self):
        print(f"==================================================")
        print(f"  Searendipity v{VERSION} — Online as {self.user}")
        print(f"  Operating Nation: {self.nation}")
        print(f"  Command Prefixes: {', '.join(self.prefixes)}")
        print(f"==================================================")

    async def on_command_error(self, ctx: commands.Context, error: commands.CommandError):
        if isinstance(error, commands.CommandNotFound):
            return
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"Missing required argument: `{error.param.name}`. Type `{ctx.prefix}help {ctx.command.name}` for usage details.")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"Invalid argument provided: {error}. Type `{ctx.prefix}help {ctx.command.name}` for usage details.")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"This command is on cooldown. Try again in {error.retry_after:.1f}s.")
        else:
            print(f"[Command Error] in {ctx.command}: {error}")
            await ctx.send(f"An error occurred executing this command: `{error}`")

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="searendipity",
        description="Searendipity NationStates manual and automated recruitment bot"
    )
    parser.add_argument("-n", "--nation-name", help="Your main nation name (identifies bot in User-Agent)")
    parser.add_argument("-p", "--prefix", help="Command prefix character (e.g. ! or ?; default: both ! and ?)")
    parser.add_argument("--db", default="bot.db", help="Path to SQLite database file (default: bot.db)")
    args = parser.parse_args()

    settings = dotenv_values(".env")

    nation_name = args.nation_name or settings.get("DEFAULT_NATION")
    if not nation_name:
        nation_name = input("Please enter your main NationStates nation name: ").strip()

    if not nation_name:
        print("Error: Nation name is required to establish User-Agent per NationStates API rules.")
        sys.exit(1)

    agent_str = f"Searendipity/{VERSION} (Discord recruitment bot) used by {nation_name}"
    sans.set_agent(agent_str)
    print(f"[Searendipity] User-Agent set to: {agent_str}")

    token = settings.get("TOKEN")
    if not token:
        print("Error: TOKEN not found in .env. Please copy .env.example to .env and configure your Discord bot token.")
        sys.exit(1)

    owner_id_str = settings.get("OWNER_ID")
    owner_id = int(owner_id_str) if owner_id_str and owner_id_str.isdigit() else 0

    if args.prefix:
        prefixes = [args.prefix.strip()]
    elif settings.get("COMMAND_PREFIX"):
        prefixes = [p.strip() for p in settings["COMMAND_PREFIX"].split(",") if p.strip()]
    else:
        prefixes = ["!", "?"]

    connection = sqlite3.connect(args.db)

    bot = SearendipityBot(connection, nation_name, owner_id, prefixes)
    bot.run(token)

if __name__ == "__main__":
    main()
