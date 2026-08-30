#!/usr/bin/env python3
"""
Riepilogo settimanale concorsi Roma
Invia ogni domenica un resoconto di tutti i concorsi attivi a Roma.
"""

import html as html_module
import json
import os
import re
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from datetime import datetime, timedelta

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "")


def fetch_page(url: str) -> str:
    req = Request(url, headers={
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    })
    with urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def parse_mininterno() -> list[dict]:
    url = "https://www.mininterno.net/gu-concorsi"
    html = fetch_page(url)
    flat = html.replace("\r", " ").replace("\n", " ")

    contests = []
    matches = re.findall(
        r'<a\s+href="gxatto\.asp\?k=([^"]+)"[^>]*>(.*?)</a>',
        flat, re.IGNORECASE | re.DOTALL,
    )

    for code, content in matches:
        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"&nbsp;", " ", text)
        text = re.sub(r"&[a-z]+;", " ", text)
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
            "source": "mininterno",
            "ente": ente,
            "posti": posti,
            "scadenza": scadenza,
            "url": f"https://www.mininterno.net/gxatto.asp?k={code}",
        })

    return contests


ROMA_POSITIVE = [
    "sede di roma", "comune di roma", "provincia di roma",
    "citta metropolitana di roma", "città metropolitana di roma",
    "universita di roma", "università di roma",
    "universita degli studi di roma", "università degli studi di roma",
    "tor vergata", "roma tre", "roma 3", "sapienza", "la sapienza",
    "forze armate - roma", "ministero - roma",
    "roma,", "roma.", "roma -", "roma)", " (roma)",
    "di roma ", "a roma ", "in roma ", "per roma ", "presso roma",
    "regione lazio", "asl roma", "a.s.l. roma",
    "ospedale di roma", "ospedale roma",
    "camera di commercio roma", "inps roma",
    "agenzia delle entrate roma", "provincia roma",
]

ROMA_NEGATIVE = ["emilia-romagna", "emilia romagna"]


def is_roma(contest: dict) -> bool:
    text = contest.get("ente", "").lower() + " " + contest.get("description", "").lower()
    for neg in ROMA_NEGATIVE:
        if neg in text:
            return False
    for pos in ROMA_POSITIVE:
        if pos in text:
            return True
    return False


def parse_scadenza(scadenza_str: str) -> datetime | None:
    """Converte stringa scadenza in datetime per confronti."""
    if not scadenza_str:
        return None
    # Formati comuni: 25/9/2026, 25-09-2026, ecc.
    patterns = [
        r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{4})',
        r'(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})',
    ]
    for p in patterns:
        m = re.search(p, scadenza_str)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000
            try:
                return datetime(y, mo, d)
            except ValueError:
                return None
    return None


def send_telegram(message: str) -> bool:
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("[WARN] Token Telegram o chat_id mancanti.")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }).encode("utf-8")

    try:
        req = Request(url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("ok", False)
    except Exception as e:
        print(f"[ERR] Telegram: {e}")
        return False


def build_summary(contests: list[dict]) -> str:
    oggi = datetime.now()
    prossima_settimana = oggi + timedelta(days=7)

    # Ordina per scadenza
    contests_sorted = sorted(contests, key=lambda c: parse_scadenza(c.get("scadenza", "")) or datetime(2099, 12, 31))

    # Separa in scadenza imminente e altri
    in_scadenza = []
    altri = []
    for c in contests_sorted:
        scad = parse_scadenza(c.get("scadenza"))
        if scad and scad <= prossima_settimana:
            in_scadenza.append(c)
        else:
            altri.append(c)

    lines = [
        f"📅 <b>RIEPILOGO SETTIMANALE CONCORSI ROMA</b>",
        f"<i>{oggi.strftime('%d/%m/%Y')}</i>",
        "",
        f"Totale concorsi attivi a Roma: <b>{len(contests)}</b>",
        "",
    ]

    if in_scadenza:
        lines.append("🚨 <b>SCADENZA IMMINENTE (entro 7 giorni):</b>")
        lines.append("")
        for c in in_scadenza:
            ente = html_module.escape(c.get('ente') or 'Ente N/D')
            posti = f" ({c['posti']} posti)" if c.get('posti') else ""
            scad = c.get('scadenza', 'N/D')
            lines.append(f"⏰ <b>{ente}</b>{posti}")
            lines.append(f"   Scade il: <b>{scad}</b>")
            lines.append(f'   🔗 <a href="{c["url"]}">Vedi dettagli</a>')
            lines.append("")

    if altri:
        lines.append("📋 <b>ALTRI CONCORSI ATTIVI:</b>")
        lines.append("")
        for c in altri[:10]:  # Limita a 10 per non mandare messaggi troppo lunghi
            ente = html_module.escape(c.get('ente') or 'Ente N/D')
            posti = f" ({c['posti']} posti)" if c.get('posti') else ""
            scad = c.get('scadenza', 'N/D')
            lines.append(f"• <b>{ente}</b>{posti} — scade {scad}")
            lines.append(f'  🔗 <a href="{c["url"]}">Vedi dettagli</a>')
            lines.append("")

        if len(altri) > 10:
            lines.append(f"<i>...e altri {len(altri) - 10} concorsi.</i>")
            lines.append("")

    lines.append("Buona settimana! 💪")
    return "\n".join(lines)


def main() -> int:
    print(f"{'='*60}")
    print(f"Riepilogo Settimanale - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    print("[1/3] Download concorsi...")
    contests = parse_mininterno()
    print(f"       Trovati {len(contests)} concorsi totali.")

    print("[2/3] Filtro Roma...")
    roma_contests = [c for c in contests if is_roma(c)]
    print(f"       {len(roma_contests)} concorsi a Roma.")

    print("[3/3] Invio riepilogo...")
    if roma_contests:
        msg = build_summary(roma_contests)
        send_telegram(msg)
    else:
        send_telegram("📅 <b>Riepilogo settimanale</b>\n\nNessun concorso a Roma attualmente attivo.")

    print("Fatto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
