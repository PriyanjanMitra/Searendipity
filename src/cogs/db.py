from discord.ext import commands
import sqlite3

class Database(commands.Cog):
    def __init__(self, bot: commands.Bot, connection: sqlite3.Connection):
        self.bot = bot
        self.db = connection
        self.init_schema()

    def init_schema(self):
        cursor = self.db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS guilds (
                guild_id INTEGER PRIMARY KEY,
                admin_role_id INTEGER,
                recruit_role_id INTEGER,
                recruit_wa INTEGER,
                recruit_newfounds INTEGER,
                recruit_refounds INTEGER
            )
        """)
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_guild_id ON guilds (guild_id);")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_templates (
                unique_id TEXT PRIMARY KEY,
                guild_id INTEGER,
                user_id INTEGER,
                wa TEXT,
                newfound TEXT,
                refound TEXT
            )
        """)
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_id ON user_templates (unique_id);")

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                unique_id TEXT PRIMARY KEY,
                guild_id INTEGER,
                user_id INTEGER,
                year INTEGER,
                month INTEGER,
                day INTEGER,
                wa_sent INTEGER,
                newfound_sent INTEGER,
                refound_sent INTEGER
            )
        """)
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_stat_unique_id ON stats (unique_id);")
        self.db.commit()
        cursor.close()
