import logging
import subprocess
import json
import os
import shutil

logger = logging.getLogger(__name__)

def scrape_google_reviews(business_name: str, location: str = "") -> dict:
    """
    Wraps the Node.js google-maps-scraper.
    1. Runs the node script with the query.
    2. Reads the output JSON.
    3. Formats it for the context builder.
    """
    
    query = f"{business_name} {location}".strip()
    logger.info(f"Invoking Node.js Maps Scraper for: {query}")
    
    # Path to the node script
    # We copied `google-maps-scraper` to `modules/maps_scraper`
    base_dir = os.path.dirname(os.path.abspath(__file__))
    scraper_dir = os.path.join(base_dir, "maps_scraper")
    script_path = os.path.join(scraper_dir, "scraper.js")
    
    # Output file is hardcoded in scraper.js as 'results.json' in CWD
    # We should run the subprocess inside the scraper_dir to manage dependencies and output
    
    try:
        # NPM Install if needed (checking if node_modules exists)
        if not os.path.exists(os.path.join(scraper_dir, "node_modules")):
            logger.info("Installing Node dependencies...")
            subprocess.run(["npm", "install"], cwd=scraper_dir, check=True, capture_output=True)
            
        # Run Scraper
        # node scraper.js "Query"
        logger.info("Running scraper...")
        try:
            result = subprocess.run(
                ["node", "scraper.js", query], 
                cwd=scraper_dir, 
                capture_output=True, 
                text=True,
                timeout=60
            )
        except subprocess.TimeoutExpired:
            logger.error("Node scraper timed out (60s). Killing process.")
            return {"success": False, "error": "Scraper timed out"}
        
        if result.returncode != 0:
            logger.error(f"Node scraper failed: {result.stderr}")
            return {"success": False, "error": "Scraper script failed"}
            
        # Read Output
        output_file = os.path.join(scraper_dir, "results.json")
        if os.path.exists(output_file):
            with open(output_file, "r") as f:
                data = json.load(f)
                
            # The scraper returns a list of businesses. We take the first one (top result).
            if data and isinstance(data, list) and len(data) > 0:
                top_result = data[0]
                
                # Transform to our internal format
                return {
                    "success": True,
                    "source_url": top_result.get("url"),
                    "address": top_result.get("address"),
                    "total_reviews": int(top_result.get("reviewCount", 0)) if top_result.get("reviewCount") else 0,
                    "average_rating": float(top_result.get("rating", 0.0)) if top_result.get("rating") else 0.0,
                    "phone": top_result.get("phone"),
                    "attributes": top_result.get("attributes", []),
                    "socials": top_result.get("socials", []),

                    "positive_themes": top_result.get("reviewCategories", []), # Using categories as proxy for themes
                    "reviews_text": [r.get("text") for r in top_result.get("reviews", []) if r.get("text")],
                    "complaints": [], # advanced analysis needed
                    "opportunity_gaps": [] # advanced analysis needed
                }
            else:
                logger.warning("Scraper ran but returned no results.")
                return {"success": False, "error": "No results found"}
        else:
            logger.error("results.json not found after execution.")
            return {"success": False, "error": "Output file missing"}
            
    except Exception as e:
        logger.error(f"Error during maps scraping: {e}")
        return {"success": False, "error": str(e)}
