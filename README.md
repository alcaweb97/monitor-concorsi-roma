# 🔍 Monitor Concorsi Roma

Monitor automatico dei concorsi pubblici a Roma su [mininterno.net](https://www.mininterno.net/gu-nuovi).

**Cosa fa:**
- Controlla ogni 2 ore i nuovi bandi
- Filtra quelli effettivamente a Roma (esclude falsi positivi come Emilia-Romagna)
- Ti avvisa su Telegram solo quando escono concorsi **nuovi**

---

## 📋 Prerequisiti

1. Account GitHub (gratuito)
2. Account Telegram
3. Bot Telegram creato (vedi sotto)

---

## 🚀 Installazione passo-passo

### 1. Crea il repository su GitHub

1. Vai su [github.com/new](https://github.com/new)
2. Nome repository: `monitor-concorsi-roma`
3. **Spunta "Public"** (gratuito e illimitato)
4. Clicca **"Create repository"**

### 2. Carica i file

Nella pagina del nuovo repository, clicca **"uploading an existing file"** e carica questi file:
- `monitor.py`
- `.github/workflows/monitor.yml`
- `.gitignore`

Oppure usa la riga di comando (se hai Git installato):

```bash
git clone https://github.com/TUO_USERNAME/monitor-concorsi-roma.git
cd monitor-concorsi-roma
# copia qui i file monitor.py, .github/workflows/monitor.yml, .gitignore
git add .
git commit -m "Primo commit"
git push origin main
```

### 3. Configura i Secrets (token Telegram)

1. Dal repository GitHub, vai su **Settings → Secrets and variables → Actions**
2. Clicca **"New repository secret"**
3. Aggiungi questi due secrets:

| Nome | Valore |
|------|--------|
| `TELEGRAM_TOKEN` | Il token del tuo bot (da @BotFather) |
| `TELEGRAM_CHAT_ID` | Il tuo chat ID (da @userinfobot) |

### 4. Attiva il workflow

Il workflow parte automaticamente. Per testarlo subito:

1. Vai su **Actions** nel repository
2. Clicca su **"Monitor Concorsi Roma"**
3. Clicca **"Run workflow"** → **"Run workflow"**

Dopo pochi secondi, riceverai il messaggio su Telegram!

---

## 🤖 Creare il bot Telegram (se non l'hai già fatto)

1. Apri Telegram e cerca **@BotFather**
2. Scrivi `/newbot`
3. Segui le istruzioni e **copia il token**
4. Cerca **@userinfobot** e scrivi qualcosa per ottenere il tuo **chat ID**
5. **Scrivi un messaggio al tuo bot** (cerca il nome che hai scelto)

---

## ⚙️ Frequenza di controllo

Il workflow gira **ogni 2 ore** (cron: `17 */2 * * *`).

Per cambiare la frequenza, modifica il file `.github/workflows/monitor.yml`:
- Ogni ora: `17 * * * *`
- Ogni 3 ore: `17 */3 * * *`
- Una volta al giorno alle 9:17: `17 9 * * *`

---

## 📁 Struttura file

| File | Scopo |
|------|-------|
| `monitor.py` | Script principale (scraping + notifica) |
| `.github/workflows/monitor.yml` | Configurazione GitHub Actions |
| `state.json` | Storico concorsi già notificati (auto-generato) |
| `.gitignore` | Esclude file temporanei |

---

## 🔒 Sicurezza

- I token Telegram sono salvati nei **GitHub Secrets**, non nel codice
- Il repository è pubblico ma i secrets sono invisibili a tutti
- Chiunque trovi il bot su Telegram **non riceve nulla** se non è il tuo chat ID

---

## 🆘 Problemi comuni

| Problema | Soluzione |
|----------|-----------|
| "Token mancante" | Controlla che i secrets siano configurati correttamente |
| Nessun messaggio su Telegram | Devi aver scritto almeno un messaggio al tuo bot prima |
| Workflow non parte | Vai in Actions e clicca "Enable Actions" |

---

Creato con ❤️ da Kimi Work
