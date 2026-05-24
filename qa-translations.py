#!/usr/bin/env python3
"""
Translation QA Agent — Parentee i18n coverage checker
Usage: python3 qa-translations.py [--fix]

Checks that every data-i18n / data-i18n-html key in index-4.html
has a non-empty, non-identical translation in all 6 language objects.
"""

import re
import sys
import json
from pathlib import Path

HTML_FILE = Path(__file__).parent / "index-4.html"
LANGUAGES = ["en", "es", "fr", "de", "pt", "tr"]
LANG_NAMES = {"en": "English", "es": "Español", "fr": "Français",
              "de": "Deutsch", "pt": "Português", "tr": "Türkçe"}

# ── ANSI colours ────────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
RESET  = "\033[0m"


def banner(text):
    w = 64
    print(f"\n{BOLD}{'═'*w}{RESET}")
    print(f"{BOLD}  {text}{RESET}")
    print(f"{BOLD}{'═'*w}{RESET}\n")


# ── Step 1: Extract all keys referenced in the HTML ─────────────────────────

def extract_html_keys(content: str) -> list[str]:
    """
    Find every data-i18n="key" and data-i18n-html="key" value.
    data-i18n="..." is matched exclusively (excludes data-i18n-html by design
    because the pattern requires the quote immediately after 'data-i18n').
    """
    plain  = re.findall(r'\bdata-i18n="([^"]+)"', content)
    html   = re.findall(r'\bdata-i18n-html="([^"]+)"', content)
    return sorted(set(plain + html))


# ── Step 2: Extract each language's translation table from the JS ────────────

