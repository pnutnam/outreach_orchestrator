import logging
import time
import re
from typing import Dict, Optional, List
from urllib.parse import urlparse
from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .driver_utils import get_driver

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class LinkedInScraperV2:
    def __init__(self):
        pass
        
    def _get_driver(self):
        return get_driver()

    def scrape_company_page(self, url: str) -> Dict[str, str]:
        """
        Scrapes a public LinkedIn company page for details (Optimized V2).
        Returns a dictionary with extracted info.
        """
        logger.info(f"Scraping LinkedIn page: {url}")
        driver = None
        data = {
            "employee_count": None,
            "follower_count": None,
            "about": None,
            "location": None,
            "url": url,
            "industry": None,
            "type": None,
            "specialties": None,
            "website": None,
            "company_size": None,
            "headquarters": None,
            "founded": None,
            "locations": [],
            "employees": []
        }

        try:
            driver = self._get_driver()
            
            # Google Referral Trick: Go to Google first
            # Reduced wait from 2s to 1s
            logger.info("Navigating to Google first to simulate referral...")
            driver.get("https://www.google.com")
            time.sleep(1)
            
            # Now go to LinkedIn
            driver.get(url)
            
            # Wait for potential content load
            # Reduced from 5s to 2s, relying on explicit waits/checks later
            time.sleep(2)
            
            # Check for Authwall (redirect to login)
            current_url = driver.current_url
            if "linkedin.com/authwall" in current_url:
                logger.warning("Hit LinkedIn Authwall. Google referral trick failed.")
                return data

            # Popup Dismissal Logic
            try:
                # Look for common modal close buttons
                close_buttons = driver.find_elements(By.CSS_SELECTOR, "button.modal__dismiss, button[aria-label='Dismiss'], button.contextual-sign-in-modal__modal-dismiss-btn")
                for btn in close_buttons:
                    if btn.is_displayed():
                        logger.info("Dismissing login popup...")
                        driver.execute_script("arguments[0].click();", btn)
                        # Reduced wait
                        time.sleep(0.5)
            except Exception as e:
                logger.warning(f"Error dismissing popup: {e}")

            
            # Scroll down to load ALL content (especially company details section)
            logger.info("Scrolling to load company details...")
            # Faster scrolling
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/3);")
            time.sleep(1)
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(1)
            
            # Refresh soup after scrolling to get all loaded content
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            # Extract Employee Count
            # Strategy 1: Look for "employees" text
            employee_text = soup.find(string=re.compile(r"[\d,]+\+?\s+employees", re.IGNORECASE))
            if employee_text:
                data["employee_count"] = employee_text.strip()
            
            # Strategy 2: Look for "View all X employees" link
            if not data["employee_count"]:
                view_all_link = soup.find('a', string=re.compile(r"View all.*employees", re.IGNORECASE))
                if view_all_link:
                    data["employee_count"] = view_all_link.get_text(strip=True).replace("View all", "").replace("employees", "").strip()

            # Extract Follower Count
            follower_text = soup.find(string=re.compile(r"[\d,]+\s+followers", re.IGNORECASE))
            if follower_text:
                data["follower_count"] = follower_text.strip()

            # Extract About
            about_section = soup.find('h2', string=re.compile(r"About", re.IGNORECASE))
            if about_section:
                parent = about_section.find_parent()
                if parent:
                    about_text = parent.get_text(separator="\n", strip=True)
                    about_text = about_text.replace("About us", "").replace("About", "").strip()
                    data["about"] = about_text[:500] + "..." if len(about_text) > 500 else about_text
            
            # Fallback About
            if not data["about"]:
                meta_desc = soup.find('meta', property='og:description')
                if meta_desc:
                    data["about"] = meta_desc.get('content')

            # Extract Location (Headquarters)
            hq_text = soup.find(string=re.compile(r"Headquarters", re.IGNORECASE))
            if hq_text:
                parent = hq_text.find_parent()
                if parent:
                    data["location"] = parent.get_text(strip=True).replace("Headquarters", "").strip()

            # Extract Additional Details (Industry, Type, Specialties, Website, Founded)
            def get_detail(label_pattern):
                all_dts = soup.find_all('dt')
                for dt in all_dts:
                    dt_text = dt.get_text(strip=True)
                    if re.match(label_pattern, dt_text, re.IGNORECASE):
                        dd = dt.find_next_sibling('dd')
                        if dd:
                            if 'Website' in label_pattern:
                                link = dd.find('a', href=True)
                                if link:
                                    return link.get_text(strip=True)
                            return dd.get_text(strip=True)
                
                label = soup.find(string=re.compile(label_pattern, re.IGNORECASE))
                if label:
                    parent = label.find_parent()
                    if parent:
                        next_sibling = parent.find_next_sibling()
                        if next_sibling:
                            return next_sibling.get_text(strip=True)
                return None

            data["industry"] = get_detail(r"^Industry$")
            data["type"] = get_detail(r"^Type$")
            data["specialties"] = get_detail(r"^Specialties$")
            data["website"] = get_detail(r"^Website$")
            data["founded"] = get_detail(r"^Founded$")
            
            if not data["industry"]:
                subtitle = soup.find('div', class_=re.compile(r"top-card.*subtitle", re.IGNORECASE))
                if not subtitle:
                    subtitle = soup.find('h2', class_=re.compile(r"top-card-layout__headline"))
                if subtitle:
                    parts = [p.strip() for p in subtitle.get_text(separator="|").split("|") if p.strip()]
                    if parts and "," not in parts[0]:
                         data["industry"] = parts[0]

            if not data["employee_count"]:
                data["employee_count"] = get_detail(r"^Company size$")
            
            company_size = get_detail(r"^Company size$")
            if company_size:
                data["company_size"] = company_size
            
            if not data["location"]:
                data["location"] = get_detail(r"^Headquarters$")
            
            if data["location"]:
                data["headquarters"] = data["location"]
            
            # Extract Locations
            location_items = soup.find_all('div', class_=re.compile(r'location'))
            for item in location_items:
                text = item.get_text(strip=True)
                if re.search(r'[A-Za-z\s]+,\s*[A-Za-z\s]+', text):
                    if text not in data["locations"] and len(text) < 100:
                        data["locations"].append(text)
            
            if len(data["locations"]) == 0:
                all_text = soup.get_text()
                location_patterns = [
                    r'([A-Z][a-z\s]+,\s*[A-Z][a-z\s]+,\s*US)',
                    r'([A-Z][a-z\s]+,\s*[A-Z]{2},\s*US)',
                    r'([A-Z][a-z\s]+,\s*[A-Z][a-z\s]+)'
                ]
                for pattern in location_patterns:
                    matches = re.findall(pattern, all_text)
                    for match in matches:
                        if match not in data["locations"] and 'Primary' not in match:
                            data["locations"].append(match)
                            if len(data["locations"]) >= 5:
                                break
                    if data["locations"]:
                        break
            
            # Extract Employees
            employee_headings = soup.find_all('h3', class_=re.compile(r'base-main-card__title'))
            seen_names = set()
            for h3 in employee_headings:
                if len(data["employees"]) >= 10:
                    break
                
                name = h3.get_text(strip=True)
                if not name or name in seen_names:
                    continue
                if len(name) < 3 or any(keyword in name.lower() for keyword in ['view', 'all', 'discover', 'see']):
                    continue
               
                seen_names.add(name)
                
                h4 = h3.find_next_sibling('h4')
                title = "Unknown"
                if h4:
                    title_text = h4.get_text(strip=True)
                    if ' at ' in title_text:
                        title = title_text.split(' at ')[0].strip()
                    else:
                        title = title_text
                
                parent_link = h3.find_parent('a', href=re.compile(r'/in/'))
                profile_url = None
                if parent_link:
                    href = parent_link.get('href', '')
                    if href.startswith('http'):
                        profile_url = href.split('?')[0]
                    else:
                        profile_url = "https://www.linkedin.com" + href.split('?')[0]
                
                if profile_url:
                    employee_data = {
                        "name": name,
                        "title": title,
                        "profile_url": profile_url
                    }
                    data["employees"].append(employee_data)
            
        except Exception as e:
            logger.error(f"Error scraping LinkedIn page {url}: {e}")
        finally:
            if driver:
                driver.quit()
        
        return data
