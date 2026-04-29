"""Claude AI task breakdown for user stories."""

import json
import re

import requests

SYSTEM_PROMPT = """You are a senior agile software engineer.
Given a user story, decompose it into concrete development tasks.

Return ONLY a valid JSON array — no markdown, no explanation.
Each element:
  "title"       — short imperative phrase (e.g. "Add login endpoint")
  "description" — 1-2 sentences on what to implement or verify
  "priority"    — 1=Critical  2=High  3=Medium  4=Low
  "effort"      — estimated hours (number)
  "tags"        — semicolon-separated (e.g. "backend;api")

Cover: backend, frontend, DB, tests, docs, DevOps as appropriate.
Aim for 4–8 focused tasks."""


def ai_breakdown(story_text: str, api_key: str) -> list[dict]:
    """Call Claude to break down story into tasks."""
    r = requests.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        json={
            "model": "claude-sonnet-4-20250514",
            "max_tokens": 2048,
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": f"User story:\n\n{story_text}"}],
        },
        timeout=60,
    )
    r.raise_for_status()
    raw = r.json()["content"][0]["text"].strip()
    raw = re.sub(r"^```(?:json)?", "", raw).rstrip("`").strip()
    return json.loads(raw)
