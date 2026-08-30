#!/usr/bin/env python3
"""
Monitor concorsi pubblici - Multi-sorgente
Fonti: mininterno.net, concorsando.it
Con deduplicazione cross-sito e notifica Telegram
"""

import hashlib
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

STATE_FILE = "state.json"

# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

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


def normalize_text(text: str) -> str:
    """Normalizza testo per confronto."""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return text


def compute_fingerprint(ente: str, posti: int | None, scadenza: str | None) -> str:
    """
    Crea un fingerprint univoco per deduplicazione cross-sito.
    Due concorsi con stesso ente, posti e scadenza sono considerati duplicati.
    """
    ente_norm = normalize_text(ente) if ente else ""
    posti_str = str(posti) if posti else ""
    scad_str = scadenza if scadenza else ""
    raw = f"{ente_norm}|{posti_str}|{scad_str}"
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Parser: mininterno.net
# ---------------------------------------------------------------------------

def parse_mininterno() -> list[dict]:
    url = "https://www.mininterno.net/gu-nuovi"
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

        fingerprint = compute_fingerprint(ente, posti, scadenza)

        contests.append({
            "source": "mininterno",
            "code": code,
            "text": text,
            "description": desc,
            "ente": ente,
            "posti": posti,
            "scadenza": scadenza,
            "url": f"https://www.mininterno.net/gxatto.asp?k={code}",
            "fingerprint": fingerprint,
        })

    return contests


# ---------------------------------------------------------------------------
# Parser: concorsando.it
# ---------------------------------------------------------------------------

