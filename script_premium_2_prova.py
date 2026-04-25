import time
import requests

# ========= CONFIG =========

TOTALCORNER_TOKEN = "3ba194aed56cca11"
TELEGRAM_BOT_TOKEN = "8556542608:AAFJPKo0CBuFfwVfRqdkiEUrX2Rh5mNNmxQ"
TELEGRAM_CHAT_ID = 724772537

POLL_INTERVAL_SECONDS = 10

TC_URL_TODAY = "https://api.totalcorner.com/v1/match/today"
TG_URL_SEND = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"


def send_msg(text: str):
    """Invia un messaggio al bot Telegram."""
    try:
        requests.post(
            TG_URL_SEND,
            data={"chat_id": TELEGRAM_CHAT_ID, "text": text},
            timeout=10
        )
    except:
        pass


def parse_pair(lst):
    """Converte [home, away] in due interi (home, away)."""
    if isinstance(lst, list) and len(lst) >= 2:
        try:
            return int(lst[0]), int(lst[1])
        except:
            return 0, 0
    return 0, 0


def parse_handicap(match):
   """
   Legge SOLO l'handicap LIVE (i_asian).

   - Se i_asian esiste e si può convertire -> lo usa.
   - Se i_asian manca o è sporco -> restituisce (None, None).

   NON usa più p_asian (handicap di apertura).
   """

   live = match.get("i_asian")
   if not live:
       return None, None

   # può essere stringa o lista
   if isinstance(live, list):
       raw = str(live[0]).split(",")[0].strip()
   else:
       raw = str(live).split(",")[0].strip()

   if not raw:
       return None, None

   try:
       val = float(raw.replace("+", ""))
       return val, raw
   except Exception:
       return None, None


def is_female_match(sex_value, home, away):
   """Restituisce True solo se la partita è femminile (basato SOLO sui 5 termini richiesti)."""

   # Prendiamo tutto in forma minuscola per confronti sicuri
   s = str(sex_value).lower()
   hn = str(home).lower()
   an = str(away).lower()

   # I 5 termini indicati, convertiti in minuscolo per confronto
   keywords = [
       "femminile",  # femminile
       "women",      # Women
       "damen"       # Damen
   ]

   # 1) Controllo nel campo 'sex'
   for kw in keywords:
       if s == kw or kw in s:
           return True

   # 2) Controllo nei nomi delle squadre
   text = (hn + " " + an).lower()
   # controllo specifico
   if "(w)" in text or "(f)" in text:
       return True
   for kw in keywords:
       if kw in text:
           return True

   return False


def get_live():
    """Legge le partite live di oggi da match/today."""
    params = {
        "token": TOTALCORNER_TOKEN,
        "type": "inplay",
        # colonne: gol, stato, nomi, sesso, attacchi, pericolosi, tiri, handicap
        "columns": "hg,ag,status,h,a,l,start,sex,attacks,dangerousAttacks,shotOn,shotOff,asian",
    }
    try:
        r = requests.get(TC_URL_TODAY, params=params, timeout=15)
    except Exception:
        return []

    if r.status_code != 200:
        return []

    try:
        js = r.json()
    except Exception:
        return []

    if not js.get("success"):
        return []

    data = js.get("data", [])
    if not isinstance(data, list):
        return []

    return data


