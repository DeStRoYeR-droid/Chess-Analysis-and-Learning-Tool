"""
Runs CALT's analysis JSON (from ui/debugInterface.py) through a prompt
template (core/prompts/prompt-<index>.txt) on your local OMLX server,
streaming the generated human-readable commentary to the terminal.
 
Talks to the server over its OpenAI-compatible chat completions API,
authenticated with OMLX_API_KEY from the environment (set via a .env file
at the project root, or exported directly as a system environment
variable - either way works, since load_dotenv() only fills in variables
that aren't already set).
 
Requires: pip install openai python-dotenv
 
Usage (standalone, against a saved JSON file):
    python3 core/llmCommentaryGeneration.py path/to/analysis.json <prompt_index>
 
Usage (from debugInterface.py):
    from core.llmCommentaryGeneration import generate_commentary_text
    generate_commentary_text(output, prompt_index=1)
"""
 
import json
import os
import sys
from pathlib import Path

try:
    from core.constants import *
except ImportError:
    from constants import *
 
try:
    from dotenv import load_dotenv
    from openai import OpenAI
except ImportError:
    print(
        "Missing dependencies. Install them with:\n"
        "    pip install openai python-dotenv",
        file=sys.stderr,
    )
    raise

load_dotenv("../.env")
load_dotenv("/.env")

try:
    from mlx_lm import load, generate
except ImportError:
    print(
        "mlx-lm isn't installed. Install it with:\n"
        "    pip install mlx-lm\n"
        "(This only works on Apple Silicon.)",
        file=sys.stderr,
    )
    raise

MAX_TOKENS = 32768
TEMPERATURE = 1
 
OMLX_BASE_URL = os.getenv("OMLX_BASE_URL", "http://localhost:8000/v1")
OMLX_API_KEY = os.getenv("OMLX_API_KEY")
CURRENT_PROMPT_IDX = 1

PROMPT_FILE = PROMPT_FOLDER_PATH + f"/prompt{CURRENT_PROMPT_IDX}.txt"
_PLACEHOLDER = "[PASTE JSON OUTPUT HERE]"

_client = None  # cached connection, set on first get_client() call
 
 
def get_client() -> OpenAI:
    """Establishes (and caches) the connection to the OMLX server."""
    global _client
    if _client is None:
        if not OMLX_API_KEY:
            raise RuntimeError(
                "OMLX_API_KEY not found in the environment. Set it in a .env "
                "file at the project root, or export it as a system "
                "environment variable:\n"
                "    OMLX_API_KEY=your-server-password"
            )
        _client = OpenAI(base_url=OMLX_BASE_URL, api_key=OMLX_API_KEY)
    return _client

def build_prompt(analysis_json: str, prompt_index: int) -> str:
    """
    Fills the placeholder in core/prompts/prompt-<prompt_index>.txt with the
    actual JSON payload. Assumes prompt_index refers to an existing file -
    no validation.
    """
    prompt_path = Path(PROMPT_FOLDER_PATH) / f"prompt-{prompt_index}.txt"
    template = prompt_path.read_text()
    json_text = json.dumps(analysis_json, indent=2)


    return template.replace(_PLACEHOLDER, json_text)

def build_prompt(analysis_json: dict, prompt_index: int = CURRENT_PROMPT_IDX) -> str:
    """
    Fills the placeholder in core/prompts/prompt-<prompt_index>.txt with the
    actual JSON payload. Assumes prompt_index refers to an existing file -
    no validation.
    """
    prompt_path = Path(PROMPT_FOLDER_PATH) / f"prompt-{prompt_index}.txt"
    template = prompt_path.read_text()
    json_text = json.dumps(analysis_json, indent=2)
    return template.replace(_PLACEHOLDER, json_text)
 
 
def generate_commentary_text(analysis_json: dict, prompt_index: int = CURRENT_PROMPT_IDX) -> str:
    """
    Builds the prompt (prompt-<prompt_index>.txt filled with analysis_json),
    sends it to the OMLX server, streams the response live to the
    terminal, and returns the final generated text.
    """
    client = get_client()
    prompt_text = build_prompt(analysis_json, prompt_index)
    messages = [{"role": "user", "content": prompt_text}]
 
    request_kwargs = dict(
        model=LLM_MODEL,
        messages=messages,
        max_tokens=MAX_TOKENS,
        temperature=TEMPERATURE,
        stream=True,
    )
 
    try:
        # Best-effort: some models (e.g. Qwen3/3.5-style hybrid-thinking
        # models) support disabling the <think>...</think> reasoning
        # preamble this way, which only adds latency for this templated-
        # writing task. Not every server/model supports the field, so fall
        # back silently if the request is rejected.
        stream = client.chat.completions.create(
            **request_kwargs, extra_body={"enable_thinking": False}
        )
    except Exception:
        stream = client.chat.completions.create(**request_kwargs)
 
    print("\n" + "=" * 70)
    print("COMMENTARY")
    print("=" * 70 + "\n")
 
    chunks = []
    for event in stream:
        delta = event.choices[0].delta.content
        if delta:
            print(delta, end="", flush=True)
            chunks.append(delta)
    print()  # trailing newline once streaming finishes
 
    return "".join(chunks)

def generate_from_output_file(prompt_index: int, output_filename: str = "output.json") -> str:
    """
    Convenience wrapper: reads the analysis JSON from output.json (project
    root - one level up from core/) and runs it through
    generate_commentary_text().
 
    Pass a different output_filename if debugInterface.py's output ever
    lives somewhere other than the project root, or under a different name.
    """
    output_path = Path(__file__).resolve().parent.parent / output_filename
    if not output_path.exists():
        raise FileNotFoundError(
            f"Couldn't find {output_path}. Make sure debugInterface.py's "
            f"JSON output has been saved there (e.g. "
            f"`python3 ui/debugInterface.py > {output_filename}`), or pass "
            f"a different output_filename."
        )
 
    with open(output_path) as f:
        analysis_json = json.load(f)
 
    return generate_commentary_text(analysis_json, prompt_index)

if __name__ == "__main__":
    generate_from_output_file(prompt_index=1)