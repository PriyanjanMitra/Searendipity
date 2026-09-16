import unittest
import os
import json
import time
import jinja2

import utility as util
from src.cogs.template import TGTemplate, UserTemplates
from src.cogs.api import APITGTemplate, APITemplates
from src.cogs.recruit import RecruitmentManager, Queue
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

if __name__ == "__main__":
    unittest.main()
