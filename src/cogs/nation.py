from discord.ext import commands, tasks
import sans
import asyncio
import re
import time
import utility as util

FOUND_REGEX = re.compile(r"@@([a-z0-9_\-]+)@@ was (founded|refounded) in %%([a-z0-9_\-]+)%%", re.IGNORECASE)
WA_JOIN_REGEX = re.compile(r"@@([a-z0-9_\-]+)@@ was admitted to the World Assembly", re.IGNORECASE)

# Known jump points / staging regions where WA joiners are typically puppets or raiders/defenders
JUMP_POINT_LIST = [
    "suspicious",
    "artificial_solar_system"
]

class NationListener(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.sse_task = None
        self.last_event = time.time()
        self.running = True

    async def cog_load(self):
        self.sse_task = asyncio.create_task(self.sse_loop())
        self.check_stale_loop.start()

    async def cog_unload(self):
        self.running = False
        self.check_stale_loop.cancel()
        if self.sse_task:
            self.sse_task.cancel()

    @tasks.loop(minutes=5)
    async def check_stale_loop(self):
        if not self.running:
            return
        current_time = time.time()
        if (current_time - self.last_event) > 300:
            print("[NationListener] No SSE events received in the last 5 minutes. Restarting connection...")
            if self.sse_task and not self.sse_task.done():
                self.sse_task.cancel()
            self.sse_task = asyncio.create_task(self.sse_loop())

    async def sse_loop(self):
        await self.bot.wait_until_ready()
        backoff = 2

        while self.running:
            try:
                recruiter = self.bot.get_cog('RecruitmentManager')
                async with sans.AsyncClient() as client:
                    print("[NationListener] Connecting to NationStates SSE stream (founding, member)...")
                    async for event in sans.serversent_events(client, "founding", "member"):
                        if not self.running:
                            break
                        self.last_event = time.time()
                        backoff = 2  # Reset backoff on successful event

                        raw_str = event.get("str", "")
                        if not raw_str:
                            continue

                        # Check founding / refounding
                        found_match = FOUND_REGEX.search(raw_str)
                        if found_match:
                            nation, action, region = found_match.groups()
                            nation = util.format_nation_or_region(nation)
                            action = action.lower()

                            if recruiter and recruiter.check_puppet_filter(nation):
                                continue

                            if action == 'founded':
                                if recruiter:
                                    recruiter.add_newfound(nation)
                                print(f"[NationListener] Newfound nation: {nation} in {region}")
                            else:
                                # Refounded nation: check if recruitment telegrams are allowed
                                skip = False
                                try:
                                    response = await client.get(sans.Nation(nation, 'tgcanrecruit'))
                                    for item in response.iter_xml():
                                        if item.tag == 'TGCANRECRUIT' and item.text and int(item.text) == 0:
                                            skip = True
                                            break
                                except Exception as err:
                                    print(f"[NationListener] Error checking tgcanrecruit for {nation}: {err}")

                                if skip:
                                    continue

                                if recruiter:
                                    recruiter.add_refound(nation)
                                print(f"[NationListener] Refounded nation: {nation} in {region}")

                            self.bot.dispatch('new_recruit', nation)
                            continue

                        # Check World Assembly joins
                        wa_match = WA_JOIN_REGEX.search(raw_str)
                        if wa_match:
                            nation = util.format_nation_or_region(wa_match.group(1))

                            if recruiter and recruiter.check_puppet_filter(nation):
                                continue

                            skip = False
                            try:
                                response = await client.get(sans.Nation(nation, 'region', 'tgcanrecruit', 'population'))
                                for item in response.iter_xml():
                                    if item.tag == 'TGCANRECRUIT' and item.text and int(item.text) == 0:
                                        skip = True
                                        break
                                    if item.tag == 'POPULATION' and item.text and int(item.text) > 500:
                                        # Over 500M population: seasoned nation, not a fresh recruit
                                        skip = True
                                        break
                                    if item.tag == 'REGION' and item.text:
                                        reg = util.format_nation_or_region(item.text)
                                        if reg in JUMP_POINT_LIST:
                                            skip = True
                                            break
                            except Exception as err:
                                print(f"[NationListener] Error checking WA nation {nation}: {err}")

                            if skip:
                                continue

                            if recruiter:
                                recruiter.add_new_wa(nation)
                            print(f"[NationListener] WA Member admitted: {nation}")
                            self.bot.dispatch('new_recruit', nation)
                            continue

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[NationListener] SSE connection encountered an error: {e}. Reconnecting in {backoff}s...")
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60)
