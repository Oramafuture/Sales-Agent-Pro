import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
from datetime import datetime, timezone
from db.client import get_supabase_client

# Mappa nomi colonne CSV -> colonne tabella leads
COLONNE_MAP = {
    # nome
    "nome": "nome",
    "first_name": "nome",
    "firstname": "nome",
    "name": "nome",
    # cognome
    "cognome": "cognome",
    "last_name": "cognome",
    "lastname": "cognome",
    "surname": "cognome",
    # email
    "email": "email",
    "e_mail": "email",
    "mail": "email",
    # telefono
    "telefono": "telefono",
    "phone": "telefono",
    "tel": "telefono",
    "cellulare": "telefono",
    "mobile": "telefono",
    # azienda
    "azienda": "azienda",
    "company": "azienda",
    "azienda_nome": "azienda",
    "ragione_sociale": "azienda",
    # ruolo
    "ruolo": "ruolo",
    "role": "ruolo",
    "job_title": "ruolo",
    "qualifica": "ruolo",
    "posizione": "ruolo",
    # settore
    "settore": "settore",
    "industry": "settore",
    "sector": "settore",
    # dipendenti
    "n_dipendenti": "n_dipendenti",
    "dipendenti": "n_dipendenti",
    "employees": "n_dipendenti",
    "num_dipendenti": "n_dipendenti",
    # fatturato
    "fatturato": "fatturato",
    "revenue": "fatturato",
    "turnover": "fatturato",
    # area geografica
    "area_geografica": "area_geografica",
    "area": "area_geografica",
    "regione": "area_geografica",
    "provincia": "area_geografica",
    "citta": "area_geografica",
    "city": "area_geografica",
    # sito web
    "sito_web": "sito_web",
    "website": "sito_web",
    "sito": "sito_web",
    "url": "sito_web",
}

COLONNE_LEADS = [
    "nome", "cognome", "email", "telefono", "azienda", "ruolo",
    "settore", "n_dipendenti", "fatturato", "area_geografica", "sito_web",
]


def _normalizza_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """Rinomina le colonne del CSV usando COLONNE_MAP e aggiunge i campi fissi."""
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]

    rename = {col: COLONNE_MAP[col] for col in df.columns if col in COLONNE_MAP}
    df = df.rename(columns=rename)

    # Tieni solo le colonne utili
    colonne_presenti = [c for c in COLONNE_LEADS if c in df.columns]
    df = df[colonne_presenti].copy()

    # Pulizia: strip stringhe e None per valori vuoti
    for col in df.select_dtypes(include="object").columns:
        df[col] = df[col].str.strip().replace("", None)

    # Campi fissi
    df["canale_origine"] = "csv"
    df["stato"] = "new"
    df["confidenza"] = 80

    return df


def carica_csv(percorso_file: str, campaign_id: str) -> dict:
    """
    Carica lead da un file CSV in Supabase.

    Restituisce un dict con le chiavi:
      - inseriti: numero di lead inseriti
      - duplicati: numero di righe saltate per email duplicata
    """
    percorso = Path(percorso_file)
    if not percorso.exists():
        raise FileNotFoundError(f"File non trovato: {percorso_file}")

    df = pd.read_csv(percorso)
    if df.empty:
        print("Il file CSV è vuoto.")
        return {"inseriti": 0, "duplicati": 0}

    df = _normalizza_dataframe(df)

    if "email" not in df.columns:
        raise ValueError("Il CSV non contiene una colonna email (o equivalente). Impossibile procedere.")

    # Rimuovi righe senza email
    df = df.dropna(subset=["email"])

    client = get_supabase_client()

    # Recupera email già presenti in leads
    email_nel_csv = df["email"].str.lower().unique().tolist()
    risposta = (
        client.table("leads")
        .select("email")
        .in_("email", email_nel_csv)
        .execute()
    )
    email_esistenti = {r["email"].lower() for r in risposta.data}

    # Deduplica
    mask_nuovi = ~df["email"].str.lower().isin(email_esistenti)
    df_nuovi = df[mask_nuovi].copy()
    n_duplicati = int((~mask_nuovi).sum())

    inseriti = 0
    if not df_nuovi.empty:
        df_nuovi["campaign_id"] = campaign_id
        df_nuovi["created_at"] = datetime.now(timezone.utc).isoformat()

        righe = df_nuovi.where(pd.notna(df_nuovi), None).to_dict(orient="records")
        client.table("leads").insert(righe).execute()
        inseriti = len(righe)

    # Registra evento in activities
    client.table("activities").insert({
        "tipo": "leads_added",
        "descrizione": f"Importazione CSV '{percorso.name}': {inseriti} inseriti, {n_duplicati} duplicati saltati.",
        "payload": {"inseriti": inseriti, "duplicati": n_duplicati, "file": percorso.name},
        "campaign_id": campaign_id,
        "lead_id": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }).execute()

    print(f"\n=== Riepilogo importazione CSV ===")
    print(f"  File            : {percorso.name}")
    print(f"  Campaign ID     : {campaign_id}")
    print(f"  Lead inseriti   : {inseriti}")
    print(f"  Duplicati saltati: {n_duplicati}")
    print(f"==================================\n")

    return {"inseriti": inseriti, "duplicati": n_duplicati}


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python agent/ingestion.py <percorso_csv> <campaign_id>")
        sys.exit(1)

    percorso_csv = sys.argv[1]
    campaign_id = sys.argv[2]
    carica_csv(percorso_csv, campaign_id)