def extract_i18n_block(content: str) -> str:
    """Pull out the raw text of the I18N = { ... } variable."""
    m = re.search(r'var\s+I18N\s*=\s*\{', content)
    if not m:
        sys.exit(f"{RED}ERROR: Could not find 'var I18N = {{' in {HTML_FILE.name}{RESET}")
    start = m.end() - 1   # opening brace position
    depth, i = 0, start
    while i < len(content):
        c = content[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return content[start : i + 1]
        i += 1
    sys.exit(f"{RED}ERROR: Unmatched brace in I18N object{RESET}")


def extract_lang_block(i18n_text: str, lang: str) -> str:
    """
    Extract the { ... } block for a specific language code.
    Handles nested braces inside value strings by tracking depth.
    """
    pat = re.compile(r'\b' + re.escape(lang) + r'\s*:\s*\{')
    m = pat.search(i18n_text)
    if not m:
        return ""
    start = m.end() - 1
    depth, i = 0, start
    while i < len(i18n_text):
        c = i18n_text[i]
        if c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i18n_text[start : i + 1]
        i += 1
    return ""


def extract_lang_kv(block: str) -> dict[str, str]:
    """
    Parse key:'value' and key:"value" pairs from a flat JS object block.
    Handles escaped quotes and multi-line strings crudely but reliably
    for the known shape of our I18N table.
    """
    result: dict[str, str] = {}
    # Strip outer braces
    inner = block[1:-1]
    # Match key: 'value' or key: "value" (allowing escaped quotes inside)
    pattern = re.compile(
        r"""([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")""",
        re.DOTALL,
    )
    for m in pattern.finditer(inner):
        key = m.group(1)
        value = m.group(2) if m.group(2) is not None else m.group(3)
        # Unescape backslash sequences
        value = value.replace("\\'", "'").replace('\\"', '"').replace("\\n", "\n")
        result[key] = value
    return result


# ── Step 3: Run all checks ───────────────────────────────────────────────────

def run_qa() -> int:
    content = HTML_FILE.read_text(encoding="utf-8")
    html_keys = extract_html_keys(content)
    i18n_block = extract_i18n_block(content)

    # Build per-language dicts
    lang_data: dict[str, dict[str, str]] = {}
    for lang in LANGUAGES:
        block = extract_lang_block(i18n_block, lang)
        lang_data[lang] = extract_lang_kv(block)

    en_kv = lang_data["en"]

    banner("Parentee — Translation QA Report")
    print(f"  File   : {HTML_FILE.name}")
    print(f"  Keys in HTML: {BOLD}{len(html_keys)}{RESET}")
    print(f"  Languages   : {', '.join(LANGUAGES)}\n")

    issues_total = 0

    for lang in LANGUAGES:
        kv        = lang_data[lang]
        missing   = [k for k in html_keys if k not in kv]
        empty     = [k for k in html_keys if kv.get(k, "").strip() == ""]
        # Same as English (suspect untranslated) — skip EN itself and keys
        # that are intentionally identical (numbers, proper nouns like "Parentee")
        same_as_en = []
        if lang != "en":
            same_as_en = [
                k for k in html_keys
                if k in kv and kv[k] == en_kv.get(k, "")
                # Ignore keys where English value is brand name / price / number only
                and not re.fullmatch(r'[\d$€£.,/\-% A-Z]+|Parentee', kv[k].strip())
            ]

        issues = len(missing) + len(empty) + len(same_as_en)
        issues_total += issues

        # Status icon
        if issues == 0:
            icon = f"{GREEN}✅{RESET}"
        elif missing or empty:
            icon = f"{RED}❌{RESET}"
        else:
            icon = f"{YELLOW}⚠️ {RESET}"

        covered   = len([k for k in html_keys if k in kv and kv[k].strip()])
        pct       = covered / len(html_keys) * 100 if html_keys else 100
        bar_fill  = int(pct / 5)
        bar       = "█" * bar_fill + "░" * (20 - bar_fill)
        lang_label = f"{BOLD}[{lang.upper()}]{RESET} {LANG_NAMES[lang]:<12}"

        print(f"  {icon} {lang_label}  {bar}  {pct:5.1f}%  ({covered}/{len(html_keys)} keys)")

        if missing:
            print(f"       {RED}MISSING {len(missing)} key(s):{RESET}")
            for k in missing:
                print(f"         {RED}✗ {k}{RESET}")

        if empty:
            print(f"       {RED}EMPTY {len(empty)} key(s):{RESET}")
            for k in empty:
                print(f"         {RED}✗ {k}{RESET}")

        if same_as_en:
            print(f"       {YELLOW}POSSIBLY UNTRANSLATED {len(same_as_en)} key(s) (identical to EN):{RESET}")
            for k in same_as_en:
                snippet = en_kv[k][:60].replace("\n", " ")
                print(f"         {YELLOW}? {k}  →  \"{snippet}…\"{RESET}" if len(en_kv[k]) > 60
                      else f"         {YELLOW}? {k}  →  \"{snippet}\"{RESET}")

        if issues == 0:
            pass  # already shown inline
        print()

    # ── Extra keys in any language not present in HTML ──────────────────────
    print(f"  {BOLD}── Orphaned keys (in JS but not in HTML) ──{RESET}")
    for lang in LANGUAGES:
        extras = sorted(set(lang_data[lang].keys()) - set(html_keys))
        if extras:
            print(f"     {YELLOW}[{lang.upper()}] {len(extras)} extra:{RESET} {', '.join(extras[:8])}"
                  + (f" … +{len(extras)-8}" if len(extras) > 8 else ""))
        else:
            print(f"     {GREEN}[{lang.upper()}] no orphaned keys{RESET}")
    print()

    # ── Summary ──────────────────────────────────────────────────────────────
    print(f"{BOLD}{'─'*64}{RESET}")
    if issues_total == 0:
        print(f"  {GREEN}{BOLD}ALL LANGUAGES PASS — {len(html_keys)} keys × {len(LANGUAGES)} langs ✓{RESET}")
    else:
        print(f"  {RED}{BOLD}{issues_total} issue(s) found across {len(LANGUAGES)} languages{RESET}")
    print(f"{BOLD}{'─'*64}{RESET}\n")

    return 0 if issues_total == 0 else 1


if __name__ == "__main__":
    sys.exit(run_qa())