def parse_concorsando() -> list[dict]:
    url = "https://www.concorsando.it/blog/"
    try:
        html = fetch_page(url)
    except Exception as e:
        print(f"[WARN] Errore download concorsando.it: {e}")
        return []

    flat = html.replace("\r", " ").replace("\n", " ")

    # Find article URLs (may appear multiple times in page)
    hrefs = re.findall(
        r'href=["\'](https://www\.concorsando\.it/blog/concorso[^"\']+)["\']',
        flat, re.IGNORECASE,
    )

    contests = []
    seen_urls = set()

    for href in hrefs:
        if href in seen_urls:
            continue
        seen_urls.add(href)

        # Derive title from URL path (e.g. concorso-comune-roma-2026 -> Concorso comune roma 2026)
        slug = href.rstrip('/').split('/')[-1]
        slug = re.sub(r'^[\d-]+', '', slug)  # Remove leading numbers/dashes
        title = slug.replace('-', ' ').replace('_', ' ').strip()
        title = title.capitalize()

        if len(title) < 10:
            continue

        # Try to extract posti from title
        posti = None
        m = re.search(r'(\d+)\s+posti', title, re.IGNORECASE)
        if not m:
            m = re.search(r' da\s+(\d+)\s', title, re.IGNORECASE)
        if m:
            posti = int(m.group(1))

        # Try to extract ente from title
        ente = None
        # Remove common prefixes
        clean = re.sub(r'^Concorso\s+', '', title, flags=re.IGNORECASE)
        # Try to find location/entity patterns
        ente_patterns = [
            r'^(.*?)(?:\s+da\s+\d+|\s+\d+\s+posti|$)',
            r'^(.*?)(?:\s+202[56]|$)',
        ]
        for pattern in ente_patterns:
            m = re.search(pattern, clean, re.IGNORECASE)
            if m:
                candidate = m.group(1).strip()
                if len(candidate) > 3:
                    ente = candidate
                    break

        if not ente:
            ente = title[:80]

        desc = title[:200]
        scadenza = None

        # Generate a unique code from URL
        code = "cc_" + slug[:30]

        fingerprint = compute_fingerprint(ente, posti, scadenza)

        contests.append({
            "source": "concorsando",
            "code": code,
            "text": title,
            "description": desc,
            "ente": ente,
            "posti": posti,
            "scadenza": scadenza,
            "url": href,
            "fingerprint": fingerprint,
        })

    return contests
    url = "https://www.concorsando.it/blog/"
    try:
        html = fetch_page(url)
    except Exception as e:
        print(f"[WARN] Errore download concorsando.it: {e}")
        return []

    flat = html.replace("\r", " ").replace("\n", " ")

    # Find article links: href="https://www.concorsando.it/blog/concorso-..."
    pattern = r'<a[^>]*href="(https://www\.concorsando\.it/blog/concorso[^"]+)"[^>]*>(.*?)</a>'
    matches = re.findall(pattern, flat, re.IGNORECASE | re.DOTALL)

    contests = []
    seen_urls = set()

    for href, content in matches:
        if href in seen_urls:
            continue
        seen_urls.add(href)

        text = re.sub(r"<[^>]+>", " ", content)
        text = re.sub(r"&[a-z]+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()

        if len(text) < 20:
            continue

        # Try to extract posti from title
        posti = None
        m = re.search(r'(\d+)\s+posti', text, re.IGNORECASE)
        if m:
            posti = int(m.group(1))

        # Try to extract ente from title
        # Common patterns: "Concorso [ENTE] [ROLE] da N posti"
        ente = None
        ente_patterns = [
            r'Concorso\s+([^:]+?)(?:\s+da\s+\d+|\s+\d+\s+posti)',
            r'Concorso\s+(.+?)(?:\s+202[56])',
        ]
        for pattern in ente_patterns:
            m = re.search(pattern, text, re.IGNORECASE)
            if m:
                ente = m.group(1).strip()
                if len(ente) > 3:
                    break

        # If no ente extracted, use first meaningful part of title
        if not ente:
            parts = text.split(':')
            if len(parts) > 1:
                ente = parts[0].strip()
            else:
                ente = text[:80]

        desc = text[:200]
        scadenza = None  # Not always available on listing page

        # Generate a unique code from URL
        code = href.rstrip('/').split('/')[-1][:20]

        fingerprint = compute_fingerprint(ente, posti, scadenza)

        contests.append({
            "source": "concorsando",
            "code": code,
            "text": text,
            "description": desc,
            "ente": ente,
            "posti": posti,
            "scadenza": scadenza,
            "url": href,
            "fingerprint": fingerprint,
        })

    return contests


# ---------------------------------------------------------------------------
# Filtro Roma
# ---------------------------------------------------------------------------

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
    text = contest["text"].lower()
    for neg in ROMA_NEGATIVE:
        if neg in text:
            return False
    for pos in ROMA_POSITIVE:
        if pos in text:
            return True
    # Also check ente and description
    check_text = (contest.get("ente") or "").lower() + " " + (contest.get("description") or "").lower()
    for pos in ROMA_POSITIVE:
        if pos in check_text:
            return True
    return False


# ---------------------------------------------------------------------------
# Telegram
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Stato
# ---------------------------------------------------------------------------

def load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Errore lettura stato: {e}")
    return {"seen_fingerprints": [], "last_run": None}


def save_state(state: dict) -> None:
    state["last_run"] = datetime.now().isoformat()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Messaggio
# ---------------------------------------------------------------------------

def build_message(contests: list[dict]) -> str:
    lines = [
        "🔔 <b>Nuovi concorsi a Roma!</b>",
        f"Trovati {len(contests)} nuovo/i bando/i.",
        "",
    ]
    for c in contests:
        source_icon = "🏛️" if c["source"] == "mininterno" else "📰"
        source_name = "mininterno.net" if c["source"] == "mininterno" else "concorsando.it"
        ente = html_module.escape(c['ente'] or 'Ente non specificato')
        desc = html_module.escape(c['description'][:180])
        posti = html_module.escape(str(c['posti'])) if c['posti'] else None
        scadenza = html_module.escape(c['scadenza']) if c['scadenza'] else None
        url = c['url']

        lines.append(f"{source_icon} <b>{ente}</b>")
        lines.append(f"   {desc}")
        if posti:
            lines.append(f"   🎯 Posti: {posti}")
        if scadenza:
            lines.append(f"   ⏰ Scadenza: {scadenza}")
        lines.append(f'   🔗 <a href="{url}">Vedi dettagli</a>')
        lines.append(f'   🏷️ <i>Fonte: {source_name}</i>')
        lines.append("")
    return "\n".join(lines)
    lines = [
        "🔔 <b>Nuovi concorsi a Roma!</b>",
        f"Trovati {len(contests)} nuovo/i bando/i.",
        "",
    ]
    for c in contests:
        source_icon = "🏛️" if c["source"] == "mininterno" else "📰"
        ente = html_module.escape(c['ente'] or 'Ente non specificato')
        desc = html_module.escape(c['description'][:180])
        posti = html_module.escape(str(c['posti'])) if c['posti'] else None
        scadenza = html_module.escape(c['scadenza']) if c['scadenza'] else None
        url = c['url']

        lines.append(f"{source_icon} <b>{ente}</b>")
        lines.append(f"   {desc}")
        if posti:
            lines.append(f"   🎯 Posti: {posti}")
        if scadenza:
            lines.append(f"   ⏰ Scadenza: {scadenza}")
        lines.append(f'   🔗 <a href="{url}">Vedi dettagli</a>')
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print(f"{'='*60}")
    print(f"Monitor Concorsi Roma - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"{'='*60}")

    # 1. Download da tutte le fonti
    print("[1/6] Download fonti...")
    all_contests = []
    print("       Parsing mininterno.net...")
    all_contests.extend(parse_mininterno())
    print(f"       -> {len([c for c in all_contests if c['source'] == 'mininterno'])} concorsi")
    print("       Parsing concorsando.it...")
    all_contests.extend(parse_concorsando())
    print(f"       -> {len([c for c in all_contests if c['source'] == 'concorsando'])} concorsi")

    # 2. Filtra Roma
    print("[2/6] Filtro Roma...")
    roma_contests = [c for c in all_contests if is_roma(c)]
    print(f"       {len(roma_contests)} concorsi a Roma (da tutte le fonti).")

    # 3. Deduplicazione cross-sito
    print("[3/6] Deduplicazione...")
    state = load_state()
    seen = set(state.get("seen_fingerprints", []))
    unique_contests = []
    skipped = 0
    for c in roma_contests:
        fp = c["fingerprint"]
        if fp in seen:
            skipped += 1
            print(f"       [SKIP] Duplicato: {c['ente'][:50]}...")
        else:
            unique_contests.append(c)
            seen.add(fp)
    print(f"       {len(unique_contests)} unici, {skipped} duplicati scartati.")

    # 4. Confronto storico (per retrocompatibilita, controlla anche i vecchi code)
    print("[4/6] Confronto storico...")
    old_seen = set(state.get("seen_codes", []))
    new_contests = [c for c in unique_contests if c["code"] not in old_seen]
    print(f"       {len(new_contests)} nuovi rispetto allo scorso controllo.")

    # 5. Notifica
    print("[5/6] Notifica...")
    if new_contests:
        msg = build_message(new_contests)
        send_telegram(msg)
    else:
        print("       Nessun nuovo concorso a Roma.")

    # 6. Salva stato
    print("[6/6] Salvataggio stato...")
    # Aggiorna sia fingerprints che codici per retrocompatibilita
    all_fp = {c["fingerprint"] for c in roma_contests}
    all_codes = {c["code"] for c in roma_contests}
    state["seen_fingerprints"] = sorted(seen | all_fp)
    state["seen_codes"] = sorted(old_seen | all_codes)
    save_state(state)

    print(f"{'='*60}")
    print("Fatto.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
