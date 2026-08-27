#!/usr/bin/env python3
"""
Monitor concorsi pubblici su mininterno.net
Versione per GitHub Actions — legge token da variabili d'ambiente
"""

import html as html_module
import json
import os
import re
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from datetime import datetime

# ---------------------------------------------------------------------------
# Configurazione da variabili d'ambiente (per GitHub Actions)
# ---------------------------------------------------------------------------
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")

# File di stato
STATE_FILE = "state.json"
URL = "https://www.mininterno.net/gu-nuovi"

# ---------------------------------------------------------------------------
# Roma filter keywords
# ---------------------------------------------------------------------------
ROMA_POSITIVE = [
    "sede di roma",
    "comune di roma",
    "provincia di roma",
    "citta metropolitana di roma",
    "città metropolitana di roma",
    "universita di roma",
    "università di roma",
    "universita degli studi di roma",
    "università degli studi di roma",
    "tor vergata",
    "roma tre",
    "roma 3",
    "sapienza",
    "la sapienza",
    "forze armate - roma",
    "ministero - roma",
    "roma,",
    "roma.",
    "roma -",
    "roma)",
    " (roma)",
    "di roma ",
    "a roma ",
    "in roma ",
    "per roma ",
    "presso roma",
    "regione lazio",
    "asl roma",
    "a.s.l. roma",
    "ospedale di roma",
    "ospedale roma",
    "camera di commercio roma",
    "inps roma",
    "agenzia delle entrate roma",
    "provincia roma",
]

ROMA_NEGATIVE = [
    "emilia-romagna",
    "emilia romagna",
]


def fetch_page(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        },
    )
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_contests(html: str) -> list[dict]:
    contests = []
    flat = html.replace("\r", " ").replace("\n", " ")

    matches = re.findall(
        r'<a\s+href="gxatto\.asp\?k=([^"]+)"[^>]*>(.*?)</a>',
        flat,
        re.IGNORECASE | re.DOTALL,
    )

    for code, content in matches:
        is_new = "newc.gif" in content.lower()
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&agrave;", "à", text)
        text = re.sub(r"&egrave;", "è", text)
        text = re.sub(r"&igrave;", "ì", text)
        text = re.sub(r"&ograve;", "ò", text)
        text = re.sub(r"&ugrave;", "ù", text)
        text = re.sub(r"&eacute;", "é", text)
        text = re.sub(r"\s+", " ", text).strip()

        scadenza = None
        m = re.search(r"Scadenza:\s*([^\s]+)", text)
        if m:
            scadenza = m.group(1)

        posti = None
        m = re.search(r"Posti:\s*(\d+)", text)
        if m:
            posti = int(m.group(1))

        ente = None
        parts = [p.strip() for p in re.split(r"[.!?;]", text) if len(p.strip()) > 3]
        for part in reversed(parts[-5:]):
            if re.match(r"^\d+[\/\-]", part):
                continue
            if "scadenza" in part.lower():
                continue
            if "posti" in part.lower() and len(part) < 20:
                continue
            if len(part) > 5:
                ente = part
                break

        desc = text[:200]
        if "Concorso (scad." in text:
            idx = text.find("Concorso (scad.")
            if idx > 0:
                desc = text[:idx].strip()

        contests.append({
            "code": code,
            "is_new": is_new,
            "text": text,
            "description": desc,
            "ente": ente,
            "posti": posti,
            "scadenza": scadenza,
            "url": f"https://www.mininterno.net/gxatto.asp?k={code}",
        })

    return contests


def is_roma(contest: dict) -> bool:
    text = contest["text"].lower()
    for neg in ROMA_NEGATIVE:
        if neg in text:
            return False
    for pos in ROMA_POSITIVE:
        if pos in text:
            return True
    return False


def send_telegram(message: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Token Telegram o chat_id mancanti.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }).encode("utf-8")

    try:
        req = Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            if result.get("ok"):
                print("[OK] Notifica Telegram inviata.")
                return True
            else:
                print(f"[ERR] Telegram: {result}")
                return False
    except Exception as e:
        print(f"[ERR] Errore invio Telegram: {e}")
        return False


def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Errore lettura stato: {e}")
    return {"seen_codes": [], "last_run": None}


def save_state(state: dict) -> None:
    state["last_run"] = datetime.now().isoformat()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def build_message(contests: list[dict]) -> str:
    lines = [
        "🔔 <b>Nuovi concorsi a Roma!</b>",
        f"Trovati {len(contests)} nuovo/i bando/i.",
        "",
    ]
    for c in contests:
        ente = html_module.escape(c['ente'] or 'Ente non specificato')
        desc = html_module.escape(c['description'][:180])
        posti = html_module.escape(str(c['posti'])) if c['posti'] else None
        scadenza = html_module.escape(c['scadenza']) if c['scadenza'] else None
        url = c['url']

        lines.append(f"📌 <b>{ente}</b>")
        lines.append(f"   {desc}")
        if posti:
            lines.append(f"   🎯 Posti: {posti}")
        if scadenza:
            lines.append(f"   ⏰ Scadenza: {scadenza}")
        lines.append(f'   🔗 <a href="{url}">Vedi dettagli</a>')
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    print(f"{'='*60}")
    print(f"Monitor Concorsi Roma - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    print("[1/5] Download pagina...")
    try:
        html = fetch_page(URL)
    except Exception as e:
        print(f"[ERR] Download fallito: {e}")
        return 1

    print("[2/5] Parsing concorsi...")
    all_contests = parse_contests(html)
    print(f"       Trovati {len(all_contests)} concorsi totali.")

    print("[3/5] Filtro Roma...")
    roma_contests = [c for c in all_contests if is_roma(c)]
    print(f"       {len(roma_contests)} concorsi a Roma.")

    print("[4/5] Confronto storico...")
    state = load_state()
    seen = set(state.get("seen_codes", []))
    new_contests = [c for c in roma_contests if c["code"] not in seen]
    print(f"       {len(new_contests)} nuovi rispetto allo scorso controllo.")

    print("[5/5] Notifica e salvataggio...")
    if new_contests:
        msg = build_message(new_contests)
        send_telegram(msg)
        for c in new_contests:
            seen.add(c["code"])
        state["seen_codes"] = sorted(seen)
    else:
        print("       Nessun nuovo concorso a Roma.")

    all_roma_codes = {c["code"] for c in roma_contests}
    state["seen_codes"] = sorted(seen | all_roma_codes)
    save_state(state)

    print(f"{'='*60}")
    print("Fatto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
