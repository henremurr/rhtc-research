"""Read-only reconciliation of shadow feeds with the periodic full catalog.

Differences are diagnostic, not deletion instructions. A full scan spans an
interval, and metadata updates can occur during that interval.
"""
import json
import logging
from contextlib import closing
from app.options import kalshi_ingestion as ki
from app.options import kalshi_metadata_sync as km
from app.options import kalshi_quote_refresh as kq

log=logging.getLogger(__name__)


def reconcile():
    # Initialize additive tables before acquiring the read transaction.
    with closing(km.connect()),closing(kq.connect()):
        pass
    with closing(ki.connect()) as db:
        db.execute("BEGIN")
        scan=db.execute("SELECT stamp,count FROM scans ORDER BY stamp DESC LIMIT 1").fetchone()
        if not scan:
            return {"status":"waiting for full scan"}
        stamp=scan["stamp"]
        actual=db.execute("SELECT COUNT(*) FROM snapshots WHERE stamp=?",(stamp,)).fetchone()[0]
        # Compare only known shadow metadata changes, not the entire universe.
        counts=db.execute("""SELECT COUNT(*) AS changes,
            COALESCE(SUM(CASE WHEN s.id IS NOT NULL THEN 1 ELSE 0 END),0) AS present,
            COALESCE(SUM(CASE WHEN s.id IS NULL AND m.status IN ('active','open') THEN 1 ELSE 0 END),0) AS active_absent,
            COALESCE(SUM(CASE WHEN s.id IS NOT NULL AND m.status NOT IN ('active','open') THEN 1 ELSE 0 END),0) AS inactive_present,
            COALESCE(SUM(CASE WHEN s.id IS NOT NULL AND json_extract(s.payload,'$._metadata') IS NOT NULL
                AND json_extract(s.payload,'$._metadata')<>m.metadata_key THEN 1 ELSE 0 END),0) AS rule_differences
            FROM metadata_current m LEFT JOIN snapshots s ON s.stamp=? AND s.id=m.id""",(stamp,)).fetchone()
        quotes=db.execute("""SELECT COUNT(*) AS observed,
            COALESCE(SUM(CASE WHEN s.id IS NULL THEN 1 ELSE 0 END),0) AS absent
            FROM quote_current q LEFT JOIN snapshots s ON s.stamp=? AND s.id=q.id""",(stamp,)).fetchone()
        watermark=db.execute("SELECT upper_ts FROM metadata_watermark WHERE id=1").fetchone()
        result={"status":"ok" if actual==scan["count"] else "integrity mismatch",
            "scan_stamp":stamp,"declared_count":scan["count"],"actual_count":actual,
            "metadata_watermark":watermark[0] if watermark else None,
            "metadata_comparison":dict(counts),"quote_comparison":dict(quotes),
            "interpretation":"Shadow changes are not a complete catalog. Differences may reflect lifecycle timing; no automatic deletion or quote replacement."}
    log.warning("Kalshi reconciliation: %s",json.dumps(result))
    return result
