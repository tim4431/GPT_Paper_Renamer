"""Filename-based metadata lookup: recognize arXiv IDs / DOIs in the filename
and fetch title+author from arXiv or Crossref APIs before falling back to the
LLM. Zero external dependencies — uses stdlib urllib + xml.etree + json.

Entry point: ``try_lookup(filename_stem)`` -> Optional[Paper].
Returns None on no match, network error, or malformed response — the caller
is expected to fall back to the GPT extractor in that case.
"""

from __future__ import annotations

import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

import yaml

from .extractor import Paper
from .files import strip_duplicate_marker

log = logging.getLogger(__name__)

_PATTERNS_FILE = Path(__file__).resolve().parent / "patterns.yaml"
_USER_AGENT = "GPTPaperRenamer/1.0 (+https://github.com/tim4431/GPT_Paper_Renamer)"
_TIMEOUT_SECONDS = 10.0

_ARXIV_ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


@dataclass(frozen=True)
class _Source:
    name: str
    api: str                  # "arxiv" | "crossref"
    prefix: str               # DOI prefix to prepend (crossref only)
    patterns: List[re.Pattern]


_sources: Optional[List[_Source]] = None


def _load_sources() -> List[_Source]:
    global _sources
    if _sources is not None:
        return _sources
    try:
        with _PATTERNS_FILE.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    except OSError:
        log.exception("Could not read %s", _PATTERNS_FILE)
        _sources = []
        return _sources

    out: List[_Source] = []
    for entry in data.get("sources", []):
        try:
            name = str(entry["name"])
            api = str(entry["api"]).lower()
            prefix = str(entry.get("prefix", ""))
            patterns = [re.compile(p, re.IGNORECASE) for p in entry["patterns"]]
        except (KeyError, re.error, TypeError):
            log.exception("Invalid entry in patterns.yaml: %r", entry)
            continue
        if api not in ("arxiv", "crossref"):
            log.warning("Unknown api %r in patterns.yaml; skipping", api)
            continue
        out.append(_Source(name=name, api=api, prefix=prefix, patterns=patterns))
    _sources = out
    return _sources


# --- HTTP helpers -----------------------------------------------------------

def _http_get(url: str, *, accept: str) -> Optional[bytes]:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, "Accept": accept},
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            if resp.status != 200:
                log.warning("GET %s -> %d", url, resp.status)
                return None
            return resp.read()
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as e:
        log.info("HTTP error for %s: %s", url, e)
        return None


# --- arXiv ------------------------------------------------------------------

def _arxiv_lookup(arxiv_id: str) -> Optional[Paper]:
    url = "http://export.arxiv.org/api/query?" + urllib.parse.urlencode(
        {"id_list": arxiv_id, "max_results": "1"}
    )
    body = _http_get(url, accept="application/atom+xml")
    if body is None:
        return None
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        log.exception("arXiv: could not parse XML for %s", arxiv_id)
        return None

    entry = root.find("atom:entry", _ARXIV_ATOM_NS)
    if entry is None:
        log.info("arXiv: no entry for %s", arxiv_id)
        return None

    title_el = entry.find("atom:title", _ARXIV_ATOM_NS)
    author_el = entry.find("atom:author/atom:name", _ARXIV_ATOM_NS)
    if title_el is None or author_el is None:
        return None

    # arXiv line-wraps titles; collapse whitespace.
    title = re.sub(r"\s+", " ", (title_el.text or "")).strip()
    author = (author_el.text or "").strip()
    if not title or not author:
        return None
    return Paper(title=title, author=author)


# --- Crossref ---------------------------------------------------------------

def _crossref_lookup(doi: str) -> Optional[Paper]:
    doi = doi.strip().rstrip(".")
    url = "https://api.crossref.org/works/" + urllib.parse.quote(doi, safe="/:")
    body = _http_get(url, accept="application/json")
    if body is None:
        return None
    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        log.exception("Crossref: could not parse JSON for %s", doi)
        return None

    msg = payload.get("message") or {}
    titles = msg.get("title") or []
    authors = msg.get("author") or []
    if not titles or not authors:
        log.info("Crossref: missing title or author for %s", doi)
        return None

    title = re.sub(r"\s+", " ", str(titles[0])).strip()
    a0 = authors[0] or {}
    given = str(a0.get("given", "")).strip()
    family = str(a0.get("family", "")).strip()
    author = (given + " " + family).strip() or str(a0.get("name", "")).strip()
    if not title or not author:
        return None
    return Paper(title=title, author=author)


# --- Public API -------------------------------------------------------------

def try_lookup(filename_stem: str) -> Optional[Tuple[Paper, str]]:
    """Attempt to identify *filename_stem* and fetch metadata from a public API.

    Strips browser duplicate markers (" (1)" etc.) before pattern matching.
    Returns ``(Paper, source_name)`` on success, or None if nothing matches
    or the API call fails — the caller should fall back to the LLM extractor
    in that case. ``source_name`` is the human-readable tag from patterns.yaml
    (e.g. ``"arXiv"``, ``"Nature"``, ``"Generic DOI"``).
    """
    cleaned = strip_duplicate_marker(filename_stem)
    for source in _load_sources():
        for pattern in source.patterns:
            m = pattern.search(cleaned)
            if not m:
                continue
            identifier = m.group("id")
            log.info("Filename lookup matched %s id=%s", source.name, identifier)
            if source.api == "arxiv":
                paper = _arxiv_lookup(identifier)
            else:  # crossref
                doi = source.prefix + identifier if source.prefix else identifier
                paper = _crossref_lookup(doi)
            if paper is not None:
                return paper, source.name
            log.info("Filename lookup (%s) fetched nothing; continuing", source.name)
    return None
