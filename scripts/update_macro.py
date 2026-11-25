"""Fetch public monthly US macro series from FRED and write rules/macro.json.

No API key required; uses FRED's public fredgraph CSV endpoint.
Thresholds match StockLab's M7 macro gate:
  - stress_std: HOUST 3M-YoY < 0%  | UNRATE > 12M mean + 0.1 Pp | INDPRO YoY < 0% | CPI YoY > 4.5%
  - stress_h5 : HOUST 3M-YoY < -5% | UNRATE > 12M mean + 0.1 Pp | INDPRO YoY < 0% | CPI YoY > 4.5%
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
from datetime import date
from pathlib import Path

FRED_URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"


def fetch_series(series_id: str) -> list[tuple[str, float]]:
    req = urllib.request.Request(
        FRED_URL.format(series=series_id),
        headers={"User-Agent": "stocklab-signal-macro/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        text = resp.read().decode("utf-8")
    out: list[tuple[str, float]] = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 2 or row[0].startswith("DATE") or row[0].startswith("observation"):
            continue
        if row[1] in ("", "."):
            continue
        out.append((row[0], float(row[1])))
    if len(out) < 24:
        raise RuntimeError(f"{series_id}: expected >= 24 monthly points, got {len(out)}")
    return out


def main() -> None:
    houst = fetch_series("HOUST")
    unrate = fetch_series("UNRATE")
    indpro = fetch_series("INDPRO")
    cpi = fetch_series("CPIAUCNS")

    # 3-month rolling average of HOUST vs 12 months earlier
    h_now = sum(v for _, v in houst[-3:]) / 3.0
    h_prev = sum(v for _, v in houst[-15:-12]) / 3.0
    houst_3m_yoy = h_now / h_prev - 1.0

    # UNRATE vs 12-month rolling average (inclusive of latest)
    u_now = unrate[-1][1]
    u_12m = sum(v for _, v in unrate[-12:]) / 12.0
    unemp_gap = u_now - u_12m

    # INDPRO YoY and CPI YoY
    indpro_yoy = indpro[-1][1] / indpro[-13][1] - 1.0
    cpi_yoy = cpi[-1][1] / cpi[-13][1] - 1.0

    base_stress = (unemp_gap > 0.1) or (indpro_yoy < 0.0) or (cpi_yoy > 0.045)
    stress_std = base_stress or (houst_3m_yoy < 0.0)
    stress_h5 = base_stress or (houst_3m_yoy < -0.05)

    payload = {
        "updated": date.today().isoformat(),
        "source": "FRED",
        "stress_h5": bool(stress_h5),
        "stress_std": bool(stress_std),
        "indicators": {
            "houst_3m_yoy": round(houst_3m_yoy, 4),
            "houst_date": houst[-1][0],
            "unrate": round(u_now, 2),
            "unemp_gap": round(unemp_gap, 3),
            "unrate_date": unrate[-1][0],
            "indpro_yoy": round(indpro_yoy, 4),
            "indpro_date": indpro[-1][0],
            "cpi_yoy": round(cpi_yoy, 4),
            "cpi_date": cpi[-1][0],
        },
    }
    target = Path(__file__).resolve().parents[1] / "rules" / "macro.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
