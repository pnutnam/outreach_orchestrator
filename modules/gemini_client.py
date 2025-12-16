import json
import logging
import os

logger = logging.getLogger(__name__)

def generate_gem_prompt(context_package: dict, gem_url: str = None) -> str:
    """
    Constructs the prompt to send to the Gemini Gem.
    Reads from templates/prompt_template.txt
    """
    context_str = json.dumps(context_package, indent=2)
    
    GEM_LINK = gem_url if gem_url else "https://gemini.google.com/gem/1olyB7e5v41fSxu03e_PRBzOVXeP2RseL?usp=sharing"
    
    # Path to template
    template_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates", "prompt_template.txt")
    
    try:
        with open(template_path, "r") as f:
            template = f.read()
    except Exception as e:
        logger.error(f"Failed to load prompt template from {template_path}: {e}")
        # Fallback to a minimal string just in case
        return f"Analyze this context: {context_str}"

    # Replace placeholders
    prompt = template.replace("{{GEM_LINK}}", GEM_LINK).replace("{{CONTEXT_STR}}", context_str)
    
    return prompt



import google.generativeai as genai
from .credentials import get_gemini_pool

# Valid Gemini Keys Pool (Full objects now)
GEMINI_POOL = get_gemini_pool()
CURRENT_KEY_IDX = 0 # Global state for rotation persistence

def consult_gem(context_package: dict, api_key: str = None) -> dict:
    """
    Calls Gemini, rotating keys if Rate Limits are hit.
    """
    global CURRENT_KEY_IDX
    
    # Prompt is now generated inside loop with rotating Gem URL
    
    # 1. Determine Initial Key (arg > env > pool[0])
    current_key_idx = 0
    # Try to find which key matches arg/env to start there? 
    # Or just ignore env if we have a robust pool?
    # Let's prioritize the pool for rotation.
    
    # Retry Loop (across keys)
    import time
    
    # Total attempts = (keys * 2) to give each key a couple chances?
    # Let's simple cycle through the pool.
    
    for attempt in range(len(GEMINI_POOL)):
        cred = GEMINI_POOL[CURRENT_KEY_IDX % len(GEMINI_POOL)]
        key = cred["gemini_key"]
        prompt = generate_gem_prompt(context_package, cred.get("gem_url"))
        
        try:
            genai.configure(api_key=key)
            # Switching to Gemma 3 27B IT (Higher Limits: 30 RPM / 14.4k RPD)
            model = genai.GenerativeModel('gemma-3-27b-it') 
            
            logger.info(f"Calling Gemini API (Key ...{key[-4:]})...") # Verbose
            
            # Gemma does not support JSON mode. Using default.
            response = model.generate_content(prompt)
            
            # Safety Check
            try:
                txt = response.text
            except Exception as e:
                logger.error(f"Gemini Response Error (Blocked?): {e} | Feedback: {response.prompt_feedback}")
                # Do not retry on safety blocks, just fail this key/prompt
                return {"status": "error", "error": f"Blocked/Empty: {e}"}

            # Manual JSON Extraction (for Gemma)
            try:
                # Strip markdown code blocks if present
                clean_txt = txt.replace("```json", "").replace("```", "").strip()
                result_json = json.loads(clean_txt)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON from Gemma: {e}\nResponse: {txt[:200]}...")
                return {"status": "error", "error": f"JSON Parse Error: {e}"}
            return {
                "status": "success",
                "data": result_json,
                "raw_response": response.text
            }

        except Exception as e:
            err_str = str(e)
            
            # Rotate on Rate Limit (429) OR Auth Errors (403 Leaked/Invalid)
            if any(code in err_str for code in ["429", "quota"]):
                logger.warning(f"Rate Limit on Key ...{key[-4:]}. Sleeping 5s then rotating...")
                time.sleep(5)
                CURRENT_KEY_IDX += 1
                continue
            
            elif any(code in err_str for code in ["403", "leaked", "permission"]):
                logger.warning(f"Key ...{key[-4:]} INVALID/LEAKED. Rotating immediately...")
                CURRENT_KEY_IDX += 1
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
