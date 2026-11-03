import sys, os, time, threading
sys.path.insert(0, ".."); import agent
agent.cfg.update(cache_dir=os.getcwd()+"/cache")
a = agent.Agent(); runs = []
def fake():
    runs.append(time.time()); time.sleep(0.5); return {"ok": True}
a.sync_once = fake
t = threading.Thread(target=a.sync); t.start(); time.sleep(0.1)
a.sync(); a.sync()          # doua apeluri in timpul primului
t.join(); time.sleep(1.2)
print("rulari:", len(runs), "(asteptat 2: prima + una pentru apelurile venite in timpul ei)")
sys.exit(0 if len(runs) == 2 else 1)
