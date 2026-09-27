import unittest
import os
import json
import time
import jinja2

import utility as util
from src.cogs.template import TGTemplate, UserTemplates
from src.cogs.api import APITGTemplate, APITemplates
from src.cogs.recruit import RecruitmentManager, Queue, RecruiterSession, BatchView
from src.report.classes import Stats, TimeRange, Analytics, Recruit, Telegram, TelegramTemplate
from src.report.filters import (
    renderRate, renderDate, methodName, displayNumberWithCommas,
    normalizeNationName, sortByHighest
)
from genreport import SearendipityEncoder

class TestUtility(unittest.TestCase):
    def test_format_nation_or_region(self):
        self.assertEqual(util.format_nation_or_region("The Pacific"), "the_pacific")
        self.assertEqual(util.format_nation_or_region("  Test_Nation  "), "test_nation")
        self.assertEqual(util.format_nation_or_region(""), "")

    def test_parse_template_id(self):
        self.assertEqual(util.parse_template_id("%TEMPLATE-12345%"), 12345)
        self.assertEqual(util.parse_template_id("TEMPLATE-999"), 999)
        self.assertEqual(util.parse_template_id("54321"), 54321)
        self.assertIsNone(util.parse_template_id("invalid-text"))
        self.assertIsNone(util.parse_template_id(""))

class TestTemplates(unittest.TestCase):
    def test_user_templates_serialization(self):
        wa_str = "wa_v1:101,wa_v2:102"
        new_str = "new_v1:201"
        ref_str = "ref_v1:301"

        user_tpls = UserTemplates.from_strings(wa_str, new_str, ref_str)
        self.assertEqual(len(user_tpls.wa), 2)
        self.assertEqual(user_tpls.wa[0].category, "wa_v1")
        self.assertEqual(user_tpls.wa[0].tgid, 101)
        self.assertEqual(user_tpls.wa[1].tgid, 102)
        self.assertEqual(len(user_tpls.newfound), 1)
        self.assertEqual(len(user_tpls.refound), 1)

        out_wa, out_new, out_ref = user_tpls.to_strings()
        self.assertEqual(out_wa, wa_str)
        self.assertEqual(out_new, new_str)
        self.assertEqual(out_ref, ref_str)

    def test_api_templates_serialization(self):
        wa_str = "wa_api:101:secretkey1"
        new_str = "new_api:201:secretkey2"
        ref_str = "ref_api:301:secretkey3"

        api_tpls = APITemplates.from_strings(wa_str, new_str, ref_str)
        self.assertIsInstance(api_tpls, APITemplates)
        self.assertEqual(len(api_tpls.wa), 1)
        self.assertEqual(api_tpls.wa[0].category, "wa_api")
        self.assertEqual(api_tpls.wa[0].tgid, 101)
        self.assertEqual(api_tpls.wa[0].key, "secretkey1")

        out_wa, out_new, out_ref = api_tpls.to_strings()
        self.assertEqual(out_wa, wa_str)
        self.assertEqual(out_new, new_str)
        self.assertEqual(out_ref, ref_str)

class TestQueueAndPuppetFilter(unittest.TestCase):
    def test_puppet_filter(self):
        class DummyBot:
            pass

        mgr = RecruitmentManager(DummyBot(), "test_nation")

        # First nation passes
        self.assertFalse(mgr.check_puppet_filter("great_empire"))

        # Distinct nation passes
        self.assertFalse(mgr.check_puppet_filter("different_republic"))

        # Similar spam puppet cascades should be filtered
        mgr.check_puppet_filter("puppet_army_01")
        # puppet_army_02 is 13/14 identical = 92% similarity -> should return True (filtered)
        self.assertTrue(mgr.check_puppet_filter("puppet_army_02"))
        self.assertTrue(mgr.check_puppet_filter("puppet_army_03"))

    def test_queue_pop_and_sort(self):
        class DummyBot:
            guilds = []

        mgr = RecruitmentManager(DummyBot(), "test_nation")
        guild_id = 999
        mgr._ensure_guild_queues(guild_id)

        mgr.newfound_queue[guild_id].nations.append(("nation_a", time.time()))
        mgr.newfound_queue[guild_id].nations.append(("nation_b", time.time()))

        popped = mgr.pop_new_nations(guild_id, 5)
        self.assertEqual(len(popped), 2)
        self.assertIn("nation_a", popped)
        self.assertIn("nation_b", popped)
        self.assertEqual(len(mgr.newfound_queue[guild_id].nations), 0)

