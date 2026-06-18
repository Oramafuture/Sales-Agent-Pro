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

    # Classifica il lead: PMI o azienda strutturata
    n_dip = lead.get("n_dipendenti") or 0
    fatturato = lead.get("fatturato") or 0.0
    is_pmi = (n_dip <= s.soglia_pmi_dipendenti) and (fatturato <= s.soglia_pmi_fatturato)
    tipo_azienda = "PMI" if is_pmi else "azienda strutturata"

    sistema = """\
Sei il responsabile commerciale di Orama Energy & Projects, una società di consulenza energetica \
per PMI italiane. Il tuo compito è scrivere email di primo contatto calde, autentiche e \
consulenziali — non da venditore, ma da professionista che vuole capire se può essere utile.

IDENTITA' DI ORAMA ENERGY:
- Non vende percentuali di risparmio generiche, non fa promesse numeriche
- Il vero valore è: portare ordine, controllo e prevedibilità sulla voce energia, \
che per molti imprenditori è fonte di ansia e incertezza
- Servizi offerti: consulenza energetica personalizzata, gestione delle commodity energetiche \
(luce e gas), monitoraggio e controllo dei consumi
- Il cliente ideale è qualsiasi PMI che oggi vive l'energia come costo imprevedibile \
e vuole qualcuno di fiducia che se ne occupi per loro
- Approccio umano, non tecnocratico: parla la lingua dell'imprenditore, non del tecnico
- Forte esperienza consolidata nel settore RSA e sanità privata (mai nomi di clienti)"""

    # Istruzioni comuni a entrambi i tipi: posizionamento come outsourcing
    outsourcing_note = """\
POSIZIONAMENTO CHIAVE (valido sempre):
- Non sappiamo se il destinatario gestisca personalmente l'energia o se lo faccia qualcun altro \
  in azienda: non importa — il messaggio è che Orama Energy diventa il referente esterno \
  che se ne occupa in toto, come un vero servizio in outsourcing
- L'energia smette di essere un'incombenza aziendale da delegare internamente: c'è qualcuno \
  fuori che la gestisce con professionalità, liberando tempo e risorse interne
- Mai assumere che il destinatario "segua le bollette di persona": parla dell'azienda, non solo \
  di lui/lei"""

    if is_pmi:
        istruzioni_tono = f"""\
Il lead è una PICCOLA IMPRESA ({n_dip} dip., fatturato {int(fatturato):,} EUR).
- Tono caldo, umano, diretto — come se parlassi con l'imprenditore di persona
- Focus su: Orama come outsourcing energetico che elimina un'incombenza aziendale, \
  restituisce tempo e serenità, porta prevedibilità di spesa
- Non entrare nei dettagli tecnici dei servizi, basta evocare che ci siamo noi a occuparcene
- Cala il messaggio sul settore "{settore}" e sul ruolo "{ruolo}": \
  cosa guadagna l'azienda quando smette di occuparsi di energia internamente?
{outsourcing_note}"""
    else:
        fatturato_fmt = f"{fatturato / 1_000_000:.1f}M" if fatturato >= 1_000_000 else f"{int(fatturato / 1_000)}K"
        istruzioni_tono = f"""\
Il lead è un'AZIENDA STRUTTURATA ({n_dip} dip., fatturato {fatturato_fmt} EUR).
- Tono professionale, consulenziale, con più contenuto concreto
- Presenta Orama come outsourcing energetico a tutti gli effetti: \
  consulenza personalizzata, gestione delle commodity luce e gas, monitoraggio consumi
- Tocca temi rilevanti per organizzazioni più grandi: prevedibilità di budget, \
  reportistica chiara, eventuale gestione multi-sito, riduzione del carico gestionale interno
- L'azienda non deve più dedicare risorse interne alla gestione energia: \
  c'è un partner esterno specializzato che se ne occupa
- Rimani concreto ma senza promesse numeriche
{outsourcing_note}"""

    prompt = f"""{sistema}

Scrivi un'email di primo contatto in italiano per questo lead:

Mittente: {s.tuo_nome} di {s.tua_azienda} ({s.tua_email})
Destinatario: {nome} {cognome}, {ruolo} di {azienda}
Settore del lead: {settore}
Link Calendly per video call 15 minuti: {s.calendly_link}

TIPO DI AZIENDA E TONO:
{istruzioni_tono}

REGOLE TASSATIVE (valide per tutti):
- Subject: massimo 10 parole, specifico per il settore, non generico
- Body: massimo 130 parole
- Inizia con "Buongiorno {nome},"
- Presentati come {s.tuo_nome} di {s.tua_azienda} in modo naturale (una riga)
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

    print(f"[EmailWriter] Genero email primo contatto per {nome} {cognome} ({settore}) [{tipo_azienda}]...")
    testo = _chiedi_claude(prompt)

    try:
        # Estrai il blocco JSON cercando il primo { e l'ultimo } — robusto a backtick markdown
        start = testo.index("{")
        end = testo.rindex("}") + 1
        dati = json.loads(testo[start:end])
        subject = dati.get("subject", "").strip()
        body = dati.get("body", "").strip()
        if not subject or not body:
            raise ValueError("subject o body vuoti")
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
        start = testo.index("{")
        end = testo.rindex("}") + 1
        dati = json.loads(testo[start:end])
        subject = dati.get("subject", "").strip()
        body = dati.get("body", "").strip()
        if not subject or not body:
            raise ValueError("subject o body vuoti")
    except (json.JSONDecodeError, ValueError, AttributeError):
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
