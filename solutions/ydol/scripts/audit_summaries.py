from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

from pypdf import PdfReader

from utils import DATA_DIR, OUTPUTS_DIR, cached_download, write_text


AUDITS: dict[str, str] = {
    "arrakis-modular-chainscurity.pdf": "https://cdn.prod.website-files.com/65d35b01a4034b72499019e8/66b4b186bfc8f14e17ea63ae_ChainSecurity_Spacing_Guild_Arrakis_Modular_audit.pdf",
    "arrakis-uniswap-v4-module-chainscurity.pdf": "https://cdn.prod.website-files.com/65d35b01a4034b72499019e8/677d4757ee5ee90cea211e90_ChainSecurity_Arrakis_Finance_Uniswap_V4_Module_audit.pdf",
}


def extract_text(pdf_path: Path) -> str:
    reader = PdfReader(str(pdf_path))
    return "\n".join((page.extract_text() or "") for page in reader.pages)


def parse_findings_overview(text: str) -> dict[str, int] | None:
    severities = ["Critical", "High", "Medium", "Low", "Informational"]
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    try:
        start = next(i for i, ln in enumerate(lines) if "Overview of the Findings" in ln)
    except StopIteration:
        return None
    window = lines[start : start + 140]
    counts: dict[str, int] = {}
    for sev in severities:
        idxs = [i for i, ln in enumerate(window) if ln == sev]
        if not idxs:
            continue
        idx = idxs[0]
        for j in range(idx + 1, min(idx + 12, len(window))):
            m = re.search(r"\b(\d+)\b", window[j])
            if m:
                counts[sev] = int(m.group(1))
                break
    return counts or None


def keyword_snippets(text: str, keywords: list[str], *, max_lines: int = 12) -> dict[str, list[str]]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    out: dict[str, list[str]] = {}
    for kw in keywords:
        matches = [ln for ln in lines if kw.lower() in ln.lower()]
        if matches:
            out[kw] = matches[:max_lines]
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Download Arrakis audit PDFs and extract key summary information.")
    parser.add_argument("--refresh", action="store_true", help="Re-download PDFs even if cached.")
    args = parser.parse_args()

    audits_dir = DATA_DIR / "audits"
    audits_dir.mkdir(parents=True, exist_ok=True)

    report_lines = ["# Audit summaries (generated)", "", f"As of: {datetime.utcnow().isoformat()}Z", ""]

    for filename, url in AUDITS.items():
        pdf_path = cached_download(url, audits_dir / filename, refresh=args.refresh)
        text = extract_text(pdf_path)
        txt_path = audits_dir / (pdf_path.stem + ".txt")
        txt_path.write_text(text, encoding="utf-8")

        counts = parse_findings_overview(text)
        report_lines.append(f"## {filename}")
        report_lines.append(f"- Source: {url}")
        report_lines.append(f"- Cached: `{pdf_path}`")
        report_lines.append(f"- Extracted text: `{txt_path}`")
        if counts:
            report_lines.append("- Findings overview:")
            for k, v in counts.items():
                report_lines.append(f"  - {k}: {v}")
        else:
            report_lines.append("- Findings overview: (not parsed)")

        snippets = keyword_snippets(
            text,
            keywords=[
                "beacon",
                "upgrade",
                "guardian",
                "owner",
                "timelock",
                "nft",
                "hook",
                "approval",
                "pause",
                "whitelist",
            ],
        )
        if snippets:
            report_lines.append("- Notable keyword hits (quick scan; review the PDF for full context):")
            for kw, lines in snippets.items():
                report_lines.append(f"  - `{kw}`:")
                for ln in lines:
                    report_lines.append(f"    - {ln}")
        report_lines.append("")

    out_report = OUTPUTS_DIR / "arrakis-audit-summary.md"
    write_text(out_report, "\n".join(report_lines).strip() + "\n")
    print(f"Wrote `{out_report}` and cached PDFs under `{audits_dir}`.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

