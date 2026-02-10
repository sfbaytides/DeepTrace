"""Carl AI integration for cold case analysis.

This module provides AI-powered analysis using Carl (Qwen 2.5 3B Instruct)
running on Ollama at ai.baytides.org.
"""

from __future__ import annotations

import os
import logging
from typing import Any

import requests

logger = logging.getLogger(__name__)

# Carl's Ollama endpoint
CARL_API_URL = os.getenv("CARL_API_URL", "https://ai.baytides.org/api/generate")
CARL_DEFAULT_MODEL = os.getenv("CARL_DEFAULT_MODEL", "qwen2.5:3b-instruct")


def analyze_with_carl(
    prompt: str,
    mode: str = "default",
    model: str | None = None,
    context: dict[str, Any] | None = None,
    timeout: int = 30
) -> dict[str, Any]:
    """Send analysis request to Carl AI (Ollama).

    Args:
        prompt: The question or evidence to analyze
        mode: Analyst mode (default, devils-advocate, red-hat, what-if, sensitivity)
        model: Model to use (defaults to CARL_DEFAULT_MODEL)
        context: Optional metadata about the request
        timeout: Request timeout in seconds

    Returns:
        dict with keys:
            - response: The AI analysis text
            - model: Model used
            - success: Whether the request succeeded
            - error: Error message if failed
    """
    if model is None:
        model = CARL_DEFAULT_MODEL

    # Build full prompt with system prompt + user prompt
    system_prompt = _get_system_prompt(mode)
    full_prompt = f"{system_prompt}\n\nUser Query:\n{prompt}"

    # Ollama API format
    payload = {
        "model": model,
        "prompt": full_prompt,
        "stream": False,
        "options": {
            "temperature": 0.7,
            "num_predict": 4096
        }
    }

    try:
        response = requests.post(
            CARL_API_URL,
            json=payload,
            timeout=timeout
        )
        response.raise_for_status()

        data = response.json()

        return {
            "response": data.get("response", ""),
            "model": data.get("model", model),
            "success": True,
            "error": None
        }

    except requests.exceptions.Timeout:
        logger.error(f"Carl AI request timed out after {timeout}s")
        return {
            "response": "",
            "model": model,
            "success": False,
            "error": f"Request timed out after {timeout} seconds"
        }

    except requests.exceptions.RequestException as e:
        logger.error(f"Carl AI request failed: {e}")
        return {
            "response": "",
            "model": model,
            "success": False,
            "error": f"Request failed: {str(e)}"
        }

    except Exception as e:
        logger.error(f"Unexpected error in Carl AI request: {e}")
        return {
            "response": "",
            "model": model,
            "success": False,
            "error": f"Unexpected error: {str(e)}"
        }


def _get_system_prompt(mode: str) -> str:
    """Get system prompt for each analyst mode.

    These modes implement different analytical perspectives based on
    formal investigative methodologies.
    """

    prompts = {
        "default": """You are an expert cold case analyst using ACH (Analysis of Competing Hypotheses) methodology.

Your role:
- Analyze evidence objectively and identify competing hypotheses
- Consider which hypotheses this evidence supports vs contradicts
- Identify cognitive biases (confirmation bias, anchoring, availability heuristic)
- Assess diagnostic value: does this evidence distinguish between hypotheses?
- Flag assumptions and gaps in reasoning

Provide balanced, methodical analysis. Focus on evidence quality and logical inference.""",

        "devils-advocate": """You are a devil's advocate analyst challenging the leading hypothesis.

Your role:
- Identify the most commonly accepted theory about this case
- Actively search for weaknesses, gaps, and contradictions in that theory
- Propose alternative explanations that have been overlooked
- Question assumptions that investigators may have taken for granted
- Highlight evidence that contradicts the leading hypothesis

Be rigorous and skeptical. Your job is to stress-test the prevailing narrative.""",

        "red-hat": """You are analyzing this case from the perpetrator's perspective (Red Hat thinking).

Your role:
- Reason from the offender's point of view: motivations, opportunities, constraints
- Consider what behaviors or patterns would make sense from their perspective
- Identify what risks they would have taken and why
- Analyze MO (modus operandi) vs signature behaviors
- Consider victim selection and targeting patterns

This is analytical perspective-taking for investigative purposes. Focus on behavioral patterns and decision-making.""",

        "what-if": """You are conducting "What-If" scenario analysis for this cold case.

Your role:
- Assume an unlikely or previously dismissed scenario actually occurred
- Work backward from that assumption to identify what evidence would support it
- Identify what new information would be needed to validate this scenario
- Challenge conventional thinking about timing, sequence, or actor involvement
- Explore alternative interpretations of existing evidence

Think creatively while remaining grounded in evidence. Look for overlooked possibilities.""",

        "sensitivity": """You are conducting sensitivity analysis on key evidence items.

Your role:
- Identify the most diagnostic pieces of evidence (those that distinguish between hypotheses)
- Test how removing or re-interpreting each key item changes the overall picture
- Assess which evidence is load-bearing vs corroborative
- Identify which items, if proven unreliable, would most change conclusions
- Highlight dependencies and circular reasoning

Focus on evidence robustness and hypothesis stability. Which conclusions are fragile?"""
    }

    return prompts.get(mode, prompts["default"])


def get_available_modes() -> list[dict[str, str]]:
    """Get list of available analyst modes with descriptions."""
    return [
        {
            "id": "default",
            "name": "Default (ACH)",
            "description": "Balanced analysis using Analysis of Competing Hypotheses methodology"
        },
        {
            "id": "devils-advocate",
            "name": "Devil's Advocate",
            "description": "Challenges the leading hypothesis and identifies weaknesses"
        },
        {
            "id": "red-hat",
            "name": "Red Hat (Perpetrator)",
            "description": "Analyzes from the offender's perspective and behavioral patterns"
        },
        {
            "id": "what-if",
            "name": "What-If Scenarios",
            "description": "Explores unlikely scenarios and alternative interpretations"
        },
        {
            "id": "sensitivity",
            "name": "Sensitivity Analysis",
            "description": "Tests which evidence is most critical to conclusions"
        }
    ]


def is_carl_available() -> bool:
    """Check if Carl AI is reachable.

    Returns:
        True if Carl responds to health check, False otherwise
    """
    try:
        response = requests.get(
            CARL_API_URL.replace("/api/generate", "/api/tags"),
            timeout=5
        )
        return response.status_code == 200
    except Exception:
        return False
