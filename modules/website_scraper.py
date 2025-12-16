import logging
from bs4 import BeautifulSoup
from .driver_utils import get_driver

logger = logging.getLogger(__name__)

def scrape_website(url: str) -> dict:
    """
    Visits a URL and extracts content for analysis.
    """
    result = {
        "url": url,
        "title": None,
        "meta_description": None,
        "h1s": [],
        "body_text": None,
        "success": False
    }
    
    if not url:
        return result
        
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url
        
    driver = get_driver()
    try:
        logger.info(f"Visiting {url}")
        driver.get(url)
        
        result["title"] = driver.title
        
        # Get source and parse with BS4 for easier extraction
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        # Meta Description
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if meta_desc:
            result["meta_description"] = meta_desc.get("content")
            
        # Scroll to bottom to trigger lazy loading (footers, etc)
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        import time
        time.sleep(5) # Wait for load (Increased for reliability)
        
        # Re-parse soup after scroll/render
        soup = BeautifulSoup(driver.page_source, 'html.parser')
            
        # H1s
        result["h1s"] = [h1.get_text(strip=True) for h1 in soup.find_all("h1")]

        # --- EXTRACT LINKS BEFORE CLEANING SOUP ---
        # (Socials are often in nav/footer)
        
        # Social Links Extraction
        social_domains = {
            "facebook.com", "twitter.com", "x.com", "linkedin.com", 
            "instagram.com", "pinterest.com", "youtube.com", "tiktok.com"
        }
        # Strings that indicate a non-profile link
        social_noise = [
            "/p/", "/share", "/sharer", "/intent", "/stories/", "/reel/", 
            "about:blank", "javascript:void", "/home.php"
        ]
        
        found_socials = []
        # Email Extraction
        import re
        found_emails = set()
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'

        # Helper to extract emails/socials from a soup
        def extract_from_soup(soup_obj):
            s_socials = []
            s_emails = set()
            
            # Links
            a_tags = soup_obj.find_all("a", href=True)
            for l in a_tags:
                lh = l['href'].strip()
                ll = lh.lower()
                
                # Socials
                if any(d in ll for d in social_domains):
                    logger.info(f"Checking Social Link Candidate: {lh}") # DEBUG
                    if not any(n in ll for n in social_noise):
                         # Extra check: valid profile usually has path depth 1 (e.g. /username) or 2
                         # But let's just accept it if it passed the noise filter for now
                        if lh not in s_socials:
                            s_socials.append(lh)
                    else:
                        logger.info(f"Filtered as Noise: {lh}")

                
                # Mailto
                if ll.startswith("mailto:"):
                    ce = ll.replace("mailto:", "").split("?")[0].strip()
                    if re.match(email_pattern, ce):
                        s_emails.add(ce)

            # --- Check specific aria-labels or titles for social icons ---
            # e.g. <a aria-label="Instagram">
            for l in a_tags:
                label = (l.get('aria-label') or l.get('title') or "").lower()
                lh = l['href'].strip()
                if "instagram" in label or "facebook" in label or "linkedin" in label:
                     if lh not in s_socials:
                         # Ensure it's not a share link
                         if not any(n in lh.lower() for n in social_noise):
                             s_socials.append(lh)
                             logger.info(f"Found Social via Aria/Title: {lh}")
            
            # Text Emails

            t_content = soup_obj.get_text(separator=' ')
            t_emails = re.findall(email_pattern, t_content)
            for te in t_emails:
                 # heuristic to filter filenames
                 if te.lower() not in [x.lower() for x in s_emails]:
                     s_emails.add(te)
            
            return s_socials, s_emails

        # 1. Scrape Home (Full Soup)
        home_socials, home_emails = extract_from_soup(soup)
        found_socials.extend(home_socials)
        found_emails.update(home_emails)

        # --- REGEX FALLBACK (Raw Source) ---
        # Sometimes links are in JS/Script tags or data attributes not caught by soup.find("a")
        # especially for Squarespace/Wix social widgets.
        raw_html = driver.page_source
        
        # Instagram Profile Pattern (excluding posts/reels/etc)
        # Matches: instagram.com/username but not instagram.com/p/ or /share/
        ig_pattern = r'instagram\.com/(?!p/|reel/|stories/|share/)([a-zA-Z0-9_.]+)'
        ig_matches = re.finditer(ig_pattern, raw_html)
        for m in ig_matches:
            handle = m.group(1)
            if handle and "snowdrop" in handle.lower(): # Basic validation to avoid generic handles
                 full_link = f"https://www.instagram.com/{handle}"
                 if full_link not in found_socials:
                     found_socials.append(full_link)
                     logger.info(f"Found IG via Regex: {full_link}")

        # Facebook Pattern
        fb_pattern = r'facebook\.com/([a-zA-Z0-9_.]+)'
        fb_matches = re.finditer(fb_pattern, raw_html)
        for m in fb_matches:
            handle = m.group(1)
            # Filter FB specific noise
            if handle.lower() not in ["tr", "dialog", "sharer", "home.php"]:
                if "snowdrop" in handle.lower(): # Basic validation
                    full_link = f"https://www.facebook.com/{handle}"
                    if full_link not in found_socials:
                        found_socials.append(full_link)
                        logger.info(f"Found FB via Regex: {full_link}")

        # 2. Check for Contact/About/Connect pages
        internal_candidates = []
        domain_base = url.split("://")[-1].split("/")[0]
        
        # Keywords for interest tables
        interest_keywords = ["contact", "about", "connect", "inquire", "touch", "hello"]

        for link in soup.find_all("a", href=True):
            lh = link['href'].strip()
            # Also check if it's an icon-only link with aria-label targeting social
            # (Sometimes these are internal links too? Unlikely, but let's check internals first)
            
            # Internal Page Discovery
            if any(k in lh.lower() for k in interest_keywords):
                if lh.startswith("/") or domain_base in lh:
                    if lh.startswith("/"):
                        full_url = url.rstrip("/") + lh
                    elif lh.startswith("http"):
                        full_url = lh
                    else:
                        full_url = url.rstrip("/") + "/" + lh
                    
                    if full_url not in internal_candidates and full_url != url:
                        internal_candidates.append(full_url)

        # Visit Internal
        if internal_candidates:
            target_page = internal_candidates[0]
            logger.info(f"Visiting Internal Page: {target_page}")
            try:
                driver.get(target_page)
                sub_soup = BeautifulSoup(driver.page_source, 'html.parser')
                sub_socials, sub_emails = extract_from_soup(sub_soup)
                for s in sub_socials:
                    if s not in found_socials:
                        found_socials.append(s)
                found_emails.update(sub_emails)
            except Exception as e:
                logger.warning(f"Failed to visit internal page {target_page}: {e}")

        result["social_links"] = list(set(found_socials))
        result["emails"] = list(found_emails)

        # --- CLEAN SOUP FOR BODY TEXT ---
        # Body Text (Cleaned)
        # Get text, strip whitespace, remove script/style
        for script in soup(["script", "style", "nav", "footer"]):
            script.decompose()
            
        text = soup.get_text(separator=' ')
        # Clean up multiple spaces
        import re
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Simple Address/Location Extraction Heuristic
        # Look for "City, State" patterns or "PO Box", etc.
        # This is basic; a full address parser is complex.
        # Format: City, State (2 chars)
        location_match = re.search(r'\b([A-Z][a-zA-Z\s]+, \s*[A-Z]{2})\b', text)
        if location_match:
             result["detected_location"] = location_match.group(1)
        
        # Limit text length to avoid token limits later (e.g. 5000 chars)
        result["body_text"] = text[:5000]




        result["success"] = True
        
    except Exception as e:
        logger.error(f"Error scraping website {url}: {e}")
    finally:
        driver.quit()
        
    return result