class TestReportAnalyticsAndFilters(unittest.TestCase):
    def test_filters(self):
        self.assertEqual(renderRate(100, 25), "25.00%")
        self.assertEqual(renderRate(0, 0), "0.00%")
        self.assertEqual(methodName("api"), "API Template")
        self.assertEqual(displayNumberWithCommas(1234567), "1,234,567")
        self.assertEqual(normalizeNationName("New South Wales"), "new_south_wales")

    def test_stats_aggregation(self):
        s1 = Stats(delivered=100, readCount=50, recruitCount=5)
        s2 = Stats(delivered=200, readCount=120, recruitCount=15)
        s1.add(s2)

        self.assertEqual(s1.delivered, 300)
        self.assertEqual(s1.readCount, 170)
        self.assertEqual(s1.recruitCount, 20)
        self.assertEqual(s1.readRate, f"{round(170/300*100, 2):.2f}%")

    def test_template_rendering_smoke_test(self):
        # Verify Jinja templates render without syntax error
        templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(templates_dir))
        env.filters['renderdate'] = renderDate
        env.filters['items'] = lambda d: d.items()
        env.filters['sorttop'] = lambda d: list(d.items())[:5]
        env.filters['sortstatstop'] = lambda d: list(d.items())[:5]
        env.filters['sortbyhighest'] = sortByHighest
        env.filters['sortstatsbyhighest'] = lambda d: list(d.items())
        env.filters['methodname'] = methodName
        env.filters['displaynum'] = displayNumberWithCommas
        env.filters['canonname'] = lambda n: n.replace("_", " ").title()

        analytics = Analytics(
            stats=Stats(delivered=500, readCount=250, recruitCount=25),
            faithful=[Recruit(cte=False, recruitedAt=1000, name="loyal_nation")],
            wa_faithful=[Recruit(cte=False, recruitedAt=1000, name="loyal_nation")],
            traitor_destinations={"other_region": 2},
            uninterested_destinations={"somewhere_else": 10},
            timeRange=TimeRange(start=1000, end=2000)
        )

        tg = Telegram("test_category")
        tg.stats = Stats(delivered=500, readCount=250, recruitCount=25)
        tg.timeRange = TimeRange(1000, 2000)
        telegrams = {"test_category": tg}
        methods = {"template": Stats(delivered=500, readCount=250, recruitCount=25)}
        nations = {"recruiter_main": Stats(delivered=500, readCount=250, recruitCount=25)}

        index_tmpl = env.get_template("index.html.jinja")
        rendered_index = index_tmpl.render(
            analytics=analytics,
            methods=methods,
            nations=nations,
            telegrams=telegrams,
            region="test_region"
        )
        self.assertIn("Searendipity", rendered_index)
        self.assertIn("Recruitment Performance Report", rendered_index)
        self.assertIn("test_category", rendered_index)

        tg_tmpl = env.get_template("telegram.html.jinja")
        rendered_tg = tg_tmpl.render(telegram=tg, region="test_region")
        self.assertIn("Category: test_category", rendered_tg)

    def test_cogs_commands_registered(self):
        import sqlite3
        import asyncio
        from searendipity import SearendipityBot

        conn = sqlite3.connect(":memory:")
        bot = SearendipityBot(conn, "test_nation", 123456789, prefixes=["!", "?"])

        async def load():
            await bot.setup_hook()
            command_names = [cmd.name for cmd in bot.commands]
            expected = [
                "start", "config", "templates", "add", "setup", "remove", "clear",
                "recruit", "stop", "forcestop", "queue", "timer", "stats",
                "apiguild", "apiclient", "apistart", "apistop", "apirestart",
                "apistatus", "apitemplates", "apiadd", "apisetup", "apiremove", "apiclear"
            ]
            for exp in expected:
                self.assertIn(exp, command_names, f"Expected command '{exp}' to be registered.")

            nation_cog = bot.get_cog('NationListener')
            if nation_cog:
                await nation_cog.cog_unload()
            await bot.close()
            conn.close()

        asyncio.run(load())

    def test_gui_components_instantiation(self):
        from src.cogs.gui import (
            ControlPanelView, APIPanelView, RecruitModal, AddTemplateModal,
            QuickSetupModal, ServerConfigModal, ForceStopModal,
            APIClientModal, APIAddTemplateModal, APISetupModal, GuiManager
        )

        class DummyBot:
            pass

        gui_cog = GuiManager(DummyBot())

        panel_view = ControlPanelView(gui_cog)
        self.assertGreater(len(panel_view.children), 0)

        api_view = APIPanelView(gui_cog)
        self.assertGreater(len(api_view.children), 0)

        # Verify all modals instantiate without error
        r_modal = RecruitModal(gui_cog)
        self.assertEqual(r_modal.title, "Start Recruitment Session")

        add_modal = AddTemplateModal(gui_cog)
        self.assertEqual(add_modal.title, "Add Telegram Template")

        setup_modal = QuickSetupModal(gui_cog)
        self.assertEqual(setup_modal.title, "Quick Generic Template Setup")

        cfg_modal = ServerConfigModal(gui_cog)
        self.assertEqual(cfg_modal.title, "Server Recruitment Configuration")

        stop_modal = ForceStopModal(gui_cog)
        self.assertEqual(stop_modal.title, "Force Stop Recruiter Session")

        client_modal = APIClientModal(gui_cog)
        self.assertEqual(client_modal.title, "Set API Client Key")

        api_add_modal = APIAddTemplateModal(gui_cog)
        self.assertEqual(api_add_modal.title, "Add API Telegram Template")

        api_setup_modal = APISetupModal(gui_cog)
        self.assertEqual(api_setup_modal.title, "Quick Generic API Template Setup")

