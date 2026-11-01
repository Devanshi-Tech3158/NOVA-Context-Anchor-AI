"""LLM client interface and testing doubles."""

import json
import logging
import re
from typing import Any, Protocol, runtime_checkable

import httpx

logger = logging.getLogger("nova.core.llm")


@runtime_checkable
class LLMClient(Protocol):
    """Protocol for language model completion providers."""

    def complete(self, prompt: str, *, json: bool = False) -> str:
        """Generate a response completion for the prompt."""
        ...


class FakeLLM:
    """Scripted LLM implementation for offline testing."""

    def __init__(
        self,
        responses: list[str] | dict[str, str] | str | None = None,
        default_response: str = "",
    ) -> None:
        """Initialize FakeLLM with scripted responses."""
        self.default_response = default_response
        self.calls: list[dict[str, Any]] = []
        if isinstance(responses, str):
            self._responses_list = [responses]
            self._responses_dict: dict[str, str] = {}
        elif isinstance(responses, list):
            self._responses_list = list(responses)
            self._responses_dict = {}
        elif isinstance(responses, dict):
            self._responses_list = []
            self._responses_dict = dict(responses)
        else:
            self._responses_list = []
            self._responses_dict = {}

    def complete(self, prompt: str, *, json: bool = False) -> str:
        """Return scripted response matching the prompt or next in list."""
        self.calls.append({"prompt": prompt, "json": json})
        if prompt in self._responses_dict:
            return self._responses_dict[prompt]
        if self._responses_list:
            return self._responses_list.pop(0)
        return self.default_response


class GeminiLLM:
    """Google Gemini API client."""

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash") -> None:
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str, *, json: bool = False) -> str:
        """Generate text completion via Google Gemini REST API."""
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent?key={self.api_key}"
        )
        headers = {"Content-Type": "application/json"}
        payload: dict[str, Any] = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1},
        }
        if json:
            payload["generationConfig"]["responseMimeType"] = "application/json"
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return parts[0].get("text", "")
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
            logger.warning("Gemini LLM completion failed: %s", exc)
        return ""


class OpenAILLM:
    """OpenAI API client."""

    def __init__(self, api_key: str, model: str = "gpt-4o-mini") -> None:
        self.api_key = api_key
        self.model = model

    def complete(self, prompt: str, *, json: bool = False) -> str:
        """Generate text completion via OpenAI chat completions."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        if json:
            payload["response_format"] = {"type": "json_object"}
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(url, headers=headers, json=payload)
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if choices:
                    return choices[0].get("message", {}).get("content", "")
        except (httpx.HTTPError, json.JSONDecodeError, KeyError) as exc:
            logger.warning("OpenAI LLM completion failed: %s", exc)
        return ""


class HeuristicLLM:
    """Intelligent offline fallback LLM that parses prompts and produces structured outputs."""

    def complete(self, prompt: str, *, json: bool = False) -> str:
        """Produce structured extraction or verification decisions heuristically."""
        # Check if prompt is memory extraction
        if "Conversation turns to analyze" in prompt or "extract memories" in prompt.lower():
            return self._heuristic_extract(prompt)

        # Check if prompt is claim splitting
        if "split" in prompt.lower() and "claim" in prompt.lower():
            return self._heuristic_split(prompt)

        # Check if prompt is evidence judging
        if "verify claims against stored memories" in prompt.lower() or "judge" in prompt.lower():
            return self._heuristic_judge(prompt)

        return "NOVA Context Anchor verified result."

    def _heuristic_extract(self, prompt: str) -> str:
        results: list[dict[str, Any]] = []
        msg_pattern = re.compile(r"\[(m\d+|[^\]]+)\]\s*\(([^)]+)\):\s*(.+)", re.MULTILINE)
        matches = msg_pattern.findall(prompt)

        for msg_id, role, text in matches:
            text_str = text.strip()
            # Match decision phrases
            m_dec = re.search(
                r"(?:decided|use|using|switch(?:ed)? to|chose|choose)\s+([A-Za-z0-9_ -]+?)\s+(?:for|as)\s+([A-Za-z0-9_ -]+)",
                text_str,
                re.IGNORECASE,
            )
            if m_dec:
                val, subj = m_dec.group(1).strip(), m_dec.group(2).strip()
                results.append(
                    {
                        "type": "decision",
                        "subject": subj.lower().replace(" ", "_"),
                        "value": val,
                        "reason": "Team decision in discussion",
                        "source_msg_id": msg_id,
                        "source_quote": text_str,
                        "confidence": 0.95,
                    }
                )
                continue

            # Fallback subject extraction
            words = text_str.split()
            if len(words) >= 3:
                subject = words[0].lower().replace(" ", "_")
                results.append(
                    {
                        "type": "fact",
                        "subject": subject,
                        "value": text_str,
                        "reason": "Stated fact",
                        "source_msg_id": msg_id,
                        "source_quote": text_str,
                        "confidence": 0.85,
                    }
                )

        return json.dumps(results)

    def _heuristic_split(self, prompt: str) -> str:
        # Extract the answer from prompt
        match = re.search(r"Answer to split:\s*(.+)", prompt, re.DOTALL | re.IGNORECASE)
        answer = match.group(1).strip() if match else prompt
        claims = [c.strip() for c in re.split(r"[.!?]\s+", answer) if c.strip()]
        return json.dumps(claims if claims else [answer])

    def _heuristic_judge(self, prompt: str) -> str:
        # Extract memories and claims
        verdicts: list[dict[str, Any]] = []
        claim_matches = re.findall(r"(\d+)\.\s*\"([^\"]+)\"", prompt)
        mem_matches = re.findall(r"id=\"([^\"]+)\"\s+value=\"([^\"]+)\"", prompt)

        mem_dict = {val.lower(): m_id for m_id, val in mem_matches}

        for idx_str, claim_text in claim_matches:
            c_idx = int(idx_str)
            claim_lower = claim_text.lower()
            matched_id = None
            for val_lower, m_id in mem_dict.items():
                if val_lower in claim_lower or claim_lower in val_lower:
                    matched_id = m_id
                    break

            if matched_id:
                verdicts.append(
                    {
                        "claim_idx": c_idx,
                        "label": "supported",
                        "memory_ids": [matched_id],
                        "rationale": "Directly supported by stored context anchor memory",
                    }
                )
            else:
                verdicts.append(
                    {
                        "claim_idx": c_idx,
                        "label": "unsupported",
                        "memory_ids": [],
                        "rationale": "Absence of stored evidence in memories",
                    }
                )

        return json.dumps(verdicts)
