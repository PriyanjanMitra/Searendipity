from dataclasses import dataclass, field
import typing
from .filters import renderRate

def accumulate(dest: dict, src: dict, default, add_callback) -> dict:
    result = dict(dest)
    for element, value in src.items():
        if element not in result:
            result[element] = default
        result[element] = add_callback(result[element], value)
    return result

@dataclass
class Recruit:
    cte: bool
    recruitedAt: int
    name: str

    @staticmethod
    def fromJSON(src: dict) -> "Recruit":
        return Recruit(
            cte=src.get("cte", False),
            recruitedAt=src.get("recruitedAt", src.get("timestamp", 0)),
            name=src.get("name", "")
        )

@dataclass
class Nation:
    canon_name: str
    api_name: str
    region: str
    wa: bool
    lastlogin: int

@dataclass
class Stats:
    delivered: int = 0
    readCount: int = 0
    recruitCount: int = 0

    def add(self, other: "Stats"):
        self.delivered += other.delivered
        self.readCount += other.readCount
        self.recruitCount += other.recruitCount

    def join(self, other: "Stats") -> "Stats":
        return Stats(
            self.delivered + other.delivered,
            self.readCount + other.readCount,
            self.recruitCount + other.recruitCount
        )

    @property
    def readRate(self) -> str:
        return renderRate(self.delivered, self.readCount)

    @property
    def recruitRate(self) -> str:
        return renderRate(self.delivered, self.recruitCount)

    @property
    def readToRecruitRate(self) -> str:
        return renderRate(self.readCount, self.recruitCount)

    @staticmethod
    def empty() -> "Stats":
        return Stats(0, 0, 0)

    @staticmethod
    def fromJSON(src: dict) -> "Stats":
        return Stats(
            delivered=src.get("delivered", 0),
            readCount=src.get("readCount", 0),
            recruitCount=src.get("recruitCount", 0)
        )

@dataclass
class TimeRange:
    start: int = 9999999999999
    end: int = 0

    @staticmethod
    def default() -> "TimeRange":
        return TimeRange(9999999999999, 0)

    def try_add_start(self, start: int):
        if start and start < self.start:
            self.start = start

    def try_add_end(self, end: int):
        if end and end > self.end:
            self.end = end

    @staticmethod
    def fromJSON(src: dict) -> "TimeRange":
        return TimeRange(
            start=src.get("start", 9999999999999),
            end=src.get("end", 0)
        )

@dataclass
class Analytics:
    stats: Stats = field(default_factory=Stats.empty)
    faithful: list[Recruit] = field(default_factory=list)
    wa_faithful: list[Recruit] = field(default_factory=list)
    traitor_destinations: dict[str, int] = field(default_factory=dict)
    uninterested_destinations: dict[str, int] = field(default_factory=dict)
    timeRange: TimeRange = field(default_factory=TimeRange.default)

    @property
    def faithfulCount(self) -> int:
        return len(self.faithful)

    @property
    def waFaithfulCount(self) -> int:
        return len(self.wa_faithful)

    @property
    def preserveRate(self) -> str:
        return renderRate(self.stats.recruitCount, len(self.faithful))

    @property
    def waPreserveRate(self) -> str:
        return renderRate(self.stats.recruitCount, len(self.wa_faithful))

    @staticmethod
    def empty() -> "Analytics":
        return Analytics(Stats.empty(), [], [], {}, {}, TimeRange.default())

    def add(self, other: "Analytics"):
        self.faithful.extend(other.faithful)
        self.wa_faithful.extend(other.wa_faithful)
        self.stats.add(other.stats)

        self.timeRange.try_add_start(other.timeRange.start)
        self.timeRange.try_add_end(other.timeRange.end)

        self.traitor_destinations = accumulate(self.traitor_destinations, other.traitor_destinations, 0, lambda a, b: a + b)
        self.uninterested_destinations = accumulate(self.uninterested_destinations, other.uninterested_destinations, 0, lambda a, b: a + b)

    @staticmethod
    def fromJSON(src: dict) -> "Analytics":
        return Analytics(
            stats=Stats.fromJSON(src.get("stats", {})),
            faithful=[Recruit.fromJSON(s) for s in src.get("faithful", [])],
            wa_faithful=[Recruit.fromJSON(s) for s in src.get("wa_faithful", [])],
            traitor_destinations=src.get("traitor_destinations", {}),
            uninterested_destinations=src.get("uninterested_destinations", {}),
            timeRange=TimeRange.fromJSON(src.get("timeRange", {}))
        )

class TelegramTemplate:
    tgid: int
    type: str
    nation: str
    category: str
    timeRange: TimeRange
    stats: Stats
    recipients: list[str]
    recruits: dict[str, Recruit]

    def __init__(self):
        self.tgid = 0
        self.type = ""
        self.nation = ""
        self.category = "Uncategorized"
        self.timeRange = TimeRange.default()
        self.stats = Stats.empty()
        self.recipients = []
        self.recruits = {}

    @staticmethod
    def fromJSON(src: dict) -> "TelegramTemplate":
        tpl = TelegramTemplate()
        tpl.tgid = src.get("tgid", 0)
        tpl.type = src.get("type", "")
        tpl.nation = src.get("nation", "")
        tpl.category = src.get("category", "Uncategorized")
        tpl.timeRange = TimeRange.fromJSON(src.get("timeRange", {}))
        tpl.stats = Stats.fromJSON(src.get("stats", {}))
        tpl.recipients = src.get("recipients", [])
        tpl.recruits = {}
        for k, v in src.get("recruits", {}).items():
            tpl.recruits[k] = Recruit.fromJSON(v)
        return tpl

class Telegram:
    stats: Stats
    category: str
    recipients: list[str]
    recruits: dict[str, Recruit]
    templates: list[TelegramTemplate]
    methods: dict[str, Stats]
    nations: dict[str, Stats]
    timeRange: TimeRange
    analytics: Analytics

    def __init__(self, category_name: str = ""):
        self.category = category_name
        self.stats = Stats.empty()
        self.timeRange = TimeRange.default()
        self.recipients = []
        self.recruits = {}
        self.templates = []
        self.methods = {}
        self.nations = {}
        self.analytics = Analytics.empty()

    @staticmethod
    def fromJSON(src: dict) -> "Telegram":
        tg = Telegram(src.get("category", ""))
        tg.stats = Stats.fromJSON(src.get("stats", {}))
        tg.recipients = src.get("recipients", [])
        tg.recruits = {k: Recruit.fromJSON(v) for k, v in src.get("recruits", {}).items()}
        tg.templates = [TelegramTemplate.fromJSON(s) for s in src.get("templates", [])]
        tg.methods = {k: Stats.fromJSON(v) for k, v in src.get("methods", {}).items()}
        tg.nations = {k: Stats.fromJSON(v) for k, v in src.get("nations", {}).items()}
        tg.timeRange = TimeRange.fromJSON(src.get("timeRange", {}))
        tg.analytics = Analytics.fromJSON(src.get("analytics", {}))
        return tg
