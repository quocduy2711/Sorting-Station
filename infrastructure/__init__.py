"""
infrastructure/ — Concrete adapters implementing domain ports.

RULE: This layer MUST NOT be imported by services/.
RULE: Only main.py (composition root) wires infrastructure to ports.
RULE: All external dependencies (aiohttp, paho, sqlite3) live here.
"""