def main():
    print("SCRIPT PRINCIPALE: REGOLA 1 + REGOLA 2 (indipendenti, niente finali)\n")

    # match_id -> {"r1": bool, "r2": bool}
    tracked = {}

    while True:
        matches = get_live()
        print("\n==============================")
        print(f"Trovate {len(matches)} partite. Controllo...")

        for m in matches:
            try:
                match_id = m.get("id")
                if not match_id:
                    continue

                if match_id not in tracked:
                    tracked[match_id] = {"r1": False, "r2": False, "r3": False, "r4": False, "r5": False, "r6": False, "r7": False, "r8": False, "r9": False, "r10": False}
                state = tracked[match_id]

                league = m.get("l", "?")
                league_str = str(league).lower()
                home = m.get("h", "?")
                away = m.get("a", "?")
                start = m.get("start", "?")
                sex = m.get("sex", "")
                hid = m.get("hid")
                aid = m.get("aid")
                handi_val, handi_raw = parse_handicap(m)

                # NO ESoccer / e-football
                if ("esoccer" in league_str or
                    "e-football" in league_str or
                    "efootball" in league_str or
                    "e-soccer" in league_str):
                    continue

                # MINUTO
                try:
                    minute = int(str(m.get("status")))
                except Exception:
                    continue

                # GOL (solo per info)
                try:
                    hg = int(str(m.get("hg", "0")))
                    ag = int(str(m.get("ag", "0")))
                except Exception:
                    hg, ag = 0, 0

                # ATTACCHI TOTALI
                att_h, att_a = parse_pair(m.get("attacks") or [])

                # ATTACCHI PERICOLOSI
                datt_h, datt_a = parse_pair(
                    m.get("dangerousAttacks")
                    or m.get("dang_attacks")
                    or m.get("dangerous_attacks")
                    or []
                )

                # TIRI IN PORTA
                on_h, on_a = parse_pair(
                    m.get("shotOn")
                    or m.get("shot_on")
                    or []
                )

                # TIRI FUORI
                off_h, off_a = parse_pair(
                    m.get("shotOff")
                    or m.get("shot_off")
                    or []
                )

                tot_shots_h = on_h + off_h
                tot_shots_a = on_a + off_a

                handi_val, handi_raw = parse_handicap(m)

                # DEBUG NEL TERMINALE
                print(
                    f"  {league} | {home} vs {away} | {minute}' | {hg}-{ag} "
                    f"(att={att_h}-{att_a}, dang={datt_h}-{datt_a}, "
                    f"ON={on_h}-{on_a}, OFF={off_h}-{off_a}, HANDI={handi_raw})"
                )

                # ================= REGOLA 1 =================
                # (come l’abbiamo testata prima, solo la favorita casa con handi -6..-1.0)
                if (
                    not state["r1"]                 # non ancora mandato
                    and not is_female_match(sex, home, away)   # solo maschi
                    and handi_val is not None
                    and -3.0 <= handi_val <= -2.5
                    and minute == 79
                    and (hg, ag) in [
                        (0,1),(1,2),
                        (2,3),(3,4) 
                    ]  
                    and datt_h >= 0                 # pericolosi casa
                ):
                    msg = (
                        "⚽ REGOLA CORNER\n\n"
                        f"Lega: {league}\n"
                        f"Partita: {home} vs {away}\n"
                        f"Ora inizio: {start}\n\n"
                        f"Minuto: {minute}'\n"
                        f"Handicap apertura casa: {handi_raw}\n\n"
                        f"Attacchi pericolosi: {datt_h} - {datt_a}\n"
                        f"Attacchi totali: {att_h} - {att_a}\n\n"
                        f"Tiri in porta: {on_h} - {on_a}\n"
                        f"Tiri fuori: {off_h} - {off_a}\n"
                        f"Tiri totali casa: {tot_shots_h}\n"
                        f"Risultato attuale: {hg} - {ag}\n"
                    )
                    send_msg(msg)
                    state["r1"] = True

                # ================= REGOLA 2 =================
                # Solo MASCHILI, handi casa +3.5..+1.5, minuto 60,
                # pericolosi casa >= 10, tiri totali >= 1
                if (
                    not state["r2"]                 # non ancora mandato
                    and not is_female_match(sex, home, away)   # solo maschi
                    and handi_val is not None
                    and +1.0 <= handi_val <= +3.0
                    and minute == 45
                    and (hg, ag) in [
                        (1,1),(2,2),(3,3)
                    ]  
                    and datt_a >= 30                # attacchi pericolosi ospite
                    and on_a >= 5                  # tiri in porta ospite
                    and tot_shots_a >= 8            
                ):
                    msg = (
                        "⚽️ FAVORITA OSPITE PAREGGIA\n\n"
                        f"Lega: {league}\n"
                        f"Partita: {home} vs {away}\n"
                        f"Ora inizio: {start}\n\n"
                        f"Minuto: {minute}'\n"
                        f"Handicap apertura casa: {handi_raw}\n\n"
                        f"Attacchi pericolosi: {datt_h} - {datt_a}\n"
                        f"Attacchi totali: {att_h} - {att_a}\n\n"
                        f"Tiri in porta: {on_h} - {on_a}\n"
                        f"Tiri fuori: {off_h} - {off_a}\n"
                        f"Tiri totali ospite: {tot_shots_a}\n"
                        f"Risultato attuale: {hg} - {ag}\n"
                    )
                    send_msg(msg)
                    state["r2"] = True

                # ================= REGOLA 7 =================
                # Solo MASCHILI, handi casa +3.5..+1.5, minuto 60,
                # pericolosi casa >= 10, tiri totali >= 1
                if (
                    not state["r7"]                 # non ancora mandato
                    and not is_female_match(sex, home, away)   # solo maschi
                    and handi_val is not None
                    and +1.0 <= handi_val <= +3.0
                    and minute == 45
                    and (hg, ag) in [
                        (1,0),(2,0),(2,1),(3,1),
                        (3,2),(4,2),(4,3)
                    ]  
                    and datt_a >= 30                # attacchi pericolosi ospite
                    and on_a >= 4                   # tiri in porta ospite 
                    and tot_shots_a >= 7           
                ):
                    msg = (
                        "⚽️ FAVORITA OSPITE PERDE\n\n"
                        f"Lega: {league}\n"
                        f"Partita: {home} vs {away}\n"
                        f"Ora inizio: {start}\n\n"
                        f"Minuto: {minute}'\n"
                        f"Handicap apertura casa: {handi_raw}\n\n"
                        f"Attacchi pericolosi: {datt_h} - {datt_a}\n"
                        f"Attacchi totali: {att_h} - {att_a}\n\n"
                        f"Tiri in porta: {on_h} - {on_a}\n"
                        f"Tiri fuori: {off_h} - {off_a}\n"
                        f"Tiri totali ospite: {tot_shots_a}\n"
                        f"Risultato attuale: {hg} - {ag}\n"
                    )
                    send_msg(msg)
                    state["r7"] = True

                # =============== REGOLA 3 ===============
                # Solo MASCHILI, casa -1.0..-2.5, minuto 59,
                # risultati ammessi, pericolosi >= 0,
                # tiri in porta >= 0, tiri totali >= 0
                if (
                    not state["r3"]                      # non ancora mandato
                    and not is_female_match(sex, home, away)   # solo maschi
                    and handi_val is not None
                    and -3.5 <= handi_val <= -1.0
                    and minute == 45
                    and (hg, ag) in [
                        (1,1),(2,2),(3,3)
                    ]
                    and datt_h >= 30
                    and on_h >= 4
                    and tot_shots_h >= 8
                ):
                    msg = (
                        "⚽️ FAVORITA CASA PAREGGIA\n\n"
                        f"Lega: {league}\n"
                        f"Partita: {home} vs {away}\n"
                        f"Ora inizio: {start}\n\n"
                        f"Minuto: {minute}'\n"
                        f"Handicap apertura casa: {handi_raw}\n\n"
                        f"Attacchi pericolosi: {datt_h} - {datt_a}\n"
                        f"Attacchi totali: {att_h} - {att_a}\n"
                        f"Tiri in porta: {on_h} - {on_a}\n"
                        f"Tiri fuori: {off_h} - {off_a}\n"
                        f"Tiri totali casa: {tot_shots_h}\n"
                        f"Risultato attuale: {hg} - {ag}\n"
                    )
                    send_msg(msg)
                    state["r3"] = True

                # =============== REGOLA 8 ===============
                # Solo MASCHILI, casa -1.0..-2.5, minuto 59,
                # risultati ammessi, pericolosi >= 0,
                # tiri in porta >= 0, tiri totali >= 0
                if (
                    not state["r8"]                      # non ancora mandato
                    and not is_female_match(sex, home, away)   # solo maschi
                    and handi_val is not None
                    and -3.5 <= handi_val <= -1.0
                    and minute == 45
                    and (hg, ag) in [
                        (0,1),(0,2),(1,2),(1,3),
                        (2,3),(2,4),(3,4)
                    ]
                    and datt_h >= 20
                    and on_h >= 3
                    and tot_shots_h >= 6
                ):
                    msg = (
                        "⚽️ FAVORITA CASA PERDE\n\n"
                        f"Lega: {league}\n"
                        f"Partita: {home} vs {away}\n"
                        f"Ora inizio: {start}\n\n"
                        f"Minuto: {minute}'\n"
                        f"Handicap apertura casa: {handi_raw}\n\n"
                        f"Attacchi pericolosi: {datt_h} - {datt_a}\n"
                        f"Attacchi totali: {att_h} - {att_a}\n"
                        f"Tiri in porta: {on_h} - {on_a}\n"
                        f"Tiri fuori: {off_h} - {off_a}\n"
                        f"Tiri totali casa: {tot_shots_h}\n"
                        f"Risultato attuale: {hg} - {ag}\n"
                    )
                    send_msg(msg)
                    state["r8"] = True

                # =============== REGOLA 4 ===============
                # Solo MASCHILI, casa -1.0..-2.5, minuto 45,
                # risultati ammessi, attacchi pericolosi >= 30,
                # tiri in porta >= 4, tiri totali >= 0
                if (
                    not state["r4"]                      # non ancora mandato
                    and not is_female_match(sex, home, away)   # solo maschi
                    and handi_val is not None
                    and -3.5 <= handi_val <= -0.0
                    and minute == 5
                    and (hg, ag) in [
                        (0,0),(3,2),(3,1)
                    ]
                    and datt_h >= 50
                    and on_h >= 0
                    and tot_shots_h >= 0
                ):
                    msg = (
                        "🚨 FAVORITA CASA CON GOL\n\n"
                        f"Lega: {league}\n"
                        f"Partita: {home} vs {away}\n"
                        f"Ora inizio: {start}\n\n"
                        f"Minuto: {minute}'\n"
                        f"Handicap apertura casa: {handi_raw}\n\n"
                        f"Attacchi pericolosi: {datt_h} - {datt_a}\n"
                        f"Attacchi totali: {att_h} - {att_a}\n"
                        f"Tiri in porta: {on_h} - {on_a}\n"
                        f"Tiri fuori: {off_h} - {off_a}\n"
                        f"Tiri totali casa: {tot_shots_h}\n"
                        f"Risultato attuale: {hg} - {ag}\n"
                    )
                    send_msg(msg)
                    state["r4"] = True

                # ================= REGOLA 5 =================
                # (come l’abbiamo testata prima, solo la favorita casa con handi -6..-1.0)
                if (
                    not state["r5"]                 # non ancora mandato
                    and not is_female_match(sex, home, away)   # solo maschi
                    and handi_val is not None
                    and -3.0 <= handi_val <= -0.0
                    and minute == 45
                    and (hg, ag) in [
                        (0,2),
                        (1,0),(1,2),(2,0),
                        (0,2),(2,1),(0,1)
                    ]  
                    and datt_h >= 35                 # pericolosi casa
                    and on_h >= 6
                    and tot_shots_h >= 9
                ):
                    msg = (
                        "⚽ REGOLA GOL LINE >=3.5\n\n"
                        f"Lega: {league}\n"
                        f"Partita: {home} vs {away}\n"
                        f"Ora inizio: {start}\n\n"
                        f"Minuto: {minute}'\n"
                        f"Handicap apertura casa: {handi_raw}\n\n"
                        f"Attacchi pericolosi: {datt_h} - {datt_a}\n"
                        f"Attacchi totali: {att_h} - {att_a}\n\n"
                        f"Tiri in porta: {on_h} - {on_a}\n"
                        f"Tiri fuori: {off_h} - {off_a}\n"
                        f"Tiri totali casa: {tot_shots_h}\n"
                        f"Risultato attuale: {hg} - {ag}\n"
                    )
                    send_msg(msg)
                    state["r5"] = True

                # ================= REGOLA 6 =================
                # (come l’abbiamo testata prima, solo la favorita casa con handi -6..-1.0)
                if (
                    not state["r6"]                 # non ancora mandato
                    and not is_female_match(sex, home, away)   # solo maschi
                    and handi_val is not None
                    and -4.0 <= handi_val <= -2.0
                    and minute == 8
                    and (hg, ag) in [
                        (0,1),(0,2)
                    ]  
                    and datt_h >= 0                 # pericolosi casa
                ):
                    msg = (
                        "⚽ REGOLA PRIMO TEMPO\n\n"
                        f"Lega: {league}\n"
                        f"Partita: {home} vs {away}\n"
                        f"Ora inizio: {start}\n\n"
                        f"Minuto: {minute}'\n"
                        f"Handicap apertura casa: {handi_raw}\n\n"
                        f"Attacchi pericolosi: {datt_h} - {datt_a}\n"
                        f"Attacchi totali: {att_h} - {att_a}\n\n"
                        f"Tiri in porta: {on_h} - {on_a}\n"
                        f"Tiri fuori: {off_h} - {off_a}\n"
                        f"Tiri totali casa: {tot_shots_h}\n"
                        f"Risultato attuale: {hg} - {ag}\n"
                    )
                    send_msg(msg)
                    state["r6"] = True

                # ================= REGOLA 9 =================
                # Solo MASCHILI, handi casa +3.5..+1.5, minuto 60,
                # pericolosi casa >= 10, tiri totali >= 1
                if (
                    not state["r9"]                 # non ancora mandato
                    and not is_female_match(sex, home, away)   # solo maschi
                    and handi_val is not None
                    and +1.0 <= handi_val <= +3.0
                    and minute == 45
                    and (hg, ag) in [
                        (0,0)
                    ]  
                    and datt_a >= 85                # attacchi pericolosi ospite
                    and on_a >= 6                   # tiri in porta ospite 
                    and tot_shots_h >= 11           
                ):
                    msg = (
                        "⚽️ FAVORITA OSPITE 0-0\n\n"
                        f"Lega: {league}\n"
                        f"Partita: {home} vs {away}\n"
                        f"Ora inizio: {start}\n\n"
                        f"Minuto: {minute}'\n"
                        f"Handicap apertura casa: {handi_raw}\n\n"
                        f"Attacchi pericolosi: {datt_h} - {datt_a}\n"
                        f"Attacchi totali: {att_h} - {att_a}\n\n"
                        f"Tiri in porta: {on_h} - {on_a}\n"
                        f"Tiri fuori: {off_h} - {off_a}\n"
                        f"Tiri totali ospite: {tot_shots_a}\n"
                        f"Risultato attuale: {hg} - {ag}\n"
                    )
                    send_msg(msg)
                    state["r9"] = True

                # =============== REGOLA 10 ===============
                # Solo MASCHILI, casa -1.0..-2.5, minuto 59,
                # risultati ammessi, pericolosi >= 0,
                # tiri in porta >= 0, tiri totali >= 0
                if (
                    not state["r10"]                      # non ancora mandato
                    and not is_female_match(sex, home, away)   # solo maschi
                    and handi_val is not None
                    and -3.5 <= handi_val <= -2.0
                    and minute == 20
                    and (hg, ag) in [
                        (0,0)
                    ]
                    and datt_h >= 12
                    and on_h >= 5
                    and tot_shots_h >= 9
                ):
                    msg = (
                        "⚽️ FAVORITA CASA al 20° PRIMO TEMPO\n\n"
                        f"Lega: {league}\n"
                        f"Partita: {home} vs {away}\n"
                        f"Ora inizio: {start}\n\n"
                        f"Minuto: {minute}'\n"
                        f"Handicap apertura casa: {handi_raw}\n\n"
                        f"Attacchi pericolosi: {datt_h} - {datt_a}\n"
                        f"Attacchi totali: {att_h} - {att_a}\n"
                        f"Tiri in porta: {on_h} - {on_a}\n"
                        f"Tiri fuori: {off_h} - {off_a}\n"
                        f"Tiri totali casa: {tot_shots_h}\n"
                        f"Risultato attuale: {hg} - {ag}\n"
                    )
                    send_msg(msg)
                    state["r10"] = True

            except Exception as e:
                print("Errore:", e)

        time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    main()
