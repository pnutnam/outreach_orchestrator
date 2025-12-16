import logging
from .linkedin_scraper_v2 import LinkedInScraperV2

logger = logging.getLogger(__name__)

def lookup_linkedin(business_name: str) -> dict:
    """
    Uses the robust LinkedInScraperV2 to find and scrape company data.
    """
    # 1. We need a URL first. The V2 scraper expects a company page URL.
    #    We can reuse the logic from my previous attempt (DDG Search) to finding the URL,
    #    THEN pass it to V2.
    
    from .driver_utils import get_driver # ScraperV2 imports this, make sure it exists
    
    # Simple search to get URL
    # TODO: Refactor this search logic if needed, or stick to the one I wrote in step 41
    # For now, I'll inline a quick search helper or reuse the one from step 41 logic
    
    # ... Re-implementing the search part quickly here or importing it?
    # Let's import the search logic if I kept it? I overwrote the file.
    # I'll rewrite the search logic here to feed the V2 scraper.
    
    # API-based Search (Robust with Rotation)
    import requests
    import os
    from .credentials import get_search_pool
    
    search_pool = get_search_pool()
    
    linkedin_url = None
    
    # Try pool of keys
    for creds in search_pool:
        api_key = creds["key"]
        cx = creds["cx"]
        
        search_query = f"{business_name} site:linkedin.com/company"
        url = f"https://www.googleapis.com/customsearch/v1?key={api_key}&cx={cx}&q={search_query}"
        
        try:
            logger.info(f"Searching Google API for: {search_query} (Key ...{api_key[-4:]})")
            resp = requests.get(url)
            
            if resp.status_code == 429 or resp.status_code == 403:
                logger.warning(f"Search Key ...{api_key[-4:]} Limit/Error ({resp.status_code}). Rotating...")
                continue # Try next key
                
            results = resp.json()
            
            if "items" in results:
                for item in results["items"]:
                    link = item.get("link")
                    if "linkedin.com/company/" in link:
                        linkedin_url = link
                        break # Found it!
                if linkedin_url: break # Break outer loop
            else:
                logger.warning(f"No Google API results. Response: {str(results)[:100]}...")
                # If no results (but not 429), it might just be not found. 
                # Should we try next key? Probably not needed unless we suspect quota block disguised as something else.
                # But let's assume if status_code=200, key is fine.
                break 
                
        except Exception as e:
            logger.error(f"Google Search API Error: {e}")
            continue # Try next key on error
        
    if not linkedin_url:
        return {"error": "Could not find LinkedIn URL", "success": False}
        
    # Now use the V2 Scraper
    logger.info(f"Found LinkedIn URL: {linkedin_url}. specific scraping...")
    scraper = LinkedInScraperV2()
    # Note: V2 scraper creates its own driver internally using 'get_driver' from 'driver_utils'
    # capable of handling the scraping.
    
    try:
        data = scraper.scrape_company_page(linkedin_url)
        data["success"] = True
        data["source_url"] = linkedin_url
        return data

    except Exception as e:
        logger.error(f"Error executing LinkedInScraperV2: {e}")
        return {"error": str(e), "success": False}
