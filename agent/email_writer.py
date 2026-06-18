import sys
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import anthropic
from datetime import datetime, timezone
from db.client import get_supabase_client
from config.settings import settings as _default_settings

_claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))

# ---------------------------------------------------------------------------
# Helpers interni
# ---------------------------------------------------------------------------

def _chiedi_claude(prompt: str) -> str:
    risposta = _claude.messages.create(
        model="claude-opus-4-8",
        max_tokens=512,
        thinking={"type": "adaptive"},
        messages=[{"role": "user", "content": prompt}],
    )
    for block in risposta.content:
        if block.type == "text":
            return block.text.strip()
    return ""


def _salva_email(
    lead_id: str | None,
    campaign_id: str | None,
    tipo: str,
    subject: str,
    body: str,
) -> None:
    client = get_supabase_client()
    client.table("emails").insert({
        "lead_id": lead_id,
        "campaign_id": campaign_id,
        "tipo": tipo,
        "stato": "draft",
        "subject": subject,
        "body": body,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


# Settori sanitari/assistenziali per cui citare l'esperienza Orama
_SETTORI_SANITARI = {
    "rsa", "residenza sanitaria", "casa di riposo", "struttura residenziale",
    "sanita", "sanità", "sanitario", "assistenziale", "assistenza",
    "clinica", "cliniche", "ospedale", "poliambulatorio", "ambulatorio",
    "farmacia", "farmaceutico", "medico", "medica", "salute",
    "home care", "cure domiciliari", "riabilitazione", "hospice",
}

def _e_settore_sanitario(settore: str) -> bool:
    s = settore.lower()
    return any(kw in s for kw in _SETTORI_SANITARI)


# ---------------------------------------------------------------------------
# 1. Email primo contatto
# ---------------------------------------------------------------------------

def genera_email_primo_contatto(lead: dict, s=None) -> dict:
    """
    Genera un'email di primo contatto personalizzata per il lead.
    Salva il draft nella tabella emails (tipo='first_contact').
    Restituisce {"subject": ..., "body": ...}.
    """
    if s is None:
        s = _default_settings

    import json

    nome = lead.get("nome") or "Buongiorno"
    cognome = lead.get("cognome") or ""
    ruolo = lead.get("ruolo") or "professionista"
    settore = lead.get("settore") or "settore di riferimento"
    azienda = lead.get("azienda") or "la vostra azienda"

    # Istruzione aggiuntiva per settore sanitario/assistenziale
    if _e_settore_sanitario(settore):
        nota_settore = (
            f'- Orama Energy lavora da tempo con realtà del settore sanitario e assistenziale: '
            f'menziona questa esperienza come punto di fiducia, in modo naturale e NON autoreferenziale. '
            f'Non citare mai nomi di clienti specifici.'
        )
    else:
        nota_settore = (
            f'- NON fare alcun riferimento al settore sanitario o alle RSA: '
            f'è irrilevante per questo lead e non va mai citato.'
        )

    sistema = """\
Sei il responsabile commerciale di Orama Energy & Projects, una società di consulenza energetica \
per PMI italiane. Il tuo compito è scrivere email di primo contatto calde, autentiche e \
consulenziali — non da venditore, ma da professionista che vuole capire se può essere utile.

IDENTITA' DI ORAMA ENERGY:
- Non vende una percentuale di risparmio generica, non fa promesse numeriche
- Il vero valore è: portare ordine, controllo e prevedibilità sulla voce energia, \
che per molti imprenditori è fonte di ansia e incertezza
- Offre: consulenza energetica, gestione delle commodity, monitoraggio dei consumi
- Il cliente ideale è qualsiasi PMI che oggi vive l'energia come costo imprevedibile \
e vuole qualcuno di fiducia che se ne occupi per loro, liberando tempo mentale
- Approccio umano, non tecnocratico: parla la lingua dell'imprenditore, non del tecnico
- Forte esperienza consolidata nel settore RSA e sanità privata (mai nomi di clienti)"""

    prompt = f"""{sistema}

Scrivi un'email di primo contatto in italiano per questo lead:

Mittente: {s.tuo_nome} di {s.tua_azienda} ({s.tua_email})
Destinatario: {nome} {cognome}, {ruolo} di {azienda}
Settore del lead: {settore}
Link Calendly per video call 15 minuti: {s.calendly_link}

REGOLE TASSATIVE:
- Subject: massimo 10 parole, specifico per il settore, non generico
- Body: massimo 130 parole, tono caldo, consulenziale, umano — non robotico
- Inizia con "Buongiorno {nome},"
- Presentati come {s.tuo_nome} di {s.tua_azienda} in modo naturale (una riga)
- Centra il messaggio su: controllo dei costi energia, prevedibilità di spesa, \
serenità operativa — calato sul contesto specifico del settore "{settore}" \
e sul ruolo "{ruolo}" (cosa significa per loro l'energia imprevedibile nel loro lavoro quotidiano?)
- NON inventare percentuali di risparmio (niente "25%", "30%" o simili)
- NON usare frasi generiche vuote come "ottimizzare i processi"
- Chiudi proponendo SOLO la video call Calendly di 15 minuti: {s.calendly_link}
- NON menzionare mai incontri fisici, trasferte o meeting in presenza
- Firma con "{s.tuo_nome}"
{nota_settore}

Rispondi SOLO con questo formato JSON, senza testo aggiuntivo prima o dopo:
{{
  "subject": "...",
  "body": "..."
}}"""

    print(f"[EmailWriter] Genero email primo contatto per {nome} {cognome} ({settore})...")
    testo = _chiedi_claude(prompt)

    try:
        pulito = testo.strip()
        # Rimuovi eventuali backtick markdown
        if pulito.startswith("```"):
            pulito = pulito.split("```", 2)[-1] if pulito.count("```") >= 2 else pulito
            pulito = pulito.removeprefix("json").strip().removesuffix("```").strip()
        # Trova il primo { e l'ultimo } per estrarre solo il JSON
        start = pulito.index("{")
        end = pulito.rindex("}") + 1
        dati = json.loads(pulito[start:end])
        subject = dati.get("subject", "").strip()
        body = dati.get("body", "").strip()
    except (json.JSONDecodeError, ValueError, AttributeError):
        subject = "Una riflessione sui costi energia per la vostra azienda"
        body = testo

    lead_id = lead.get("id")
    campaign_id = lead.get("campaign_id")

    _salva_email(lead_id, campaign_id, "first_contact", subject, body)

    print(f"[EmailWriter] OK - Subject: {subject}")
    print(f"[EmailWriter] OK - Parole nel body: {len(body.split())}")

    return {"subject": subject, "body": body}


# ---------------------------------------------------------------------------
# 2. Email push/qualification
# ---------------------------------------------------------------------------

def genera_email_push(lead: dict, s=None) -> dict:
    """
    Genera un'email di qualificazione con 3 domande chiuse per lead inbound/push.
    Salva il draft nella tabella emails (tipo='push_qualification').
    Restituisce {"subject": ..., "body": ...}.
    """
    if s is None:
        s = _default_settings

    nome = lead.get("nome") or "Buongiorno"
    cognome = lead.get("cognome") or ""
    ruolo = lead.get("ruolo") or "professionista"
    settore = lead.get("settore") or "settore di riferimento"
    azienda = lead.get("azienda") or "la vostra azienda"

    # Costruisci le soglie leggibili
    dipendenti_soglia = s.min_dipendenti
    fatturato_soglia = f"{int(s.min_fatturato / 1_000_000)}M" if s.min_fatturato >= 1_000_000 else f"{int(s.min_fatturato / 1_000)}K"
    finestra_giorni = s.urgency_window

    prompt = f"""Sei un consulente commerciale B2B. Scrivi un'email di qualificazione per un lead ad alta priorità in italiano.

Mittente: {s.tuo_nome} di {s.tua_azienda}
Destinatario: {nome} {cognome}, {ruolo} di {azienda} (settore: {settore})
Link Calendly: {s.calendly_link}

Contesto per le domande di qualificazione:
- Soglia dimensione aziendale: {dipendenti_soglia} dipendenti
- Soglia fatturato minimo: {fatturato_soglia}
- Finestra urgenza: entro {finestra_giorni} giorni

Regole TASSATIVE:
- Subject: urgente, personalizzato, max 10 parole
- Body: max 120 parole, tono diretto e orientato all'azione
- Inizia con "Buongiorno {nome},"
- Dopo la presentazione di {s.tuo_nome} di {s.tua_azienda}, includi ESATTAMENTE 3 domande chiuse (risposta Sì/No) per qualificare il lead:
  1. Una sulla dimensione aziendale (riferita a "{dipendenti_soglia} dipendenti")
  2. Una sul fatturato o budget (riferita a "{fatturato_soglia}")
  3. Una sull'urgenza o tempistica (riferita a "decisione entro {finestra_giorni} giorni")
- Chiudi proponendo SOLO la video call: {s.calendly_link}
- NON menzionare mai incontri fisici
- Firma con "{s.tuo_nome}"

Rispondi SOLO con questo formato JSON (nessun testo aggiuntivo):
{{
  "subject": "...",
  "body": "..."
}}"""

    print(f"[EmailWriter] Genero email push/qualification per {nome} {cognome} ({settore})...")
    testo = _chiedi_claude(prompt)

    import json
    try:
        pulito = testo.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
        dati = json.loads(pulito)
        subject = dati.get("subject", "").strip()
        body = dati.get("body", "").strip()
    except (json.JSONDecodeError, AttributeError):
        subject = "Qualificazione rapida — 3 domande"
        body = testo

    lead_id = lead.get("id")
    campaign_id = lead.get("campaign_id")

    _salva_email(lead_id, campaign_id, "push_qualification", subject, body)

    print(f"[EmailWriter] OK - Subject: {subject}")
    print(f"[EmailWriter] OK - Parole nel body: {len(body.split())}")

    return {"subject": subject, "body": body}


# ---------------------------------------------------------------------------
# 3. Batch
# ---------------------------------------------------------------------------

def genera_batch(campaign_id: str, settore_target: str, s=None) -> dict:
    """
    Genera email di primo contatto per tutti i lead con stato='ready' di una campagna.
    Restituisce {"elaborati": N, "riusciti": N, "errori": N}.
    """
    if s is None:
        s = _default_settings

    client = get_supabase_client()
    risposta = (
        client.table("leads")
        .select("*")
        .eq("campaign_id", campaign_id)
        .eq("stato", "ready")
        .execute()
    )
    leads = risposta.data

    if not leads:
        print(f"[EmailWriter] Nessun lead con stato 'ready' per campaign_id='{campaign_id}'.")
        return {"elaborati": 0, "riusciti": 0, "errori": 0}

    print(f"[EmailWriter] {len(leads)} lead da elaborare per campaign '{campaign_id}'...")

    n_riusciti = 0
    n_errori = 0

    for i, lead in enumerate(leads, start=1):
        nome_lead = f"{lead.get('nome', '')} {lead.get('cognome', '')}".strip()
        print(f"\n[{i}/{len(leads)}] {nome_lead} (id={lead.get('id')})")
        try:
            genera_email_primo_contatto(lead, s)
            n_riusciti += 1
        except Exception as e:
            print(f"[EmailWriter] ERRORE per {nome_lead}: {e}")
            n_errori += 1

    print(f"\n=== Riepilogo generazione email batch ===")
    print(f"  Campaign ID   : {campaign_id}")
    print(f"  Settore target: {settore_target}")
    print(f"  Elaborati     : {len(leads)}")
    print(f"  Riusciti      : {n_riusciti}")
    print(f"  Errori        : {n_errori}")
    print(f"=========================================\n")

    return {"elaborati": len(leads), "riusciti": n_riusciti, "errori": n_errori}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python agent/email_writer.py <campaign_id> <settore_target>")
        sys.exit(1)

    genera_batch(sys.argv[1], sys.argv[2])
