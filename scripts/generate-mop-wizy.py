#!/usr/bin/env python3
"""
generate-mop-wizy.py — Génère les MOPs HTML/DOCX depuis l'Excel source de vérité
en injectant les data-fields dans le template GrapeJS wizy courant.

Usage:
  python3 scripts/generate-mop-wizy.py --mop M0.20
  python3 scripts/generate-mop-wizy.py --mop all --output-dir /tmp/mops/

Source de vérité : onglet "Révision enrichie" — mop-incidents-alignment-review.xlsx
Template         : roles/mop-templates/files/mop-wizy-template.html
DOCX             : pandoc-api sur Sese-AI (via SSH)
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path
from datetime import datetime

try:
    import openpyxl
    from bs4 import BeautifulSoup
except ImportError:
    print("pip install openpyxl beautifulsoup4 lxml", file=sys.stderr)
    sys.exit(1)

REPO_ROOT   = Path(__file__).parent.parent
TEMPLATE    = REPO_ROOT / "roles/mop-templates/files/mop-wizy-template.html"
EXCEL_FILE  = REPO_ROOT / ".playwright-mcp/mop-incidents-alignment-review.xlsx"
SSH_KEY     = Path.home() / ".ssh/seko-vpn-deploy"
SSH_HOST    = "100.64.0.14"
SSH_PORT    = "804"
SSH_USER    = "mobuone"
DROP_BASE   = "https://drop.ewutelo.cloud/align"

# Colonnes Excel (0-indexé) → MOP
MOP_COLS = {"M0.20": 2, "M0.21": 3, "M0.22": 4, "M0.23": 5, "M0.24": 6}

# Lignes Excel (0-indexé) → clé de données brute
ROW_MAP = {
    4:  "doc_reference",
    5:  "doc_title",
    6:  "doc_resume",
    7:  "doc_verificateur",
    8:  "doc_date_vigueur",
    9:  "doc_date_revision",
    11: "rev1_date",
    12: "rev1_prepared_by",
    13: "rev1_verified_by",
    15: "equipements_couverts",
    17: "contacts_escalade",
    19: "s1_content",
    21: "s2_content",
    23: "s3_rex",           # Contexte terrain REX → s3_content
    24: "phase1",           # → s3_1_content (phase 1)
    25: "phase2",           # → s3_1_content (phase 2)
    26: "phase3",           # → s3_1_content (phase 3)
    27: "phase4",           # → s3_1_content (phase 4)
    29: "s4_content",
    31: "sources_kb",
}

# Champs fixes identiques pour tous les MOPs
FIXED = {
    "doc_type":          "MOP",
    "doc_confidentiality": "interne",
    "doc_owner":         "Service Technique",
    "doc_approbateur":   "Service ISO",
    "doc_scope":         "NOC Telehouse — Réseau OTN/OOB",
    "rev1_num":          "1.0",
    "rev1_description":  "Création initiale — base incidents terrain REX 2021-2025 + KB mop_kb",
    "rev1_approved_by":  "Service ISO",
    # Titres de sections
    "s1_title":   "Objet (quoi / pourquoi)",
    "s1_1_title": "Équipements couverts",
    "s1_1_1_title": "Sources de connaissance (KB)",
    "s2_title":   "Rôles et responsabilités (qui)",
    "s2_1_title": "Contacts d'escalade",
    "s2_1_1_title": "",
    "s3_title":   "Description du processus (comment)",
    "s3_1_title": "Phases d'intervention",
    "s3_1_1_title": "",
    "s4_title":   "Glossaire",
}

PHASE_LABELS = [
    "Phase 1 — Qualification",
    "Phase 2 — Diagnostic & Intervention",
    "Phase 3 — Résolution & Documentation",
    "Phase 4 — Validation & Clôture",
]


# ─── Formatage ────────────────────────────────────────────────────────────────

def fmt_date(val) -> str:
    if isinstance(val, datetime):
        return val.strftime("%d/%m/%Y")
    return str(val).strip() if val else ""


def fmt_lines(text: str) -> str:
    """Convertit un bloc texte multi-lignes en HTML <p> numérotés."""
    if not text:
        return ""
    parts = []
    for line in str(text).strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        m = re.match(r'^(\d+)\.\s+(.*)', line)
        if m:
            parts.append(
                f'<p style="margin:3px 0;">'
                f'<strong style="color:#1a3a5c;">{m.group(1)}.</strong>\u00a0{m.group(2)}</p>'
            )
        else:
            parts.append(f'<p style="margin:3px 0;">{line}</p>')
    return "\n".join(parts)


def fmt_plain(text: str) -> str:
    return str(text).strip() if text else ""


def build_phases_html(raw: dict) -> str:
    """Assemble les 4 phases en un bloc HTML structuré."""
    blocks = []
    for i, label in enumerate(PHASE_LABELS, 1):
        content = raw.get(f"phase{i}", "")
        if not content:
            continue
        blocks.append(
            f'<p style="margin:10px 0 4px;font-weight:700;color:#1a3a5c;'
            f'border-left:3px solid #1a3a5c;padding-left:8px;">'
            f'3.1.{i}\u00a0\u00a0{label}</p>'
        )
        blocks.append(fmt_lines(content))
    return "\n".join(blocks)


# ─── Données Excel ─────────────────────────────────────────────────────────────

def load_data(mop_id: str) -> dict:
    wb   = openpyxl.load_workbook(EXCEL_FILE, data_only=True)
    ws   = wb.worksheets[0]
    col  = MOP_COLS[mop_id]
    rows = list(ws.iter_rows(values_only=True))

    raw = {}
    for row_idx, key in ROW_MAP.items():
        raw[key] = rows[row_idx][col] if col < len(rows[row_idx]) else None

    d = dict(FIXED)

    # Métadonnées simples
    d["doc_reference"] = fmt_plain(raw["doc_reference"])
    if d["doc_reference"] and not d["doc_reference"].endswith("-V1"):
        d["doc_reference"] += "-V1"
    d["doc_title"]        = fmt_plain(raw["doc_title"])
    d["doc_resume"]       = fmt_lines(raw["doc_resume"])
    d["doc_verificateur"] = fmt_plain(raw["doc_verificateur"])
    d["doc_date_vigueur"] = fmt_date(raw["doc_date_vigueur"])
    d["doc_date_revision"]= fmt_date(raw["doc_date_revision"])

    # Révision
    d["rev1_date"]        = fmt_date(raw["rev1_date"])
    d["rev1_prepared_by"] = fmt_plain(raw["rev1_prepared_by"])
    d["rev1_verified_by"] = fmt_plain(raw["rev1_verified_by"])

    # SOPs citées → doc_associated
    all_phases = " ".join(str(raw.get(f"phase{i}", "")) for i in range(1, 5))
    sops = sorted(set(re.findall(r'\d{1,2}-SOP', all_phases)))
    d["doc_associated"] = " / ".join(sops) if sops else "—"

    # Section 1
    d["s1_content"]   = fmt_lines(raw["s1_content"])
    d["s1_1_content"] = fmt_lines(raw["equipements_couverts"])
    # Sources KB dans s1_1_1_title → on garde le titre, on met le contenu juste après
    d["_sources_kb"]  = fmt_lines(raw["sources_kb"])

    # Section 2
    d["s2_content"]    = fmt_lines(raw["s2_content"])
    d["s2_1_content"]  = fmt_lines(raw["contacts_escalade"])
    d["s2_1_1_content"]= ""   # pas de data-field dédié dans le template

    # Section 3 — nouveau template : s3_content + s3_1_content (phases)
    d["s3_content"]   = fmt_lines(raw["s3_rex"])
    d["s3_1_content"] = build_phases_html(raw)
    d["s3_1_1_content"] = ""

    # Section 4
    d["s4_content"] = fmt_lines(raw["s4_content"])

    return d


# ─── Injection dans le template ───────────────────────────────────────────────

def inject(soup, field: str, value: str, rich: bool = False):
    # data-field (zones de contenu) ET data-bind (header/titre GrapeJS)
    targets = soup.find_all(attrs={"data-field": field}) + \
              soup.find_all(attrs={"data-bind": field})
    for el in targets:
        el.clear()
        if rich and value:
            for child in list(BeautifulSoup(value, "html.parser").contents):
                el.append(child)
        elif value:
            el.string = value


SIMPLE_FIELDS = [
    "doc_reference", "doc_title", "doc_type", "doc_confidentiality",
    "doc_owner", "doc_verificateur", "doc_approbateur",
    "doc_date_vigueur", "doc_date_revision", "doc_scope", "doc_associated",
    "rev1_num", "rev1_date", "rev1_description",
    "rev1_prepared_by", "rev1_verified_by", "rev1_approved_by",
    "s1_title", "s1_1_title", "s1_1_1_title",
    "s2_title", "s2_1_title", "s2_1_1_title",
    "s3_title", "s3_1_title", "s3_1_1_title",
    "s4_title",
]

RICH_FIELDS = [
    "doc_resume",
    "s1_content", "s1_1_content",
    "s2_content", "s2_1_content",
    "s3_content", "s3_1_content",
    "s4_content",
]


def generate_html(mop_id: str) -> str:
    d    = load_data(mop_id)
    html = TEMPLATE.read_text(encoding="utf-8")
    soup = BeautifulSoup(html, "lxml")

    for f in SIMPLE_FIELDS:
        inject(soup, f, fmt_plain(d.get(f, "")), rich=False)

    for f in RICH_FIELDS:
        inject(soup, f, d.get(f, ""), rich=True)

    # Sources KB → insérer après le p contenant s1_1_1_title
    sources = d.get("_sources_kb", "")
    if sources:
        el = soup.find(attrs={"data-field": "s1_1_1_title"})
        if el:
            p = el.find_parent("p")
            if p:
                div = soup.new_tag("div", style="font-size:8.5pt;color:#555;margin:4px 0 0 4px;")
                for child in list(BeautifulSoup(sources, "html.parser").contents):
                    div.append(child)
                p.insert_after(div)

    # Sync data-toc-title attributes + générer TOC statique dans toc-container
    toc_entries = []
    for p in soup.find_all("p", attrs={"data-toc-level": True}):
        span = p.find(attrs={"data-field": True})
        if span:
            title = span.get_text(strip=True)
            if title:
                p["data-toc-title"] = title
                toc_entries.append({
                    "level": int(p.get("data-toc-level", 1)),
                    "anchor": p.get("id", ""),
                    "title": title,
                })

    toc_container = soup.find(id="toc-container")
    if toc_container and toc_entries:
        indent_map = {1: "0px", 2: "16px", 3: "32px"}
        color_map  = {1: "#1a3a5c", 2: "#2a5a8c", 3: "#555"}
        weight_map = {1: "700", 2: "600", 3: "400"}
        items_html = []
        for e in toc_entries:
            lvl = e["level"]
            items_html.append(
                f'<div style="margin:4px 0;padding-left:{indent_map.get(lvl,"0px")};">'
                f'<a href="#{e["anchor"]}" style="color:{color_map.get(lvl,"#333")};'
                f'font-weight:{weight_map.get(lvl,"400")};text-decoration:none;font-size:10pt;">'
                f'{e["title"]}</a></div>'
            )
        toc_html = "\n".join(items_html)
        for child in list(BeautifulSoup(toc_html, "html.parser").contents):
            toc_container.append(child)

    return str(soup)


# ─── PDF via Gotenberg Chromium (SSH) ────────────────────────────────────────

def ssh(cmd: str) -> str:
    result = subprocess.run(
        ["ssh", "-i", str(SSH_KEY), "-p", SSH_PORT,
         f"{SSH_USER}@{SSH_HOST}", cmd],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def generate_pdf(html_path: Path, mop_id: str) -> Path | None:
    """Envoie l'HTML à Gotenberg Chromium sur Sese-AI (même endpoint que mop-generate workflow)."""
    remote_html = f"/tmp/mop-{mop_id}.html"
    remote_pdf  = f"/tmp/mop-{mop_id}.pdf"
    local_pdf   = Path(f"/tmp/mop-{mop_id}.pdf")

    # SCP HTML → Sese-AI
    subprocess.run(
        ["scp", "-i", str(SSH_KEY), "-P", SSH_PORT,
         str(html_path), f"{SSH_USER}@{SSH_HOST}:{remote_html}"],
        check=True, capture_output=True
    )

    # Gotenberg Chromium — rendu CSS fidèle (web fonts, flexbox, grid)
    status = ssh(
        f"curl -s -X POST http://localhost:3000/forms/chromium/convert/html "
        f"-F 'files=@{remote_html};filename=index.html' "
        f"-o {remote_pdf} -w '%{{http_code}}'"
    )

    if not status.startswith("200"):
        print(f"  [WARN] Gotenberg HTTP {status}", file=sys.stderr)
        return None

    # Rapatrier le PDF
    subprocess.run(
        ["scp", "-i", str(SSH_KEY), "-P", SSH_PORT,
         f"{SSH_USER}@{SSH_HOST}:{remote_pdf}", str(local_pdf)],
        check=True, capture_output=True
    )
    return local_pdf


