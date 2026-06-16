import os
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

_client: Client | None = None


def get_supabase_client() -> Client:
    global _client
    if _client is None:
        url = os.environ.get("SUPABASE_URL")
        key = os.environ.get("SUPABASE_KEY")
        if not url or not key:
            raise ValueError("SUPABASE_URL e SUPABASE_KEY devono essere definite nel file .env")
        _client = create_client(url, key)
    return _client


def test_connessione() -> bool:
    try:
        client = get_supabase_client()
        response = client.table("settings").select("*").limit(1).execute()
        print(f"Connessione riuscita. Righe restituite: {len(response.data)}")
        return True
    except Exception as e:
        print(f"Errore di connessione: {e}")
        return False


if __name__ == "__main__":
    test_connessione()
