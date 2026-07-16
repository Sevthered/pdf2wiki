"""Batch-scan a directory of book PDFs: extract a title guess + publication year from each PDF's
first ~10 pages (title/copyright page). Does NOT trust filenames as ground truth — only as a
fallback when the text layer is too thin to find a title line. Output is one record per book
(filename, page_count, title_guess, year_guess, confidence) for manual review — title/year
extraction from real books is too varied to fully automate reliably."""
import glob
import os
import re

YEAR_RE = re.compile(r'(?:19|20)\d{2}')
COPYRIGHT_RE = re.compile(r'copyright\s*(?:\xa9|\(c\)|©)?\s*(?:19|20)\d{2}', re.I)


def guess_title(pages_text: list[str], filename: str) -> tuple[str, str]:
    for pg in pages_text[:6]:
        lines = [l.strip() for l in pg.split("\n") if l.strip()]
        # a title line: reasonably long, mostly alphabetic, not all-caps boilerplate, not a URL/copyright
        for l in lines:
            if 8 <= len(l) <= 90 and not YEAR_RE.search(l) and "©" not in l and "http" not in l.lower() \
               and not l.lower().startswith(("copyright", "isbn", "www.", "all rights")):
                letters = sum(c.isalpha() for c in l)
                if letters / max(len(l), 1) > 0.6:
                    return l, "text"
    # fallback: filename, cleaned up
    base = os.path.splitext(os.path.basename(filename))[0]
    base = re.sub(r'^\d{10,13}-', '', base)          # strip leading ISBN
    base = re.sub(r'[_\-]+', ' ', base).strip()
    return base, "filename-fallback"


def guess_year(pages_text: list[str]) -> tuple[int | None, str]:
    years = []
    for pg in pages_text:
        for m in COPYRIGHT_RE.finditer(pg):
            y = YEAR_RE.search(m.group(0))
            if y:
                years.append(int(y.group(0)))
    if years:
        return max(years), "copyright-line"        # most recent copyright/reprint year on the page
    # fallback: any 4-digit year on the first 3 pages
    for pg in pages_text[:3]:
        ys = [int(y) for y in YEAR_RE.findall(pg)]
        if ys:
            return max(ys), "loose-year"
    return None, "none-found"


def scan_one(path: str) -> dict:
    import pymupdf  # lazy
    try:
        d = pymupdf.open(path)
    except Exception as e:
        return {"file": os.path.basename(path), "error": str(e)}
    npages = d.page_count
    pages_text = [d[i].get_text() for i in range(min(10, npages))]
    title, tconf = guess_title(pages_text, path)
    year, yconf = guess_year(pages_text)
    return {
        "file": os.path.basename(path), "pages": npages,
        "title": title, "title_conf": tconf,
        "year": year, "year_conf": yconf,
    }


def scan_dir(directory: str) -> list[dict]:
    return [scan_one(p) for p in sorted(glob.glob(os.path.join(directory, "*.pdf")))]
