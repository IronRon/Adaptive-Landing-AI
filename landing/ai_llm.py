# The responsibilities of this module:
# Format the prompt
# Call the OpenAI API
# Parse JSON response safely
# Return a dict containing layout + customisations

import json
from openai import OpenAI
import logging
from datetime import datetime
from dotenv import load_dotenv
import os
from pathlib import Path

load_dotenv()  # take environment variables from .env file
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY not set in environment (.env missing or variable not defined)")

client = OpenAI(api_key=OPENAI_API_KEY)

ROOT = Path(__file__).resolve().parent.parent

def _read(path: Path):
    try:
        text = path.read_text(encoding='utf-8')
    except Exception:
        return ""
    cleaned = " ".join(text.split())
    return cleaned

def safe_json_parse(text):
    """
    Safely parse malformed JSON from the LLM.
    Returns dict or {} on failure.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Attempt common fixes
        try:
            cleaned = text.strip().split("```")[-1]
            return json.loads(cleaned)
        except Exception:
            logging.error("LLM returned invalid JSON:\n" + text)
            return {}


def generate_llm_recommendations(prompt_data: dict):
    """
    Calls the LLM and returns JSON-based layout recommendations.
    """


    prompt = f"""
    You are an AI assistant that personalises landing page layouts based on visitor behaviour and interaction data.
    IMPORTANT: Return ONLY valid JSON as the single response. Do NOT return explanations or text outside JSON.

    ### Input Data
    Default Layout: {prompt_data["default_layout"]}
    User Scores: {prompt_data["user_scores"]}
    Visitor Metadata: {prompt_data["visitor_meta"]}
    SITE SECTIONS + CSS: included below for context
    {prompt_data["assets"]}
    COMBINED CSS:
    {prompt_data["combined_css"]}

    ### Task
    1) Prioritise sections according to the interaction data (user_scores first).
       - If a section shows the highest clicks/interactions for this visitor, move that section earlier in the returned "layout" array.
    2) For sections with notable interaction, recommend simple visual emphasis via:
       - inline style string in customizations.<section>.style (e.g. "background: #fffbea; border: 2px solid #ffcc00;")
    3) You may also suggest minor text changes (customizations.<section>.text) to tailor headings or CTAs.
    4) Keep changes small and focused (reordering + highlight styles + optional short text tweak).
    5) Provide a short "explanation" field describing why you made the choices (used for debugging only).

    SCORING RULES (how to use the scores):
    - Treat user_scores as highest priority: a section with the highest user_score should be pushed higher in layout.
    - If no strong signals, preserve the default layout.

    ### Output Format

    {{
    "layout": ["header", "services", "pricing"],
    "customizations": {{
        "header": {{
        "text": "string",
        "style": "background-color: #fffbea; font-size: 16px; border: 2px solid gold;"
        }},
        "services": {{
        "style": "margin: 20px; border: 2px solid gold;"
        }}
    }},
    "explanation": "Reasoning for the layout choices (for debugging purposes)."
    }}
    """
    

    response = client.chat.completions.create(
        model="gpt-5-nano",
        messages=[{"role": "user", "content": prompt}],
    )

    # Prefer response.output_text if present, else fall back to the SDK message content
    out_text = getattr(response, "output_text", None) or response.choices[0].message.content

    # Log to file (timestamped via logging.basicConfig) and also keep one-line safe log
    logging.info("LLM response (truncated 200 chars): %s", (out_text or "")[:200].replace("\n", "\\n"))

    # If you want the full raw output in a separate file:
    try:
        with open(r'c:\Users\Ronak\Documents\MY STUFF1\comp sci\Year4\FYP\adaptive-landing-ai\landing\llm_full_response.txt', 'a', encoding='utf-8') as fh:
            fh.write(f"{datetime.utcnow().isoformat()} - {out_text}\n\n")
    except Exception as e:
        logging.error("Failed to write full LLM response to file: %s", e)


    llm_text = response.choices[0].message.content
    return safe_json_parse(llm_text)
