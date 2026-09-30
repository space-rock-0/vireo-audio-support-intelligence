"""Load CSVs via DuckDB, dedup to the canonical ticket table (D5).

Canonical rule: one row per ticket_id, keep the `helpdesk` copy.
stable_row_key = ticket_id__source_system__raw_seq (audit-stable).
"""
from __future__ import annotations

import csv
import os

import duckdb

DATA_DIR = os.environ.get("VIREO_DATA_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "Veo"))

TICKET_FILE = "tickets.csv"
ROSTER_FILE = "agents.csv"


def _read_csv(path: str) -> tuple[list[str], list[dict]]:
    """DuckDB parses the multiline quoted fields; rows come back as dicts."""
    con = duckdb.connect()
    rel = con.execute(
        "SELECT * FROM read_csv(?, header=true, quote='\"', escape='\"', sample_size=-1)",
        [path],
    )
    cols = [d[0] for d in rel.description]
    rows = [dict(zip(cols, r)) for r in rel.fetchall()]
    con.close()
    # Normalise everything to stripped strings (None -> "").
    # DuckDB returns timestamps/dates as objects — format them back
    # to the helpdesk display precision (minutes for timestamps).
    import datetime as _dt

    def _s(v):
        if v is None:
            return ""
        if isinstance(v, _dt.datetime):
            # Preserve seconds when nonzero (C1: flooring 10:15:30 -> 10:15
            # flips SLA-boundary breaches). Current export has none, but the
            # pipeline must not corrupt them if they appear.
            return v.strftime("%Y-%m-%d %H:%M:%S") if (v.second or v.microsecond) else v.strftime("%Y-%m-%d %H:%M")
        if isinstance(v, _dt.date):
            return v.strftime("%Y-%m-%d")
        return str(v).strip()

    norm = [{k: _s(v) for k, v in r.items()} for r in rows]
    return cols, norm


def load_tickets(data_dir: str = DATA_DIR) -> list[dict]:
    _, rows = _read_csv(os.path.join(data_dir, TICKET_FILE))
    out = []
    for seq, r in enumerate(rows):
        r = dict(r)
        r["stable_row_key"] = f"{r['ticket_id']}__{r['source_system']}__{seq}"
        out.append(r)
    return out


def deduplicate(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    """Returns (canonical, quarantine). Keeps helpdesk copy of each dup group."""
    by_id: dict[str, list[dict]] = {}
    for r in rows:
        by_id.setdefault(r["ticket_id"], []).append(r)
    canon, quar = [], []
    for tid, group in by_id.items():
        if len(group) == 1:
            canon.append(group[0])
            continue
        # Prefer helpdesk (intact timestamps, D5). Same-system dupes (never
        # observed: all 653 groups are cross-system) fall back to file order.
        keep = next((r for r in group if r["source_system"] == "helpdesk"), group[0])
        canon.append(keep)
        quar.extend(r for r in group if r is not keep)
    return canon, quar


def load_roster(data_dir: str = DATA_DIR) -> list[dict]:
    _, rows = _read_csv(os.path.join(data_dir, ROSTER_FILE))
    return rows


def load_reference_sets(data_dir: str = DATA_DIR) -> dict[str, set]:
    """Distinct join keys from reference tables (FK orphan checks)."""
    con = duckdb.connect()
    out = {}
    for name, col in (("orders.csv", "order_id"), ("customers.csv", "customer_id"),
                      ("products.csv", "sku")):
        try:
            vals = con.execute(
                f'SELECT DISTINCT "{col}" FROM read_csv(?, header=true)',
                [os.path.join(data_dir, name)],
            ).fetchall()
            out[name.split(".")[0]] = {str(v[0]).strip() for v in vals if v[0] is not None}
        except Exception:
            pass
    con.close()
    out["agents"] = set()
    try:
        _, roster = _read_csv(os.path.join(data_dir, ROSTER_FILE))
        out["agents"] = {(r.get("agent_id") or "").strip() for r in roster}
    except Exception:
        pass
    return {"orders": out.get("orders", set()), "customers": out.get("customers", set()),
            "skus": out.get("products", set()), "agents": out.get("agents", set())}


def write_csv(path: str, rows: list[dict], cols: list[str]) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)
