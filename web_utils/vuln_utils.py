# web_utils/vuln_utils.py
"""
Vulnerability management and CVE enrichment utilities.
Handles vulnerability data, CVE metadata, and enrichment from external sources.
Optimized for low-power devices like Raspberry Pi Zero.
"""
from __future__ import annotations

import json
import time
import urllib.request
import urllib.parse
from typing import Any, Dict, Optional, List, Union
from urllib.parse import urlparse, parse_qs

import logging
from logger import Logger
logger = Logger(name="vuln_utils.py", level=logging.DEBUG)

class CveEnricherOptimized:
    """Optimized CVE enricher for Raspberry Pi Zero."""

    def __init__(self, shared_data):
        self.shared = shared_data
        self.db = shared_data.db
        self._kev_index = set()
        self._last_kev_refresh = 0
        self._kev_ttl = 24 * 3600
        self._nvd_ttl = 48 * 3600
        self._cache_enabled = True
        self._max_parallel_requests = 1

    def get(self, cve_id: str, use_cache_only: bool = False) -> Dict[str, Any]:
        """Retrieve CVE metadata with aggressive caching."""
        try:
            row = self.db.get_cve_meta(cve_id)
        except Exception:
            row = None

        if row:
            try:
                age = time.time() - int(row.get("updated_at") or 0)
            except Exception:
                age = 0
            if use_cache_only or age < self._nvd_ttl * 2:
                return self._format_cached_row(row)

        if use_cache_only:
            return self._get_minimal_cve_data(cve_id)

        try:
            nvd = self._fetch_nvd_minimal(cve_id)
            if nvd:
                data = {
                    "cve_id": cve_id,
                    "description": nvd.get("description", f"{cve_id} vulnerability"),
                    "cvss": nvd.get("cvss"),
                    "references": nvd.get("references", [])[:3],
                    "lastModified": nvd.get("lastModified"),
                    "affected": [],
                    "exploits": [],
                    "is_kev": False,
                    "epss": None,
                    "epss_percentile": None,
                    "updated_at": time.time(),
                }
                try:
                    self.db.upsert_cve_meta(data)
                except Exception:
                    logger.debug("Failed to upsert cve_meta for %s", cve_id, exc_info=True)
                return data
        except Exception:
            logger.debug("NVD fetch failed for %s", cve_id, exc_info=True)

        return self._get_minimal_cve_data(cve_id)

    def get_bulk(self, cve_ids: List[str], max_fetch: int = 5) -> Dict[str, Dict[str, Any]]:
        """Bulk retrieval optimized for Pi Zero."""
        if not cve_ids:
            return {}

        # dedupe and cap
        cve_ids = list(dict.fromkeys(cve_ids))[:50]
        result: Dict[str, Dict[str, Any]] = {}

        try:
            cached = self.db.get_cve_meta_bulk(cve_ids) or {}
            for cid, row in cached.items():
                result[cid] = self._format_cached_row(row)
        except Exception:
            logger.debug("Bulk DB fetch failed", exc_info=True)
            cached = {}

        missing = [c for c in cve_ids if c not in result]

        to_fetch = missing[:max_fetch]
        for cid in to_fetch:
            try:
                data = self.get(cid, use_cache_only=False)
                if data:
                    result[cid] = data
            except Exception:
                logger.debug("Failed to fetch CVE %s", cid, exc_info=True)

        # For the rest, return minimal stubs
        for cid in missing[max_fetch:]:
            result[cid] = self._get_minimal_cve_data(cid)

        return result

    def _fetch_nvd_minimal(self, cve_id: str) -> Dict[str, Any]:
        """Fetch NVD with short timeout and minimal data."""
        url = f"https://services.nvd.nist.gov/rest/json/cves/2.0?cveId={urllib.parse.quote(cve_id)}"

        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode("utf-8"))

            vulns = data.get("vulnerabilities", [])
            if not vulns:
                return {}

            cve = vulns[0].get("cve", {})

            metrics = cve.get("metrics", {})
            cvss = None
            if "cvssMetricV31" in metrics and metrics["cvssMetricV31"]:
                cvss = metrics["cvssMetricV31"][0].get("cvssData")
            elif "cvssMetricV2" in metrics and metrics["cvssMetricV2"]:
                cvss = metrics["cvssMetricV2"][0].get("cvssData")

            desc = ""
            if cve.get("descriptions"):
                desc = cve["descriptions"][0].get("value", "")[:500]

            # references minimal - leave empty for now (can be enriched later)
            return {
                "description": desc,
                "cvss": cvss,
                "references": [],
                "lastModified": cve.get("lastModified"),
            }
        except Exception:
            logger.debug("Error fetching NVD for %s", cve_id, exc_info=True)
            return {}

    def _format_cached_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Format a cached DB row into the API shape."""
        return {
            "cve_id": row.get("cve_id"),
            "description": row.get("description", ""),
            "cvss": row.get("cvss_json"),
            "references": row.get("references_json", []) or [],
            "lastModified": row.get("last_modified"),
            "affected": row.get("affected_json", []) or [],
            "solution": row.get("solution"),
            "exploits": row.get("exploits_json", []) or [],
            "is_kev": bool(row.get("is_kev")),
            "epss": row.get("epss"),
            "epss_percentile": row.get("epss_percentile"),
            "updated_at": row.get("updated_at"),
        }

    def _get_minimal_cve_data(self, cve_id: str) -> Dict[str, Any]:
        """Return minimal data without fetching external sources."""
        year = "2020"
        try:
            parts = cve_id.split("-")
            if len(parts) >= 2:
                year = parts[1]
        except Exception:
            year = "2020"

        # simple heuristic
        try:
            year_int = int(year)
        except Exception:
            year_int = 2020

        if year_int >= 2024:
            severity = "high"
            score = 7.5
        elif year_int >= 2023:
            severity = "medium"
            score = 5.5
        else:
            severity = "low"
            score = 3.5

        return {
            "cve_id": cve_id,
            "description": f"{cve_id} - Security vulnerability",
            "cvss": {"baseScore": score, "baseSeverity": severity.upper()},
            "references": [],
            "affected": [],
            "exploits": [],
            "is_kev": False,
            "epss": None,
            "updated_at": time.time(),
        }


class VulnUtils:
    """Utilities for vulnerability management."""

    def __init__(self, shared_data):
        self.logger = logger
        self.shared_data = shared_data
        self.cve_enricher = CveEnricherOptimized(shared_data) if shared_data else None

    # Helper to write JSON responses
    @staticmethod
    def _send_json(handler, status: int, payload: Any, cache_max_age: Optional[int] = None) -> None:
        try:
            handler.send_response(status)
            handler.send_header("Content-Type", "application/json")
            if cache_max_age is not None:
                handler.send_header("Cache-Control", f"max-age={int(cache_max_age)}")
            handler.end_headers()
            handler.wfile.write(json.dumps(payload).encode("utf-8"))
        except Exception:
            # If writing response fails, log locally (can't do much else)
            logger.exception("Failed to send JSON response")

    def serve_vulns_data_optimized(self, handler) -> None:
        """Optimized API for vulnerabilities with pagination and caching."""
        try:
            parsed = urlparse(handler.path)
            params = parse_qs(parsed.query)

            page = int(params.get("page", ["1"])[0])
            limit = int(params.get("limit", ["50"])[0])
            offset = max((page - 1) * limit, 0)

            db = self.shared_data.db
            vulns = db.query(
                """
                SELECT 
                    v.id, 
                    v.mac_address, 
                    v.ip, 
                    v.hostname, 
                    v.port, 
                    v.vuln_id, 
                    v.is_active, 
                    v.first_seen, 
                    v.last_seen,
                    h.vendor AS host_vendor,
                    h.ips AS current_ips
                FROM vulnerabilities v
                LEFT JOIN hosts h ON v.mac_address = h.mac_address
                WHERE v.is_active = 1
                ORDER BY v.last_seen DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )

            total_row = db.query_one("SELECT COUNT(*) as total FROM vulnerabilities WHERE is_active=1")
            total = total_row["total"] if total_row else 0

            cve_ids = [v["vuln_id"] for v in vulns if (v.get("vuln_id") or "").startswith("CVE-")]

            meta = {}
            if self.cve_enricher and cve_ids:
                # try to use DB bulk first (fast)
                try:
                    meta = db.get_cve_meta_bulk(cve_ids[:20]) or {}
                except Exception:
                    logger.debug("DB bulk meta fetch failed", exc_info=True)
                    meta = {}

            # enrich list
            for vuln in vulns:
                vid = (vuln.get("vuln_id") or "").strip()
                m = meta.get(vid)
                if m:
                    vuln["severity"] = self._get_severity_from_cvss(m.get("cvss_json"))
                    vuln["cvss_score"] = self._extract_cvss_score(m.get("cvss_json"))
                    vuln["description"] = (m.get("description") or "")[:200]
                    vuln["is_kev"] = bool(m.get("is_kev"))
                    vuln["epss"] = m.get("epss")
                else:
                    vuln["severity"] = vuln.get("severity") or "medium"
                    vuln["cvss_score"] = vuln.get("cvss_score")
                    vuln["description"] = vuln.get("description") or f"{vid} vulnerability"
                    vuln["is_kev"] = False
                    vuln["epss"] = None

            response = {
                "vulnerabilities": vulns,
                "pagination": {
                    "page": page,
                    "limit": limit,
                    "total": total,
                    "pages": (total + limit - 1) // limit if limit > 0 else 0,
                },
            }

            self._send_json(handler, 200, response, cache_max_age=10)

        except Exception as e:
            logger.exception("serve_vulns_data_optimized failed")
            self._send_json(handler, 500, {"error": str(e)})

    def fix_vulns_data(self, handler) -> None:
        """Fix vulnerability data inconsistencies."""
        try:
            db = self.shared_data.db
            fixed_count = 0

            vulns_to_fix = db.query(
                """
                SELECT v.id, v.mac_address, h.ips, h.hostnames
                FROM vulnerabilities v
                LEFT JOIN hosts h ON v.mac_address = h.mac_address
                WHERE (v.ip IS NULL OR v.ip = 'NULL' OR v.ip = '')
                OR (v.hostname IS NULL OR v.hostname = 'NULL' OR v.hostname = '')
                """
            )

            for vuln in vulns_to_fix:
                if vuln.get("ips") or vuln.get("hostnames"):
                    ip = vuln["ips"].split(";")[0] if vuln.get("ips") else None
                    hostname = vuln["hostnames"].split(";")[0] if vuln.get("hostnames") else None

                    db.execute(
                        """
                        UPDATE vulnerabilities
                        SET ip = ?, hostname = ?
                        WHERE id = ?
                        """,
                        (ip, hostname, vuln["id"]),
                    )

                    fixed_count += 1

            db.execute("UPDATE vulnerabilities SET port = 0 WHERE port IS NULL")

            db.execute(
                """
                DELETE FROM vulnerabilities 
                WHERE rowid NOT IN (
                    SELECT MIN(rowid) 
                    FROM vulnerabilities 
                    GROUP BY mac_address, vuln_id, port
                )
                """
            )

            response = {
                "status": "success",
                "message": f"Fixed {fixed_count} vulnerability entries",
                "fixed_count": fixed_count,
            }

            self._send_json(handler, 200, response)

        except Exception as e:
            logger.exception("fix_vulns_data failed")
            self._send_json(handler, 500, {"status": "error", "message": str(e)})

    def get_vuln_enrichment_status(self, handler) -> None:
        """Check CVE enrichment status."""
        try:
            stats = self.shared_data.db.query_one(
                """
                SELECT 
                    COUNT(DISTINCT v.vuln_id) as total_cves,
                    COUNT(DISTINCT c.cve_id) as enriched_cves
                FROM vulnerabilities v
                LEFT JOIN cve_meta c ON v.vuln_id = c.cve_id
                WHERE v.vuln_id LIKE 'CVE-%'
                """
            )

            total = stats["total_cves"] or 0
            enriched = stats["enriched_cves"] or 0

            response = {
                "total_cves": total,
                "enriched_cves": enriched,
                "missing": total - enriched,
                "percentage": round(enriched / total * 100, 2) if total > 0 else 0,
            }

            self._send_json(handler, 200, response, cache_max_age=30)

        except Exception as e:
            logger.exception("get_vuln_enrichment_status failed")
            self._send_json(handler, 500, {"error": str(e)})

    def serve_vuln_history(self, handler) -> None:
        """Get vulnerability history with filters."""
        try:
            db = self.shared_data.db
            qs = parse_qs(urlparse(handler.path).query or "")
            cve = (qs.get("cve") or [None])[0]
            mac = (qs.get("mac") or [None])[0]
            try:
                limit = int((qs.get("limit") or ["500"])[0])
            except Exception:
                limit = 500

            rows = db.list_vulnerability_history(cve_id=cve, mac=mac, limit=limit)
            self._send_json(handler, 200, {"history": rows})
        except Exception as e:
            logger.exception("serve_vuln_history failed")
            self._send_json(handler, 500, {"status": "error", "message": str(e)})

    def serve_cve_details(self, handler, cve_id: str) -> None:
        """Get detailed CVE information."""
        try:
            # prefer explicit cve_id param, fallback to path parsing
            cve = cve_id or handler.path.rsplit("/", 1)[-1]
            data = self.cve_enricher.get(cve, use_cache_only=False) if self.cve_enricher else {}

            self._send_json(handler, 200, data)
        except Exception as e:
            logger.exception("serve_cve_details failed")
            self._send_json(handler, 500, {"error": str(e)})

    def serve_cve_bulk(self, handler, data: Dict[str, Any]) -> None:
        """Bulk CVE enrichment."""
        try:
            cves = data.get("cves") or []
            merged = self.cve_enricher.get_bulk(cves) if self.cve_enricher else {}
            self._send_json(handler, 200, {"cves": merged})
        except Exception as e:
            logger.exception("serve_cve_bulk failed")
            self._send_json(handler, 500, {"status": "error", "message": str(e)})

    def serve_exploitdb_by_cve(self, handler, cve_id: str) -> None:
        """Get Exploit-DB entries for a CVE."""
        try:
            data = self.cve_enricher.get(cve_id) if self.cve_enricher else {}
            exploits = data.get("exploits") or []
            self._send_json(handler, 200, {"exploits": exploits})
        except Exception as e:
            logger.exception("serve_exploitdb_by_cve failed")
            self._send_json(handler, 500, {"status": "error", "message": str(e)})

    def _get_severity_from_cvss(self, cvss_json: Union[str, Dict[str, Any], None]) -> str:
        """Extract severity from CVSS data."""
        if not cvss_json:
            return "medium"

        try:
            if isinstance(cvss_json, str):
                cvss = json.loads(cvss_json)
            else:
                cvss = cvss_json

            if not isinstance(cvss, dict):
                return "medium"

            if "baseSeverity" in cvss and cvss.get("baseSeverity"):
                return (cvss["baseSeverity"] or "medium").lower()

            if "baseScore" in cvss:
                score = float(cvss.get("baseScore", 0))
                if score >= 9.0:
                    return "critical"
                elif score >= 7.0:
                    return "high"
                elif score >= 4.0:
                    return "medium"
                else:
                    return "low"
        except Exception:
            logger.debug("Failed to parse cvss_json", exc_info=True)

        return "medium"

    def _extract_cvss_score(self, cvss_json: Union[str, Dict[str, Any], None]) -> Optional[float]:
        """Extract CVSS score."""
        if not cvss_json:
            return None

        try:
            if isinstance(cvss_json, str):
                cvss = json.loads(cvss_json)
            else:
                cvss = cvss_json

            if isinstance(cvss, dict):
                return float(cvss.get("baseScore", 0) or 0)
        except Exception:
            logger.debug("Failed to extract cvss score", exc_info=True)

        return None

    def serve_vulns_data(self, handler) -> None:
        """Serve vulnerability data as JSON with server-side enrichment."""
        try:
            vulns = self.shared_data.db.get_all_vulns() or []

            cve_ids: List[str] = []
            for v in vulns:
                vid = (v.get("vuln_id") or "").strip()
                if vid.startswith("CVE-"):
                    cve_ids.append(vid)

            meta = {}
            if self.cve_enricher and cve_ids:
                meta = self.cve_enricher.get_bulk(cve_ids)

            for vuln in vulns:
                vid = (vuln.get("vuln_id") or "").strip()
                m = meta.get(vid)
                if m:
                    cvss = m.get("cvss") or {}
                    base_score = cvss.get("baseScore") if isinstance(cvss, dict) else (cvss or {}).get("baseScore")
                    base_sev = (cvss.get("baseSeverity") or "").lower() if isinstance(cvss, dict) else ""

                    vuln["severity"] = base_sev or vuln.get("severity") or "medium"
                    vuln["cvss_score"] = base_score if base_score is not None else vuln.get("cvss_score") or None
                    vuln["description"] = m.get("description") or vuln.get("description") or f"{vid} vulnerability detected"
                    vuln["affected_product"] = vuln.get("affected_product") or "Unknown"
                    vuln["is_kev"] = bool(m.get("is_kev"))
                    vuln["has_exploit"] = bool(m.get("exploits"))
                    vuln["epss"] = m.get("epss")
                    vuln["epss_percentile"] = m.get("epss_percentile")
                    vuln["references"] = m.get("references") or []
                else:
                    vuln.setdefault("severity", "medium")
                    vuln.setdefault("cvss_score", 5.0)
                    vuln["is_kev"] = False
                    vuln["has_exploit"] = False
                    vuln["epss"] = None
                    vuln["epss_percentile"] = None
                    vuln["references"] = []

            self._send_json(handler, 200, vulns, cache_max_age=10)

        except Exception as e:
            logger.exception("serve_vulns_data failed")
            self._send_json(handler, 500, {"error": str(e)})

    def serve_vulns_stats(self, handler) -> None:
        """Lightweight endpoint for statistics only."""
        try:
            stats = self.shared_data.db.query_one(
                """
                SELECT 
                    COUNT(*) as total,
                    COUNT(CASE WHEN is_active = 1 THEN 1 END) as active,
                    COUNT(DISTINCT mac_address) as hosts,
                    COUNT(DISTINCT CASE WHEN is_active = 1 THEN mac_address END) as active_hosts
                FROM vulnerabilities
                """
            )

            severity_counts = self.shared_data.db.query(
                """
                SELECT 
                    CASE 
                        WHEN vuln_id LIKE 'CVE-2024%' THEN 'high'
                        WHEN vuln_id LIKE 'CVE-2023%' THEN 'medium'
                        WHEN vuln_id LIKE 'CVE-2022%' THEN 'low'
                        ELSE 'medium'
                    END as severity,
                    COUNT(*) as count
                FROM vulnerabilities
                WHERE is_active = 1
                GROUP BY severity
                """
            )

            response = {
                "total": stats.get("total") if stats else 0,
                "active": stats.get("active") if stats else 0,
                "hosts": stats.get("hosts") if stats else 0,
                "active_hosts": stats.get("active_hosts") if stats else 0,
                "by_severity": {row["severity"]: row["count"] for row in severity_counts} if severity_counts else {},
            }

            self._send_json(handler, 200, response, cache_max_age=10)

        except Exception as e:
            logger.exception("serve_vulns_stats failed")
            self._send_json(handler, 500, {"error": str(e)})