# ─── Upload drop.ewutelo.cloud ────────────────────────────────────────────────

def upload_drop(local_path: Path, filename: str):
    url = f"{DROP_BASE}/{filename}"
    ct  = "text/html" if filename.endswith(".html") else \
          "application/vnd.openxmlformats-officedocument.wordprocessingml.document" if filename.endswith(".docx") else \
          "application/pdf"
    result = subprocess.run(
        ["curl", "-s", "-w", "\nHTTP_%{http_code}", "-X", "PUT", url,
         "-H", f"Content-Type: {ct}", "--data-binary", f"@{local_path}"],
        capture_output=True, text=True
    )
    code = result.stdout.strip().split("\n")[-1]
    return code


# ─── Main ─────────────────────────────────────────────────────────────────────

def process_mop(mop_id: str, output_dir: Path):
    print(f"\n[{mop_id}] Génération HTML...", file=sys.stderr)
    html_str  = generate_html(mop_id)
    html_path = output_dir / f"mop-{mop_id}.html"
    html_path.write_text(html_str, encoding="utf-8")
    print(f"  HTML : {html_path} ({len(html_str):,} chars)", file=sys.stderr)

    # Upload HTML
    code = upload_drop(html_path, html_path.name)
    print(f"  drop HTML : {code}", file=sys.stderr)

    # PDF via Gotenberg Chromium
    print(f"[{mop_id}] Conversion PDF via Gotenberg Chromium...", file=sys.stderr)
    pdf_path = generate_pdf(html_path, mop_id)
    if pdf_path and pdf_path.exists():
        print(f"  PDF : {pdf_path} ({pdf_path.stat().st_size:,} B)", file=sys.stderr)
        code = upload_drop(pdf_path, pdf_path.name)
        print(f"  drop PDF : {code}", file=sys.stderr)
        return {
            "html": f"{DROP_BASE}/mop-{mop_id}.html",
            "pdf":  f"{DROP_BASE}/mop-{mop_id}.pdf",
        }
    else:
        print(f"  [WARN] PDF échoué pour {mop_id}", file=sys.stderr)
        return {"html": f"{DROP_BASE}/mop-{mop_id}.html"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mop", default="M0.20",
                        choices=list(MOP_COLS.keys()) + ["all"])
    parser.add_argument("--output-dir", default="/tmp/mops")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    mops = list(MOP_COLS.keys()) if args.mop == "all" else [args.mop]
    results = {}
    for mop_id in mops:
        results[mop_id] = process_mop(mop_id, out_dir)

    print("\n=== RÉSULTATS ===")
    for mop_id, urls in results.items():
        print(f"{mop_id}:")
        for fmt, url in urls.items():
            print(f"  {fmt}: {url}")


if __name__ == "__main__":
    main()
