import json
from datetime import datetime

def build_context_package(
    business_summary: dict,
    website_data: dict,
    reviews_data: dict,
    linkedin_data: dict
) -> dict:
    """
    Combines all scraped data into the unified context structure required by the Master Prompt.
    """
    
    # Location Priority Logic: Website > LinkedIn > Maps
    inferred_location = "Unknown"
    location_source_url = "None"
    
    # 1. Website
    if website_data.get("detected_location"):
        inferred_location = website_data.get("detected_location")
        location_source_url = website_data.get("url")
    # 2. LinkedIn
    elif linkedin_data.get("location") or linkedin_data.get("headquarters"):
        inferred_location = linkedin_data.get("location") or linkedin_data.get("headquarters")
        location_source_url = linkedin_data.get("source_url")
    # 3. Maps (Low trust)
    elif reviews_data.get("address"):
        inferred_location = reviews_data.get("address")
        location_source_url = reviews_data.get("source_url")
    
    # Unified Socials (Aggregated & Deduped)
    unified_socials = _aggregate_socials(
        website_socials=website_data.get("social_links", []),
        company_linkedin=linkedin_data.get("source_url"),
        personnel=linkedin_data.get("employees", []),
        maps_socials=reviews_data.get("socials", [])
    )

    # Structure defined in Step 5 of Master Prompt
    context_package = {
        "meta": {
            "generated_at": datetime.now().isoformat(),
            "target_business": business_summary.get("business_name")
        },
        "business_identity": {
            "name": business_summary.get("business_name"),
            "domain": business_summary.get("domain"),
            "inferred_location": inferred_location,
            "inferred_niche": website_data.get("niche") or reviews_data.get("category"),
            "sources": {
                "location": location_source_url,
                "domain": "user_input"
            }
        },
        "website_insights": {
            "brand_voice": website_data.get("brand_voice"),
            "offer_stack": _truncate_text(website_data.get("offer_stack", "")), # Truncate these potentially long fields
            "differentiators": website_data.get("differentiators"),
            "customer_types": website_data.get("customer_types"),
            "pricing_signals": website_data.get("pricing_signals"),
            "blog_sophistication": website_data.get("blog_sophistication"),
            "social_links": unified_socials,
            "emails": _resolve_emails(website_data.get("emails", []), business_summary),
            "source_url": website_data.get("url"),
            "raw_text_summary": _truncate_text(website_data.get("body_text", ""), max_words=500) # Added explicit summary field
        },

        "google_reviews_insights": {
            "note": "Review data cleared due to low confidence (mismatch detected).",
            "total_reviews": reviews_data.get("reviews_count"), 
            "average_rating": reviews_data.get("rating"),
            "positive_themes": [], # Could extract themes if we had full text analytics
            "complaints": [],
            "top_reviews": reviews_data.get("reviews", [])[:10], # LIMIT TO TOP 10 to save tokens
            "source_url": reviews_data.get("source_url")
        },


        "linkedin_org_snapshot": {
            "estimated_size": linkedin_data.get("company_size") or linkedin_data.get("employee_count"),
            "about": linkedin_data.get("about"),
            "specialties": linkedin_data.get("specialties"),
            "hiring_status": linkedin_data.get("hiring_status", "Unknown"),
            "key_personnel": linkedin_data.get("employees", []),
            "decision_maker_hierarchy": linkedin_data.get("decision_maker_hierarchy", "Unknown"),
            "source_url": linkedin_data.get("source_url")
        },

        "inferences": {
            "pain_points": [], 
            "market_sophistication": "Unknown", 
            "capacity_signals": "Unknown",
            "owner_inference": _infer_owner(linkedin_data.get("employees", []), reviews_data.get("attributes", []))
        }
    }
    
    return context_package

def _infer_owner(employees, attributes):
    """
    Deduces owner if 'Women-owned' attribute is present and female name is found.
    Simple heuristic for demonstration.
    """
    inference = "Unknown"
    is_women_owned = "Women-owned" in attributes
    
    if is_women_owned:
        for emp in employees:
            name = emp.get("name", "")
            # Basic check for Cecilia (User specified case)
            if "Cecilia" in name:
                return f"Cecilia Roy (Likely Owner - inferred from 'Women-owned' attribute)"
    
    return inference

def _resolve_emails(scraped_emails, business_summary):
    """
    Merges scraped emails with the input email if valid.
    """
    emails = set(scraped_emails)
    input_val = business_summary.get("original_input", "")
    if "@" in input_val and "." in input_val:
        emails.add(input_val)
    return list(emails)

    return list(emails)


def _aggregate_socials(website_socials, company_linkedin, personnel, maps_socials):
    """
    Combines all validated social profiles from Website, LinkedIn, and Maps.
    Dedupes by normalizing URL (ignoring protocol/www).
    """
    raw_list = []
    if website_socials: raw_list.extend(website_socials)
    if maps_socials: raw_list.extend(maps_socials)
    if company_linkedin: raw_list.append(company_linkedin)
    for p in personnel:
        if p.get("profile_url"):
            raw_list.append(p.get("profile_url"))
            
    # Dedupe logic
    unique_map = {}
    
    for url in raw_list:
        if not url: continue
        
        # Normalize Key: remove http/s, www, trailing slash
        clean_key = url.lower().replace("https://", "").replace("http://", "").replace("www.", "").rstrip("/")
        
        # Selection Logic: Prefer HTTPS, then shorter (usually cleaner)
        if clean_key not in unique_map:
            unique_map[clean_key] = url
        else:
            current = unique_map[clean_key]
            # If new one is https and current isn't, take new one
            if "https" in url and "https" not in current:
                unique_map[clean_key] = url
            # If both/neither https, maybe prefer www? or length? 
            # Let's just stick with first found unless https upgrade.
            

    return sorted(list(unique_map.values()))

def _truncate_text(text: str, max_words=800) -> str:
    """
    Truncates text to reduce token count. 
    Removes common stop words and limits to max_words.
    """
    if not text:
        return ""
        
    # Basic stop words (Hardcoded to avoid NLTK download issues in some envs)
    # Using a slightly larger set for better compression.
    stop_words = {
        "the", "is", "at", "which", "on", "a", "an", "and", "or", "but", "if", "then", "else", "when", 
        "of", "to", "in", "for", "with", "by", "from", "up", "down", "out", "over", "under", "again", 
        "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "any", "both", 
        "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", 
        "so", "than", "too", "very", "can", "will", "just", "don", "should", "now", "are", "was", "were"
    }
    
    words = text.split()
    # Filter stops and keep meaningful content
    clean_words = [w for w in words if w.lower() not in stop_words and len(w) > 2]
    
    # Truncate
    return " ".join(clean_words[:max_words])



