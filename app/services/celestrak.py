"""Lookup against CelesTrak, the catalogue the trajectory calculation uses.

A satellite is registered here with a NORAD ID, and that same ID is what the
scheduler later feeds to the propagator. If the ID is wrong, nothing fails
loudly — the station simply tracks a different object. So the registration form
resolves the ID against CelesTrak first and shows the operator the official
object name to confirm against.

This talks to CelesTrak directly rather than reusing the station's tracking
library: this application is a separate deployable with its own release cycle,
and a handful of lines of URL building is a cheaper price than coupling the two.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import requests

logger = logging.getLogger(__name__)

BASE_URL = "https://celestrak.org/NORAD/elements/gp.php"
TIMEOUT_SECONDS = 10

# A query that matches nothing comes back as HTTP 404 with this plain-text body,
# not as an empty JSON array. It has to be recognised BEFORE raise_for_status,
# otherwise "this ID does not exist" is indistinguishable from "the site is
# down" — and those two need opposite handling: the first must block the save,
# the second must not.
NO_DATA_MARKER = "No GP data found"


class CelestrakUnavailable(RuntimeError):
    """CelesTrak could not be reached, so nothing could be confirmed."""


def _query(params: Dict[str, Any]) -> List[Dict[str, Any]]:
    params = {**params, "FORMAT": "json"}
    try:
        response = requests.get(BASE_URL, params=params, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as error:
        raise CelestrakUnavailable(str(error)) from error

    if NO_DATA_MARKER in response.text:
        return []

    try:
        response.raise_for_status()
    except requests.RequestException as error:
        raise CelestrakUnavailable(str(error)) from error

    try:
        payload = response.json()
    except ValueError as error:
        raise CelestrakUnavailable(
            f"unexpected response from CelesTrak: {response.text[:120]!r}"
        ) from error

    return payload if isinstance(payload, list) else [payload]


def _summarise(entry: Dict[str, Any]) -> Dict[str, Any]:
    """Only the fields an operator needs to recognise the object."""
    return {
        "norad_id": entry.get("NORAD_CAT_ID"),
        "object_name": entry.get("OBJECT_NAME"),
        "object_id": entry.get("OBJECT_ID"),
        "epoch": entry.get("EPOCH"),
        "inclination_deg": entry.get("INCLINATION"),
        "mean_motion": entry.get("MEAN_MOTION"),
    }


def lookup_by_norad_id(norad_id: int) -> Optional[Dict[str, Any]]:
    """The catalogue entry for this ID, or None if the catalogue has no such object."""
    results = _query({"CATNR": norad_id})
    return _summarise(results[0]) if results else None


def search_by_name(name: str, limit: int = 25) -> List[Dict[str, Any]]:
    """Catalogue entries whose name matches, so an ID never has to be guessed."""
    name = name.strip()
    if not name:
        return []
    return [_summarise(entry) for entry in _query({"NAME": name})[:limit]]
