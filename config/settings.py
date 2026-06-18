import os
import sys
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Aggiunge la root del progetto al path così `db.client` è sempre trovabile
# indipendentemente da dove viene eseguito lo script
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")


@dataclass
class Settings:
    # Identità agente
    tuo_nome: str = "Giacomo Buffa"
    tua_azienda: str = "Orama Energy & Projects"
    tua_email: str = "g.buffa@oramaenergy.it"

    # Link prenotazione
    calendly_link: str = "https://calendly.com"

    # Filtri geografici e aziendali
    raggio_km: float = 50.0
    min_dipendenti: int = 10
    min_fatturato: float = 500_000.0

    # Soglie di scoring lead (A = caldo, B = tiepido)
    soglia_a: float = 0.75
    soglia_b: float = 0.50
    min_confidenza: float = 0.60

    # Soglie per classificare PMI vs azienda strutturata (usate nell'email writer)
    soglia_pmi_dipendenti: int = 20
    soglia_pmi_fatturato: float = 2_000_000.0

    # Gestione follow-up e sequenze
    tentativi_max: int = 5
    stale_days: int = 30
    urgency_window: int = 7  # giorni entro cui considerare un lead urgente

    @classmethod
    def from_env(cls) -> "Settings":
        """Costruisce Settings leggendo le variabili d'ambiente."""
        return cls(
            tuo_nome=os.environ.get("TUO_NOME", cls.tuo_nome),
            tua_azienda=os.environ.get("TUA_AZIENDA", cls.tua_azienda),
            tua_email=os.environ.get("TUA_EMAIL", cls.tua_email),
            calendly_link=os.environ.get("CALENDLY_LINK", cls.calendly_link),
            raggio_km=float(os.environ.get("RAGGIO_KM", cls.raggio_km)),
            min_dipendenti=int(os.environ.get("MIN_DIPENDENTI", cls.min_dipendenti)),
            min_fatturato=float(os.environ.get("MIN_FATTURATO", cls.min_fatturato)),
            soglia_a=float(os.environ.get("SOGLIA_A", cls.soglia_a)),
            soglia_b=float(os.environ.get("SOGLIA_B", cls.soglia_b)),
            min_confidenza=float(os.environ.get("MIN_CONFIDENZA", cls.min_confidenza)),
            tentativi_max=int(os.environ.get("TENTATIVI_MAX", cls.tentativi_max)),
            stale_days=int(os.environ.get("STALE_DAYS", cls.stale_days)),
            urgency_window=int(os.environ.get("URGENCY_WINDOW", cls.urgency_window)),
            soglia_pmi_dipendenti=int(os.environ.get("SOGLIA_PMI_DIPENDENTI", cls.soglia_pmi_dipendenti)),
            soglia_pmi_fatturato=float(os.environ.get("SOGLIA_PMI_FATTURATO", cls.soglia_pmi_fatturato)),
        )

    @classmethod
    def from_supabase(cls, base: "Settings | None" = None) -> "Settings":
        """
        Sovrascrive i valori di `base` (o i default) con quelli presenti
        nella tabella `settings` di Supabase (colonne: key, value).
        """
        from db.client import get_supabase_client

        if base is None:
            base = cls.from_env()

        try:
            client = get_supabase_client()
            rows = client.table("settings").select("chiave, valore").execute().data
        except Exception as e:
            print(f"[Settings] Impossibile leggere da Supabase, uso valori locali: {e}")
            return base

        overrides: dict[str, str] = {row["chiave"]: row["valore"] for row in rows}

        def get(key: str, default):
            return overrides.get(key, default)

        return cls(
            tuo_nome=get("tuo_nome", base.tuo_nome),
            tua_azienda=get("tua_azienda", base.tua_azienda),
            tua_email=get("tua_email", base.tua_email),
            calendly_link=get("calendly_link", base.calendly_link),
            raggio_km=float(get("raggio_km", base.raggio_km)),
            min_dipendenti=int(get("min_dipendenti", base.min_dipendenti)),
            min_fatturato=float(get("min_fatturato", base.min_fatturato)),
            soglia_a=float(get("soglia_a", base.soglia_a)),
            soglia_b=float(get("soglia_b", base.soglia_b)),
            min_confidenza=float(get("min_confidenza", base.min_confidenza)),
            tentativi_max=int(get("tentativi_max", base.tentativi_max)),
            stale_days=int(get("stale_days", base.stale_days)),
            urgency_window=int(get("urgency_window", base.urgency_window)),
            soglia_pmi_dipendenti=int(get("soglia_pmi_dipendenti", base.soglia_pmi_dipendenti)),
            soglia_pmi_fatturato=float(get("soglia_pmi_fatturato", base.soglia_pmi_fatturato)),
        )

    @classmethod
    def load(cls) -> "Settings":
        """Entry point principale: .env → override Supabase."""
        return cls.from_supabase(base=cls.from_env())


# Istanza singleton usabile nel resto del progetto
settings = Settings.load()


if __name__ == "__main__":
    s = Settings.load()
    print("\n=== Settings caricati ===")
    print(f"  tuo_nome        : {s.tuo_nome}")
    print(f"  tua_azienda     : {s.tua_azienda}")
    print(f"  tua_email       : {s.tua_email}")
    print(f"  calendly_link   : {s.calendly_link}")
    print(f"  raggio_km       : {s.raggio_km}")
    print(f"  min_dipendenti  : {s.min_dipendenti}")
    print(f"  min_fatturato   : {s.min_fatturato}")
    print(f"  soglia_a        : {s.soglia_a}")
    print(f"  soglia_b        : {s.soglia_b}")
    print(f"  min_confidenza  : {s.min_confidenza}")
    print(f"  tentativi_max   : {s.tentativi_max}")
    print(f"  stale_days      : {s.stale_days}")
    print(f"  urgency_window  : {s.urgency_window}")
    print("========================\n")
