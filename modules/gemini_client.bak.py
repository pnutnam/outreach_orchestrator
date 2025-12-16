import json
import logging
import os

logger = logging.getLogger(__name__)

def generate_gem_prompt(context_package: dict) -> str:
    """
    Constructs the prompt to send to the Gemini Gem.
    """
    context_str = json.dumps(context_package, indent=2)
    
    prompt = f"""
    ROLE: You are an expert Copywritier and Sales Strategist.
    
    TASK: Analyze the provided Business Context key insights and generate 3 highly personalized outreach emails.
    
    USE THIS GEM: https://gemini.google.com/gem/1olyB7e5v41fSxu03e_PRBzOVXeP2RseL?usp=sharing
    
    CONTEXT:
    {context_str}
    
    INSTRUCTIONS:
    1. Identify the key opportunity or pain point for this specific business.
    2. Suggest an outreach angle.
    3. Write 5 INITIAL OUTREACH emails (No follow-ups, No breakups). Options A-E:
       - Option A: Direct/Value-First (The "Helpful Resource")
       - Option B: Observational/Complimentary (The "Fan")
       - Option C: The "Short Question"
       - Option D: The "Reference/Case Study" (Social Proof)
       - Option E: The "Specific Idea" (Insight-led)


    
    OUTPUT FORMAT:
    JSON with keys: "analysis_summary", "opportunity_diagnosis", "emails" (list of objects with subject, body, angle).
    """
    return prompt



import google.generativeai as genai
from .credentials import get_gemini_pool

# Valid Gemini Keys Pool
GEMINI_KEY_POOL = get_gemini_pool()

def consult_gem(context_package: dict, api_key: str = None) -> dict:
    """
    Calls Gemini, rotating keys if Rate Limits are hit.
    """
    prompt = generate_gem_prompt(context_package)
    
    # 1. Determine Initial Key (arg > env > pool[0])
    current_key_idx = 0
    # Try to find which key matches arg/env to start there? 
    # Or just ignore env if we have a robust pool?
    # Let's prioritize the pool for rotation.
    
    # Retry Loop (across keys)
    import time
    
    # Total attempts = (keys * 2) to give each key a couple chances?
    # Let's simple cycle through the pool.
    
    for attempt in range(len(GEMINI_KEY_POOL) * 2):
        key = GEMINI_KEY_POOL[current_key_idx % len(GEMINI_KEY_POOL)]
        
        try:
            genai.configure(api_key=key)
            # Switching to 1.5 Flash Latest (Confirmed available in list_models)
            model = genai.GenerativeModel('gemini-flash-latest') 
            
            logger.info(f"Calling Gemini API (Key ...{key[-4:]})...") # Verbose
            response = model.generate_content(prompt, generation_config={"response_mime_type": "application/json"})
            
            result_json = json.loads(response.text)
            return {
                "status": "success",
                "data": result_json,
                "raw_response": response.text
            }

        except Exception as e:
            err_str = str(e)
            
            # Rotate on Rate Limit (429) OR Auth Errors (403 Leaked/Invalid)
            if any(code in err_str for code in ["429", "quota"]):
                logger.warning(f"Rate Limit on Key ...{key[-4:]}. Sleeping 60s then rotating...")
                time.sleep(60)
                current_key_idx += 1
                continue
            
            elif any(code in err_str for code in ["403", "leaked", "permission"]):
                logger.warning(f"Key ...{key[-4:]} INVALID/LEAKED. Rotating immediately...")
                current_key_idx += 1
                time.sleep(1)
                continue
            
            else:
                logger.error(f"Gemini API Error (Non-Retriable): {e}")
                print(f"DEBUG EXCEPTION: {e}") # Force print to stdout
                
    # If we fall through the loop, all keys are exhausted
    logger.error("All Gemini Keys Rate Limited.")
    return {
        "status": "prompt_generated",
        "error": "All Keys Rate Limited",
        "prompt_to_run": prompt
    }
