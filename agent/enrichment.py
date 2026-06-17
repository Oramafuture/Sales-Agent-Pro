import sys
import time
import os
import requests
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from db.client import get_supabase_client

HUNTER_API_KEY = os.environ.get("HUNTER_API_KEY", "")
HUNTER_EMAIL_FINDER_URL = "https://api.hunter.io/v2/email-finder"


def _trova_email_hunter(nome: str, cognome: str, dominio: str) -> dict | None:
    """
    Chiama Hunter.io email-finder e restituisce:
      {"email": "...", "confidenza": 0-100} oppure None se non trovata.
    """
    if not HUNTER_API_KEY:
        print("[Hunter] HUNTER_API_KEY non configurata, skip.")
        return None

    try:
        resp = requests.get(
            HUNTER_EMAIL_FINDER_URL,
            params={
                "first_name": nome,
                "last_name": cognome,
                "domain": dominio,
                "api_key": HUNTER_API_KEY,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json().get("data", {})
        email = data.get("email")
        score = data.get("score", 0)
        if email:
            return {"email": email, "confidenza": score}
        return None
    except requests.RequestException as e:
        print(f"[Hunter] Errore chiamata API: {e}")
        return None


def _estrai_dominio(sito_web: str | None, azienda: str | None) -> str | None:
    """Ricava il dominio da sito_web oppure costruisce un guess dall'azienda."""
    if sito_web:
        dominio = (
            sito_web.replace("https://", "")
                    .replace("http://", "")
                    .replace("www.", "")
                    .split("/")[0]
                    .strip()
        )
        return dominio if dominio else None
    return None


def _registra_activity(client, lead_id: str, campaign_id: str | None, payload: dict) -> None:
    client.table("activities").insert({
        "tipo": "lead_enriched",
        "descrizione": f"Arricchimento lead {lead_id}: {payload.get('esito', 'n/d')}",
        "payload": payload,
        "lead_id": lead_id,
        "campaign_id": campaign_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()


def arricchisci_lead(lead: dict) -> dict:
    """
    Arricchisce un singolo lead:
    - cerca email via Hunter.io se mancante
    - aggiorna confidenza con lo score Hunter
    - aggiorna stato: 'ready' se email presente, 'new' con warning altrimenti
    - registra evento 'lead_enriched' in activities

    Restituisce il lead aggiornato.
    """
    client = get_supabase_client()
    lead_id = lead.get("id")
    campaign_id = lead.get("campaign_id")
    email = lead.get("email")
    nome = lead.get("nome") or ""
    cognome = lead.get("cognome") or ""

    aggiornamenti: dict = {}
    payload: dict = {"lead_id": lead_id}

    if not email:
        dominio = _estrai_dominio(lead.get("sito_web"), lead.get("azienda"))

        if nome and cognome and dominio:
            print(f"[Enrichment] Cerco email per {nome} {cognome} @ {dominio} ...")
            risultato = _trova_email_hunter(nome, cognome, dominio)

            if risultato:
                email = risultato["email"]
                aggiornamenti["email"] = email
                aggiornamenti["confidenza"] = risultato["confidenza"]
                aggiornamenti["stato"] = "ready"
                payload["esito"] = "email_trovata"
                payload["email_trovata"] = email
                payload["score_hunter"] = risultato["confidenza"]
                print(f"[Enrichment] Email trovata: {email} (score: {risultato['confidenza']})")
            else:
                aggiornamenti["stato"] = "new"
                payload["esito"] = "email_non_trovata"
                payload["warning"] = "Hunter.io non ha restituito un'email valida"
                print(f"[Enrichment] WARN: email non trovata per {nome} {cognome}")
        else:
            aggiornamenti["stato"] = "new"
            payload["esito"] = "dati_insufficienti"
            payload["warning"] = "Nome, cognome o dominio mancanti — impossibile cercare email"
            print(f"[Enrichment] WARN: dati insufficienti per cercare email (lead_id={lead_id})")
    else:
        # Email già presente: porta direttamente a 'ready'
        aggiornamenti["stato"] = "ready"
        payload["esito"] = "email_gia_presente"
        payload["email"] = email
        print(f"[Enrichment] Email già presente ({email}), stato → ready")

    aggiornamenti["updated_at"] = datetime.now(timezone.utc).isoformat()

    if lead_id:
        client.table("leads").update(aggiornamenti).eq("id", lead_id).execute()
        _registra_activity(client, lead_id, campaign_id, payload)

    return {**lead, **aggiornamenti}


def arricchisci_batch(campaign_id: str) -> dict:
    """
    Arricchisce tutti i lead con stato 'new' appartenenti a campaign_id.
    Pausa di 1 secondo tra le chiamate per rispettare i rate limit di Hunter.io.

    Restituisce {"elaborati": N, "ready": N, "warning": N}.
    """
    client = get_supabase_client()

    risposta = (
        client.table("leads")
        .select("*")
        .eq("campaign_id", campaign_id)
        .eq("stato", "new")
        .execute()
    )
    leads = risposta.data

    if not leads:
        print(f"[Enrichment] Nessun lead con stato 'new' trovato per campaign_id='{campaign_id}'.")
        return {"elaborati": 0, "ready": 0, "warning": 0}

    print(f"[Enrichment] {len(leads)} lead da arricchire per campaign '{campaign_id}'...")

    n_ready = 0
    n_warning = 0

    for i, lead in enumerate(leads, start=1):
        print(f"\n[{i}/{len(leads)}] Lead: {lead.get('nome', '')} {lead.get('cognome', '')} (id={lead.get('id')})")
        risultato = arricchisci_lead(lead)

        if risultato.get("stato") == "ready":
            n_ready += 1
        else:
            n_warning += 1

        if i < len(leads):
            time.sleep(1)

    print(f"\n=== Riepilogo arricchimento batch ===")
    print(f"  Campaign ID  : {campaign_id}")
    print(f"  Elaborati    : {len(leads)}")
    print(f"  Pronti (ready): {n_ready}")
    print(f"  Warning (new) : {n_warning}")
    print(f"=====================================\n")

    return {"elaborati": len(leads), "ready": n_ready, "warning": n_warning}


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python agent/enrichment.py <campaign_id>")
        sys.exit(1)

    arricchisci_batch(sys.argv[1])
