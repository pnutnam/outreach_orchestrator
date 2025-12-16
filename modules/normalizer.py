import re
from urllib.parse import urlparse

def normalize_input(target_input: str) -> dict:
    """
    Analyzes the input string (URL or Email) and returns a normalized dictionary.
    
    Returns:
        {
            "original_input": str,
            "type": "url" | "email",
            "domain": str,
            "business_name": str (inferred from domain),
            "valid": bool
        }
    """
    result = {
        "original_input": target_input,
        "type": None,
        "domain": None,
        "business_name": None,
        "valid": False
    }

    if not target_input:
        return result

    target_input = target_input.strip()

    # Check for Email
    email_regex = r"[^@]+@[^@]+\.[^@]+"
    if re.match(email_regex, target_input):
        result["type"] = "email"
        try:
            domain = target_input.split('@')[1]
            result["domain"] = domain
            result["valid"] = True
        except IndexError:
            result["valid"] = False
    
    # Check for URL
    else:
        # Prepend http if missing to help urlparse
        if not target_input.startswith(('http://', 'https://')):
            url_to_parse = 'http://' + target_input
        else:
            url_to_parse = target_input
            
        try:
            parsed = urlparse(url_to_parse)
            if parsed.netloc:
                result["type"] = "url"
                # Strip www.
                domain = parsed.netloc.replace('www.', '')
                result["domain"] = domain
                result["valid"] = True
            else:
                # Fallback for simple domain strings like "google.com" that might not netloc correctly without scheme if logic above failed
                 pass # Logic above handles scheme addition
        except Exception:
            pass

    if result["valid"] and result["domain"]:
        # Infer business name: remove TLD, capitalize
        # e.g. "acme-corp.com" -> "Acme Corp"
        try:
            name_part = result["domain"].rsplit('.', 1)[0]
            # Replace hyphens/underscores with spaces
            name_part = name_part.replace('-', ' ').replace('_', ' ')
            result["business_name"] = name_part.title()
        except:
            result["business_name"] = result["domain"]

    return result
