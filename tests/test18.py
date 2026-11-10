import sys
sys.path.insert(0, "..")
import agent
from datetime import datetime
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m) or (c or sys.exit(1))
D = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M")

# program pe zile: luni 10-18, sambata 22:00-02:00 (peste miezul noptii); celelalte zile inchise
# 2026-12-07 = luni, 2026-12-05 = sambata, 2026-12-06 = duminica
raw = {"schedule": [{"day": 1, "open": "10:00", "close": "18:00"}, {"day": 6, "open": "22:00", "close": "02:00"}],
       "default": [{"file": "a.mp4", "order": 1}, {"file": "b.mp4", "order": 2}],
       "parties": [{"date": "2026-12-07", "files": [{"file": "p.mp4", "order": 1}]}]}
p = agent.parse_program(raw)
ok(agent.is_open(p, D("2026-12-07 10:00")) and agent.is_open(p, D("2026-12-07 17:59")), "luni: deschis 10:00-17:59")
ok(not agent.is_open(p, D("2026-12-07 09:59")) and not agent.is_open(p, D("2026-12-07 18:00")), "luni: inchis inainte de 10:00 si de la 18:00")
ok(not agent.is_open(p, D("2026-12-08 12:00")), "marti (zi fara program): inchis")
ok(not agent.is_open(p, D("2026-12-05 21:59")) and agent.is_open(p, D("2026-12-05 22:00")) and agent.is_open(p, D("2026-12-05 23:59")), "sambata: deschis de la 22:00")
ok(agent.is_open(p, D("2026-12-06 00:00")) and agent.is_open(p, D("2026-12-06 01:59")), "duminica dupa miezul noptii: inca deschis (programul de sambata)")
ok(not agent.is_open(p, D("2026-12-06 02:00")) and not agent.is_open(p, D("2026-12-06 12:00")), "duminica de la 02:00: inchis, duminica nu are program")
ok(not agent.is_open(p, D("2026-12-07 01:00")), "luni 01:00: inchis (duminica nu avea program peste noapte)")

# clipurile implicite nu au zile: ruleaza toate, in orice zi deschisa; in zi inchisa nu ruleaza nimic
k, it = agent.compute_target(p, D("2026-12-07 12:00"))
ok(k == "default" and [i["file"] for i in it] == ["a.mp4", "b.mp4"], "luni in program: ruleaza toate clipurile")
ok(agent.compute_target(p, D("2026-12-08 12:00"))[0] == "none", "marti inchis: nimic")

# petrecerea are doar data: nu porneste singura, doar manual, id 'data #N'
ok([x["id"] for x in p["parties"]] == ["2026-12-07 #1"], "petrecere doar cu data: id 'YYYY-MM-DD #1'")
ok(agent.compute_target(p, D("2026-12-07 12:00"))[0] == "default", "petrecerea fara ore nu porneste singura")

# program fara nicio zi: mereu inchis
ok(not agent.is_open(agent.parse_program({"schedule": [], "default": []}), D("2026-12-07 12:00")), "schedule gol: mereu inchis")

# forma veche (open/close unice, days pe clip) se citeste in continuare
old = agent.parse_program({"open": "09:00", "close": "20:00",
                           "default": [{"file": "a.mp4", "days": [1], "order": 1}]})
ok(agent.is_open(old, D("2026-12-08 12:00")), "forma veche: orele valabile in toate zilele")
ok(agent.compute_target(old, D("2026-12-08 12:00"))[1] == [] and len(agent.compute_target(old, D("2026-12-07 12:00"))[1]) == 1, "forma veche: days pe clip respectat")

# respinse
bads = [{"schedule": [{"day": 0, "open": "10:00", "close": "18:00"}]},
        {"schedule": [{"day": 8, "open": "10:00", "close": "18:00"}]},
        {"schedule": [{"day": "1", "open": "10:00", "close": "18:00"}]},
        {"schedule": [{"day": 1, "open": "10:00", "close": "18:00"}, {"day": 1, "open": "11:00", "close": "12:00"}]},
        {"schedule": [{"day": 1, "open": "25:00", "close": "18:00"}]},
        {"schedule": [{"day": 1, "open": "10:00"}]},
        {"schedule": "luni"},
        {}]
for bad in bads:
    try:
        agent.parse_program({**bad, "default": []}); ok(False, "ar fi trebuit respins " + str(bad))
    except (KeyError, TypeError, ValueError):
        ok(True, "respins: " + str(bad))
print("TOATE OK")
