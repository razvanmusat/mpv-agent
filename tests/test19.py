import sys, os, shutil, time
sys.path.insert(0, ".."); import agent
T = os.getcwd(); os.environ["PATH"] = T + "/bin:" + os.environ["PATH"]
d = T + "/cache19"; shutil.rmtree(d, ignore_errors=True); os.makedirs(d + "/clips")
agent.cfg.update(cache_dir=d, mpv_socket=T+"/run/mpv19.sock", mpv_args=[])
bad = []
def ok(c, m):
    print(("PASS " if c else "FAIL ") + m)
    if not c: bad.append(m)

a = agent.Agent()
a.player.refresh_entries = lambda: None      # fara mpv real: nu avem cum interoga lista de intrari

# (a) mesajul „no audio or video data played” nu se retine; alta eroare da
a.player.report_error({"file_error": "no audio or video data played"})
ok(a.player.last_error is None, "„no audio or video data played” nu seteaza last_error")
a.player.report_error({"file_error": "unrecognized file format"})
ok(a.player.last_error is not None and a.player.last_error["message"] == "unrecognized file format", "alta eroare se retine")
seq = a.player.last_error["id"]
a.player.report_error({"file_error": "no audio or video data played"})
ok(a.player.last_error["id"] == seq and a.player.last_error["message"] == "unrecognized file format", "mesajul ignorat nu atinge nici eroarea retinuta")

# (b) recover_idle, cu mpv simulat
state = {"running": True, "idle": True, "stops": 0, "applied": []}
a.player.running = lambda: state["running"]
a.player.idle = lambda: state["idle"]
a.player.stop = lambda: state.__setitem__("stops", state["stops"] + 1)
a.apply = lambda playlist: state["applied"].append(playlist)
PL = [("/x/a.mp4", None)]
def reset(playlist=PL, idle=True, running=True, loading=False, last=0.0):
    state.update(running=running, idle=idle, stops=0, applied=[])
    a.playlist, a.adhoc_loading, a.last_idle_retry = playlist, loading, last

reset()
a.recover_idle()
ok(state["stops"] == 1 and state["applied"] == [PL], "mpv idle cu playlist: opreste si reia redarea")
ok(a.last_idle_retry > 0, "momentul reluarii e retinut")
a.recover_idle()
ok(state["stops"] == 1 and len(state["applied"]) == 1, "nu repeta in cele 30 s")
a.last_idle_retry = time.monotonic() - agent.IDLE_RETRY_SECONDS - 1
a.recover_idle()
ok(state["stops"] == 2 and len(state["applied"]) == 2, "dupa 30 s reia din nou")

reset(idle=False)
a.recover_idle()
ok(state["stops"] == 0 and not state["applied"], "mpv nu e idle: nu reia")
reset(playlist=[])
a.recover_idle()
ok(state["stops"] == 0 and not state["applied"], "playlist gol: nu reia")
reset(playlist=None)
a.recover_idle()
ok(state["stops"] == 0 and not state["applied"], "playlist inexistent (None): nu reia")
reset(loading=True)
a.recover_idle()
ok(state["stops"] == 0 and not state["applied"], "adhoc_loading adevarat: nu reia")
reset(running=False)
a.recover_idle()
ok(state["stops"] == 0 and not state["applied"], "mpv nu ruleaza: nu reia")

print("GATA" if not bad else "ESUATE"); sys.exit(1 if bad else 0)
