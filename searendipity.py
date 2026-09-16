#!/usr/bin/env python3
"""
Searendipity: The serendipitous NationStates recruitment and analytics suite.
Discord manual & API recruitment bot.
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
    def __init__(self, connection: sqlite3.Connection, nation: str, owner_id: int):
        intents = discord.Intents.default()
        intents.members = True

        super().__init__(command_prefix="!", intents=intents)

        self.db_connection = connection
        self.nation = util.format_nation_or_region(nation)
        self.owner_id = owner_id

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
        print(f"==================================================")

        try:
            synced = await self.tree.sync()
            print(f"[Searendipity] Successfully synced {len(synced)} application slash commands.")
        except Exception as e:
            print(f"[Searendipity] Error syncing application commands: {e}")

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="searendipity",
        description="Searendipity NationStates manual and automated recruitment bot"
    )
    parser.add_argument("-n", "--nation-name", help="Your main nation name (identifies bot in User-Agent)")
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

    connection = sqlite3.connect(args.db)

    bot = SearendipityBot(connection, nation_name, owner_id)
    bot.run(token)

if __name__ == "__main__":
    main()
