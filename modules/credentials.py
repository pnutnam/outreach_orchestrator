import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

def get_credential_pool():
    """
    Constructs the credential pool from environment variables.
    Looks for pattern GEMINI_KEY_{N}, SEARCH_KEY_{N}, etc.
    """
    pool = []
    i = 1
    while True:
        # Check for existence of a key set
        g_key = os.getenv(f"GEMINI_KEY_{i}")
        s_key = os.getenv(f"SEARCH_KEY_{i}")
        cx = os.getenv(f"SEARCH_CX_{i}")
        gem_url = os.getenv(f"GEM_URL_{i}")

        # If we have at least a Gemini Key, we consider it a valid entry
        if g_key:
            pool.append({
                "name": f"Account_{i}",
                "gemini_key": g_key,
                "search_key": s_key,
                "cx": cx,
                "gem_url": gem_url
            })
            i += 1
        else:
            # unique case: if we have gaps (e.g. 1 and 3 but not 2), this loop stops.
            # Assuming sequential numbering for simplicity.
            # If 1 is missing, we check if there are ANY keys, if not, maybe basic fallback?
            if i == 1:
                 # Check for un-numbered legacy or single-user vars
                 single_g = os.getenv("GEMINI_KEY")
                 single_s = os.getenv("SEARCH_KEY")
                 single_cx = os.getenv("SEARCH_CX")
                 single_url = os.getenv("GEM_URL")
                 
                 if single_g:
                     pool.append({
                        "name": "Default",
                        "gemini_key": single_g,
                        "search_key": single_s,
                        "cx": single_cx,
                        "gem_url": single_url
                    })
            break
            
    return pool

def get_gemini_pool():
    pool = get_credential_pool()
    return [c for c in pool if c.get("gemini_key")]

def get_search_pool():
    pool = get_credential_pool()
    return [{"key": c["search_key"], "cx": c["cx"]} for c in pool if c.get("search_key") and c.get("cx")]
