# Sellbit agent (Raspberry Pi)

Agent Python (doar biblioteca standard) care ruleaza pe un Raspberry Pi conectat la un TV:

- deschide un tunel SSH invers catre server (se reconecteaza la 5 secunde, la nesfarsit);
- primeste comenzi instant prin tunel (`play`, `pause`, `stop`, `next`, `party`, `quick`) si semnalul de sincronizare;
- trage cu rsync `program.json` si fisierele din program, valideaza programul si il aplica;
- reda cu `mpv` (HDMI, fara desktop) dupa program: petreceri, clipuri implicite in orele de lucru, poze de fundal.

API local (doar `127.0.0.1`): `GET /status`, `POST /command`, `POST /sync`.

## Instalare (Debian / Raspberry Pi OS)

`sudo ./install.sh` — te intreaba, rand pe rand, in consola, fiecare valoare (Enter = valoarea implicita din paranteza):
serverul, caile de pe server, adresa si portul tunelului, utilizatorul serviciului etc. Apoi scrie singur `.env`
si face tot restul:

- instaleaza pachetele (mpv, rsync, python3) si creeaza utilizatorul de serviciu;
- genereaza cheia SSH a tunelului si scrie `known_hosts` (iti arata amprenta serverului si cere confirmarea);
- pune fisierele in `/opt/mpv-agent` si porneste serviciul systemd `mpv-agent`;
- la final afiseaza linia de adaugat in `authorized_keys` pe server (singurul pas manual, o data).

Toata configurarea e in `.env`, langa `agent.py` (`env.example` arata cheile si semnificatia lor); nu exista valori de
deploy in cod. La pornire, agentul raporteaza toate lipsurile din `.env` deodata si nu porneste cu config incomplet.
Pentru alt server rulezi din nou `sudo ./install.sh` (valorile vechi sunt implicitele). Jurnal: `journalctl -u mpv-agent -f`.

## Teste

`./run_tests.sh` (foloseste un mpv fals din `tests/bin`, nu are nevoie de TV).