class TestStrictRecruitmentSession(unittest.TestCase):
    def setUp(self):
        class DummyBot:
            guilds = []
            def get_cog(self, name):
                return None
        self.bot = DummyBot()
        self.manager = RecruitmentManager(self.bot, "test_nation")
        self.user = type('User', (), {'id': 12345, 'mention': '<@12345>'})()
        self.channel = type('Channel', (), {})()

    def test_telegram_link_generation(self):
        tpl = TGTemplate("standard_wa", 98765)
        nations = ["nation_one", "nation_two"]

        # Default browser profile (no container)
        link = self.manager.generate_telegram_link(tpl, nations, container=None)
        expected = "https://www.nationstates.net/page=compose_telegram?tgto=nation_one,nation_two&message=%TEMPLATE-98765%&generated_by=searendipity_bot__ran_by_test_nation"
        self.assertEqual(link, expected)

        # Multi-session container profile
        link_container = self.manager.generate_telegram_link(tpl, nations, container="MainProfile")
        expected_container = "https://www.nationstates.net/container=MainProfile/page=compose_telegram?tgto=nation_one,nation_two&message=%TEMPLATE-98765%&generated_by=searendipity_bot__ran_by_test_nation"
        self.assertEqual(link_container, expected_container)

    def test_batch_view_initialization(self):
        session = RecruiterSession(
            guild_id=1,
            user_id=12345,
            user=self.user,
            channel=self.channel,
            interval=60,
            container=None,
            current_nations=["nation_one"],
            current_template=TGTemplate("wa", 111)
        )
        view = BatchView(session, self.manager)
        self.assertEqual(len(view.children), 4)
        labels = [item.label for item in view.children]
        self.assertIn("Click to Send TG", labels)
        self.assertIn("Mark as Sent", labels)
        self.assertIn("Get Next List", labels)
        self.assertIn("Stop Session", labels)

    def test_mark_as_sent_logic(self):
        import asyncio

        session = RecruiterSession(
            guild_id=1,
            user_id=12345,
            user=self.user,
            channel=self.channel,
            interval=60,
            container=None,
            current_nations=["nation_one"],
            current_template=TGTemplate("wa", 111)
        )
        view = BatchView(session, self.manager)

        class MockResponse:
            def __init__(self):
                self.messages = []
                self.edits = []
            async def send_message(self, content=None, **kwargs):
                self.messages.append((content, kwargs))
            async def edit_message(self, **kwargs):
                self.edits.append(kwargs)

        class MockInteraction:
            def __init__(self, user_id=12345):
                self.user = type('User', (), {'id': user_id, 'mention': f'<@{user_id}>'})()
                self.response = MockResponse()

        inter = MockInteraction(user_id=12345)

        # Initial state
        self.assertFalse(session.is_sent)
        self.assertEqual(session.sent_at, 0.0)

        # Mark as sent
        mark_btn = [item for item in view.children if item.label == "Mark as Sent"][0]
        asyncio.run(mark_btn.callback(inter))

        self.assertTrue(session.is_sent)
        self.assertGreater(session.sent_at, 0.0)
        self.assertTrue(mark_btn.disabled)
        self.assertEqual(mark_btn.label, "Sent!")

        # Trying to mark as sent again should return warning
        inter2 = MockInteraction(user_id=12345)
        asyncio.run(mark_btn.callback(inter2))
        self.assertTrue(any("already been marked as sent" in m[0] for m in inter2.response.messages))

    def test_strict_wait_time_and_sent_check(self):
        import asyncio

        session = RecruiterSession(
            guild_id=1,
            user_id=12345,
            user=self.user,
            channel=self.channel,
            interval=60,
            container=None,
            current_nations=["nation_one"],
            current_template=TGTemplate("wa", 111)
        )
        view = BatchView(session, self.manager)

        class MockResponse:
            def __init__(self):
                self.messages = []
                self.edits = []
            async def send_message(self, content=None, **kwargs):
                self.messages.append((content, kwargs))
            async def edit_message(self, **kwargs):
                self.edits.append(kwargs)

        class MockInteraction:
            def __init__(self, user_id=12345):
                self.user = type('User', (), {'id': user_id, 'mention': f'<@{user_id}>'})()
                self.response = MockResponse()

        next_btn = [item for item in view.children if item.label == "Get Next List"][0]

        # Case 1: is_sent is False -> Check Failed, must mark as sent first
        inter1 = MockInteraction(user_id=12345)
        asyncio.run(next_btn.callback(inter1))
        self.assertTrue(any("Check Failed" in m[0] for m in inter1.response.messages))

        # Case 2: is_sent is True, but cooldown is still active (e.g. elapsed 10s < 60s)
        session.is_sent = True
        session.sent_at = time.time() - 10
        inter2 = MockInteraction(user_id=12345)
        asyncio.run(next_btn.callback(inter2))
        self.assertTrue(any("Strict Cooldown Active" in m[0] for m in inter2.response.messages))

        # Case 3: is_sent is True and cooldown is over (elapsed 65s >= 60s)
        session.sent_at = time.time() - 65
        inter3 = MockInteraction(user_id=12345)
        dispatch_called = []
        async def mock_dispatch(s):
            dispatch_called.append(s)
            return True
        self.manager.dispatch_next_batch = mock_dispatch

        asyncio.run(next_btn.callback(inter3))
        self.assertEqual(len(dispatch_called), 1)
        self.assertEqual(dispatch_called[0], session)
        self.assertTrue(next_btn.disabled)

if __name__ == "__main__":
    unittest.main()


