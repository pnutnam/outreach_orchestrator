import argparse
import json
import logging
import sys
import os

# Add current dir to path to find modules if running from scratch
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from modules.normalizer import normalize_input
from modules.website_scraper import scrape_website
from modules.reviews_scraper import scrape_google_reviews
from modules.linkedin_lookup import lookup_linkedin
from modules.context_builder import build_context_package
from modules.gemini_client import consult_gem

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("Orchestrator")

def main():
    parser = argparse.ArgumentParser(description="Outreach Orchestration Engine")
    parser.add_argument("--url", help="Target URL")
    parser.add_argument("--email", help="Target Email")
    parser.add_argument("--batch", help="Path to CSV file for batch processing")
    parser.add_argument("--scan", action="store_true", help="Run scraping phase only")
    parser.add_argument("--generate", action="store_true", help="Run generation phase only (requires scan data)")
    args = parser.parse_args()

    # --- BATCH MODE ---
    if args.batch:
        if args.scan:
            batch_scan(args.batch)
        elif args.generate:
            batch_generate(args.batch)
        else:
            # Default to full pipeline if no specific flag (or maybe warn?)
            # For now, let's default to full pipeline to preserve old behavior,
            # Or better, tell user to specify.
            logger.info("Running FULL PIPELINE (Scan + Generate). Use --scan or --generate for individual phases.")
            process_batch(args.batch) 
        return
    # ------------------

    target_input = args.url or args.email
    if not target_input:
        logger.error("Please provide --url or --email")
        sys.exit(1)

    # 1. Normalize
    logger.info(f"Normalizing input: {target_input}")
    normalization = normalize_input(target_input)
    if not normalization["valid"]:
        logger.error("Invalid input.")
        sys.exit(1)
    
    business_name = normalization.get("business_name")
    domain = normalization.get("domain")
    logger.info(f"Target Identified: {business_name} ({domain})")

    # 2. Website Scrape
    logger.info("Step 2: Website Scrape")
    website_url = normalization["original_input"] if normalization["type"] == "url" else f"http://{domain}"
    website_data = scrape_website(website_url)
    
    # 4. LinkedIn Lookup (Moved before Maps to provide location hint)
    logger.info("Step 3: LinkedIn Lookup")
    linkedin_data = lookup_linkedin(business_name)

    # 3. Google Reviews (Now Step 4)
    logger.info("Step 4: Google Reviews Scrape")
    
    # REFINEMENT: Use Website Title to improve Business Name for search
    refined_name = business_name
    if website_data.get("title"):
        title = website_data["title"]
        # Common separators
        if website_data.get("title"):
            title = website_data["title"]
            # Common separators
            for sep in ['|', '-', ':', '•']:
                if sep in title:
                    title = title.split(sep)[0]
            title = title.strip()
            # Tighten length check and ignore error titles
            bad_titles = ["403", "404", "forbidden", "access denied", "redirecting", "not found"]
        if title and len(title) < 35 and not any(b in title.lower() for b in bad_titles): 
            refined_name = title
            logger.info(f"Refined Business Name from Website: {refined_name}")
        else:
            logger.info(f"Website Title rejected ('{title}'), using normalized name: {refined_name}")

    # Use address found on website OR LinkedIn to refine search (Priority: LinkedIn > Website)
    location_hint = "" 
    if linkedin_data.get("location"):
        location_hint = linkedin_data.get("location")
        logger.info(f"Using LinkedIn Location Hint: {location_hint}")
    elif website_data.get("detected_location"):
         location_hint = website_data.get("detected_location")

    reviews_data = scrape_google_reviews(refined_name, location_hint)

    
    # 5. Build Context
    logger.info("Step 5: Building Context Package")
    context = build_context_package(
        business_summary=normalization,
        website_data=website_data,
        reviews_data=reviews_data,
        linkedin_data=linkedin_data
    )
    
    # 6. Consult Gem
    logger.info("Step 6: Consulting Gemini Gem")
    gem_result = consult_gem(context)
    
    # Output
    print("\n" + "="*50)
    print("FINAL CONTEXT PACKAGE")
    print("="*50)
    print(json.dumps(context, indent=2))
    
    print("\n" + "="*50)
    print("GEMINI PROMPT (Copy this to your Gem)")
    print("="*50)
    print(gem_result["prompt_to_run"])
    
    # Save to file
    output_filename = f"{business_name.replace(' ', '_')}_intelligence.json"
    with open(output_filename, "w") as f:
        json.dump({
            "context": context,
            "gem_instruction": gem_result
        }, f, indent=2)
    logger.info(f"Saved intelligence to {output_filename}")

