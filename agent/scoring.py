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
from config.settings import settings

_claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY", ""))


def _chiedi_claude(prompt: str) -> str:
    """Chiama Claude e restituisce il testo della risposta."""
    risposta = _claude.messages.create(
        model="claude-opus-4-8",
        max_tokens=256,
        messages=[{"role": "user", "content": prompt}]
    )
    for block in risposta.content:
        if block.type == "text":
            return block.text.strip()
    return ""


def _score_fit_aziendale(settore_lead: str | None, settore_target: str) -> float:
    """
    Ritorna un punteggio 0-1 per il fit aziendale.
    Match esatto = 1.0, settore correlato (giudicato da Claude) = 0-0.8, nessun match = 0.
    """
    if not settore_lead:
        return 0.0

    if settore_lead.lower().strip() == settore_target.lower().strip():
        return 1.0

    prompt = (
        f"Valuta su una scala da 0 a 10 l'affinità commerciale tra questi due settori B2B:\n"
        f"Settore 1: {settore_lead}\n"
        f"Settore 2: {settore_target}\n\n"
        f"Rispondi SOLO con un numero intero da 0 a 10. Nessun testo aggiuntivo."
    )
    try:
        testo = _chiedi_claude(prompt)
        valore = int("".join(c for c in testo if c.isdigit() or c == ".").split(".")[0])
        valore = max(0, min(10, valore))
        return round(valore / 10 * 0.8, 3)   # max 0.8 se non è match esatto
    except Exception:
        return 0.0


def _score_dimensione(n_dipendenti: int | None) -> float:
    """Punteggio crescente in base ai dipendenti rispetto a min_dipendenti. Max a ~200 dip."""
    if n_dipendenti is None:
        return 0.0
    minimo = max(1, settings.min_dipendenti)
    if n_dipendenti < minimo:
        return 0.0
    ottimale = 200
    if n_dipendenti >= ottimale:
        return 1.0
    return round((n_dipendenti - minimo) / (ottimale - minimo), 3)


def _score_fatturato(fatturato: float | None) -> float:
    """Punteggio proporzionale rispetto a min_fatturato. Max a 10× il minimo."""
    if fatturato is None:
        return 0.0
    minimo = max(1, settings.min_fatturato)
    if fatturato < minimo:
        return 0.0
    ottimale = minimo * 10
    if fatturato >= ottimale:
        return 1.0
    return round((fatturato - minimo) / (ottimale - minimo), 3)


def _score_urgenza(note: str | None) -> float:
    """
    Chiede a Claude di stimare l'urgenza dai campi testuali del lead.
    Ritorna un valore 0-1. Default neutro = 0.5.
    """
    if not note or not note.strip():
        return 0.5

    prompt = (
        f"Analizza queste note su un lead B2B e stima l'urgenza di acquisto su scala 0-10:\n"
        f"Note: {note}\n\n"
        f"Rispondi SOLO con un numero intero da 0 a 10. Nessun testo aggiuntivo."
    )
    try:
        testo = _chiedi_claude(prompt)
        valore = int("".join(c for c in testo if c.isdigit() or c == ".").split(".")[0])
        return round(max(0, min(10, valore)) / 10, 3)
    except Exception:
        return 0.5


def calcola_score(lead: dict, settore_target: str) -> dict:
    """
    Calcola il PriorityScore (0-100) e la categoria (A/B/C) per un singolo lead.
    Aggiorna il lead su Supabase e registra 'score_calculated' nelle activities.

    Pesi:
        fit_aziendale  40%
        dimensione     30%
        fatturato      20%
        urgenza        10%
    """
    lead_id = lead.get("id")

    s_fit = _score_fit_aziendale(lead.get("settore"), settore_target)
    s_dim = _score_dimensione(lead.get("n_dipendenti"))
    s_fat = _score_fatturato(lead.get("fatturato"))
    s_urg = _score_urgenza(lead.get("note"))

    score = round(
        s_fit * 40 + s_dim * 30 + s_fat * 20 + s_urg * 10
    )

    if score >= settings.soglia_a:
        categoria = "A"
    elif score >= settings.soglia_b:
        categoria = "B"
    else:
        categoria = "C"

    dettagli = {
        "score": score,
        "categoria": categoria,
        "fit_aziendale": s_fit,
        "dimensione": s_dim,
        "fatturato": s_fat,
        "urgenza": s_urg,
        "settore_target": settore_target,
    }

    print(
        f"[Scoring] Lead {lead_id} | score={score} | cat={categoria} | "
        f"fit={s_fit} dim={s_dim} fat={s_fat} urg={s_urg}"
    )

    if lead_id:
        client = get_supabase_client()
        now = datetime.now(timezone.utc).isoformat()

        client.table("leads").update({
            "score": score,
            "categoria": categoria,
            "updated_at": now,
        }).eq("id", lead_id).execute()

        client.table("activities").insert({
            "tipo": "score_calculated",
            "descrizione": f"Score calcolato: {score} (cat. {categoria})",
            "payload": dettagli,
            "lead_id": lead_id,
            "campaign_id": lead.get("campaign_id"),
            "created_at": now,
        }).execute()

    return {**lead, **dettagli}


def calcola_score_batch(campaign_id: str, settore_target: str) -> dict:
    """
    Calcola il punteggio di tutti i lead con stato='ready' per una campaign.
    Restituisce {"elaborati": N, "A": N, "B": N, "C": N}.
    """
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
        print(f"[Scoring] Nessun lead con stato 'ready' per campaign_id='{campaign_id}'.")
        return {"elaborati": 0, "A": 0, "B": 0, "C": 0}

    print(f"[Scoring] {len(leads)} lead da valutare per campaign '{campaign_id}'...")

    conteggi: dict[str, int] = {"A": 0, "B": 0, "C": 0}

    for i, lead in enumerate(leads, start=1):
        print(f"\n[{i}/{len(leads)}] {lead.get('nome', '')} {lead.get('cognome', '')} (id={lead.get('id')})")
        risultato = calcola_score(lead, settore_target)
        cat = risultato.get("categoria", "C")
        conteggi[cat] = conteggi.get(cat, 0) + 1

    print(f"\n=== Riepilogo scoring batch ===")
    print(f"  Campaign ID     : {campaign_id}")
    print(f"  Settore target  : {settore_target}")
    print(f"  Elaborati       : {len(leads)}")
    for cat in ("A", "B", "C"):
        print(f"  Categoria {cat}     : {conteggi[cat]}")
    print(f"===============================\n")

    return {"elaborati": len(leads), **conteggi}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python agent/scoring.py <campaign_id> <settore_target>")
        sys.exit(1)

    calcola_score_batch(sys.argv[1], sys.argv[2])