def batch_scan(csv_path):
    """Phase 1: Scrape and save JSON intelligence."""
    import pandas as pd
    
    if not os.path.exists(csv_path):
        logger.error(f"File not found: {csv_path}")
        return

    logger.info(f"🕵️ STARTING SCAN PHASE: {csv_path}")
    df = pd.read_csv(csv_path)
    # Standardize
    df.columns = [c.strip().lower() for c in df.columns]
    
    for index, row in df.iterrows():
        try:
            target = row.get('website') or row.get('email')
            if not target: continue
            
            logger.info(f"\n--- Row {index+1}: {target} ---")
            
            # 1. Normalize
            norm = normalize_input(target)
            if not norm["valid"]:
                logger.warning("Invalid input")
                continue
            
            # Filename check - skip if exists?
            safe_name = norm.get("business_name", "unknown").replace(" ", "_")
            out_file = os.path.abspath(f"{safe_name}_intelligence.json")
            
            # Simple check to skip if already done
            if os.path.exists(out_file):
               logger.info(f"Skipping {target}, intelligence found: {out_file}")
               print(f"⏩ Skipped (Exists): file://{out_file}")
               continue
            
            # 2. Scrape Website
            logger.info("Scraping Website...")
            web_data = scrape_website(norm["original_input"] if norm["type"] == "url" else f"http://{norm['domain']}")
            
            # 3. LinkedIn
            logger.info("Looking up LinkedIn...")
            li_data = lookup_linkedin(norm["business_name"])
            
            # 4. Maps
            logger.info("Scraping Maps...")
            loc = li_data.get("location") or web_data.get("detected_location") or ""
            # Refine name
            refined_name = norm["business_name"]
            if web_data.get("title"):
                 # Basic title cleaning
                 t = web_data["title"].split('|')[0].strip()
                 # Ignore error titles
                 bad_titles = ["403", "404", "forbidden", "access denied", "redirecting", "not found"]
                 if t and len(t) < 35 and not any(b in t.lower() for b in bad_titles): 
                     refined_name = t
            
            maps_data = scrape_google_reviews(refined_name, loc)
            
            # 5. Build Context
            context = build_context_package(norm, web_data, maps_data, li_data)
            
            # Save
            with open(out_file, "w") as f:
                json.dump({"context": context}, f, indent=2)
                
            # LOG FOR USER CLICK
            print(f"✅ Intelligence Saved: file://{out_file}")
            
        except Exception as e:
            logger.error(f"Error scanning {target}: {e}")

def batch_generate(csv_path):
    """Phase 2: Generate emails from stored JSONs."""
    import pandas as pd
    
    logger.info(f"✍️ STARTING GENERATION PHASE: {csv_path}")
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lower() for c in df.columns]
    
    results = []
    
    # Initialize CSV with Headers immediately
    _save_output([], "first_thirty_first_email.csv")
    
    for index, row in df.iterrows():
        target = row.get('website') or row.get('email')
        if not target: continue
        
        # We need the business name to find the file
        # Rerun normalize just to get the name key
        norm = normalize_input(target)
        if not norm["valid"]: continue
        
        safe_name = norm.get("business_name").replace(" ", "_")
        json_file = f"{safe_name}_intelligence.json"
        
        row_result = {
            "Input": target,
            "Contact Email": row.get('email', ''), # Added Contact Email
            "Business Name": norm.get("business_name"),
            "Status": "Pending",
             "Pain Point": "N/A"
        }
        
        if not os.path.exists(json_file):
            logger.warning(f"No intelligence file for {target} ({json_file}). Run --scan first.")
            row_result["Status"] = "Missing Intelligence"
        else:
            try:
                with open(json_file, "r") as f:
                    data = json.load(f)
                    
                context = data.get("context")
                if not context:
                   row_result["Status"] = "Invalid JSON"
                else:
                    logger.info(f"Generating for {safe_name}...")
                    
                    # CALL GEMINI
                    gem_result = consult_gem(context)
                    
                    if gem_result.get("error") == "All Keys Rate Limited":
                         logger.critical("🛑 CRITICAL: All API Keys are Rate Limited. Aborting Batch to prevent quota abuse.")
                         sys.exit(1)

                    if gem_result["status"] == "success":
                        row_result["Status"] = "Success"
                        gdata = gem_result.get("data", {})
                        row_result["Pain Point"] = gdata.get("opportunity_diagnosis", "N/A")
                        
                        emails = gdata.get("emails", [])
                        for i, email_obj in enumerate(emails):
                            if i >= 3: break # Only 3 options
                            label = ["A", "B", "C"][i]
                            row_result[f"Angle {label}"] = email_obj.get("angle", "N/A")
                            row_result[f"Subject {label}"] = email_obj.get("subject", "N/A")
                            row_result[f"Email {label}"] = email_obj.get("body", "N/A")
                            
                        # Save instruction
                        data["gem_instruction"] = gem_result
                        with open(json_file, "w") as f:
                            json.dump(data, f, indent=2)
                            
                    else:
                         row_result["Status"] = f"Gen Failed: {gem_result.get('error')}"

            except Exception as e:
                logger.error(f"Error generating {target}: {e}")
                row_result["Status"] = f"Error: {e}"
        
        results.append(row_result)
        
        # Incremental Save
        _save_output(results, "first_thirty_first_email.csv")
        
def _save_output(results, filename):
    import pandas as pd
    cols = ["Input", "Contact Email", "Business Name", "Status", "Pain Point"]
    for label in ["A", "B", "C"]:
        cols.extend([f"Angle {label}", f"Subject {label}", f"Email {label}"])
        
    df = pd.DataFrame(results)
    for c in cols:
        if c not in df.columns: df[c] = "N/A"
    
    df[cols].to_csv(filename, index=False)


if __name__ == "__main__":
    main()
