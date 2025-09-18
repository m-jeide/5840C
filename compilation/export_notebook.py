#!/usr/bin/env python3
"""Generate a printable engineering notebook (HTML + optional PDF)."""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import quote

from bs4 import BeautifulSoup
from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parent.parent
PAGES_DIR = REPO_ROOT / "pages"
TEMPLATE_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "compilation" / "output"
VEX_LOGO_PATH = "resources/home/vex_logo.png"
RESAMPLE_FILTER = Image.Resampling.LANCZOS if hasattr(Image, "Resampling") else Image.LANCZOS


def main(argv: Optional[Iterable[str]] = None) -> int:
  logging.basicConfig(level=os.environ.get("NOTEBOOK_LOG_LEVEL", "INFO"), format="[%(levelname)s] %(message)s")
  log = logging.getLogger("notebook")

  parser = argparse.ArgumentParser(description=__doc__)
  parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT_DIR,
                      help="Directory where notebook.html/pdf will be written (default: %(default)s)")
  parser.add_argument("--skip-pdf", action="store_true", help="Only emit HTML; skip PDF generation")
  parser.add_argument("--pdf-path", type=Path, help="Custom path for the generated PDF")
  parser.add_argument("--html-path", type=Path, help="Custom path for the generated HTML")
  args = parser.parse_args(list(argv) if argv is not None else None)

  output_dir = args.output.resolve()
  output_dir.mkdir(parents=True, exist_ok=True)

  manifest_path = PAGES_DIR / "manifest.json"
  if not manifest_path.exists():
    raise FileNotFoundError(f"Manifest not found at {manifest_path}")

  manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
  assets = AssetManager(output_dir, log)
  months = build_months(manifest, assets)
  home_content = extract_home_content(REPO_ROOT / "index.html", assets)

  rel_to_root = os.path.relpath(REPO_ROOT, output_dir)
  base_href = "./" if rel_to_root == "." else f"{Path(rel_to_root).as_posix()}/"

  env = Environment(
      loader=FileSystemLoader(TEMPLATE_DIR),
      autoescape=select_autoescape(['html', 'xml'])
  )
  template = env.get_template("notebook.html.jinja")

  toc = build_toc(months)
  log.info("Rendering notebook: %d months, %d total entries", len(months), sum(len(m["entries"]) for m in months))
  html_text = template.render(
      meta={"title": "Team 5840C Engineering Notebook"},
      base_href=base_href,
      vex_logo=encode_local_href(VEX_LOGO_PATH),
      home_content=home_content,
      months=months,
      toc=toc,
  )

  html_path = (args.html_path.resolve() if args.html_path else output_dir / "notebook.html")
  html_path.write_text(html_text, encoding="utf-8")
  log.info("Wrote HTML notebook to %s (%.1f KB)", html_path, html_path.stat().st_size / 1024)
  assets.report()

  if not args.skip_pdf:
    pdf_path = (args.pdf_path.resolve() if args.pdf_path else output_dir / "notebook.pdf")
    generate_pdf(html_path, pdf_path, log)

  return 0


def build_months(manifest: Dict[str, Any], assets: "AssetManager") -> List[Dict[str, Any]]:
  months: List[Dict[str, Any]] = []
  for month_name, entries_meta in manifest.items():
    entries_sorted = sorted(entries_meta, key=lambda meta: meta.get("date") or meta.get("id") or "")
    entry_objs: List[Dict[str, Any]] = []
    for entry_meta in entries_sorted:
      entry = load_entry(month_name, entry_meta, assets)
      entry_objs.append(entry)
    months.append({
        "name": month_name,
        "anchor": slugify(month_name),
        "entries": entry_objs,
    })
  return months


def build_toc(months: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
  toc = [
      {"title": "Title Page", "anchor": "title-page", "children": []},
      {"title": "Table of Contents", "anchor": "table-of-contents", "children": []},
      {"title": "Home", "anchor": "home", "children": []},
  ]
  for month in months:
    toc.append({
        "title": month["name"],
        "anchor": month["anchor"],
        "children": [
            {"title": entry["title"], "anchor": entry["anchor"]}
            for entry in month["entries"]
        ]
    })
  return toc


def extract_home_content(index_path: Path, assets: "AssetManager") -> str:
  html_text = index_path.read_text(encoding="utf-8")
  soup = BeautifulSoup(html_text, "html.parser")
  sections = []
  for selector in ("section#about", "section#links"):
    node = soup.select_one(selector)
    if node:
      for img in node.select("img[src]"):
        src = img.get("src")
        if not src or is_http(src):
          continue
        normalized = src.lstrip("./")
        fs_candidate = (index_path.parent / normalized).resolve()
        if not fs_candidate.exists():
          continue
        try:
          rel = fs_candidate.relative_to(REPO_ROOT)
        except ValueError:
          continue
        resolved = ResolvedSrc(
            href=encode_local_href(rel.as_posix()),
            fs_path=fs_candidate,
        )
        new_src = assets.prepare_image(resolved)
        if new_src:
          img["src"] = new_src
      sections.append(node.decode())
  return "\n".join(sections)


def load_entry(month_name: str, entry_meta: Dict[str, Any], assets: "AssetManager") -> Dict[str, Any]:
  entry_id = entry_meta.get("id")
  if not entry_id:
    raise ValueError(f"Entry in {month_name} missing 'id'")

  entry_path = PAGES_DIR / month_name / f"{entry_id}.json"
  if not entry_path.exists():
    raise FileNotFoundError(f"Entry file not found: {entry_path}")

  data = json.loads(entry_path.read_text(encoding="utf-8"))
  ctx = {"cls": month_name, "id": entry_id}
  return build_entry(data, ctx, assets)


def build_entry(page: Dict[str, Any], ctx: Dict[str, str], assets: "AssetManager") -> Dict[str, Any]:
  id_str = ctx["id"]
  file_base = strip_ext(Path(id_str).name)

  raw_title = first_truthy(
      page.get("title"),
      page.get("name"),
      id_str,
      file_base,
  )
  title = apply_placeholders(raw_title, page, ctx)

  brief = page.get("brief") if isinstance(page.get("brief"), list) else []
  elements = page.get("elements") if isinstance(page.get("elements"), list) else []

  processed_elements = [
      process_element(el, page, ctx, assets)
      for el in elements
  ]

  anchor = slugify(f"{ctx['cls']}-{title}-{page.get('date', id_str)}")

  return {
      "anchor": anchor,
      "title": title,
      "date": page.get("date", ""),
      "type": page.get("type", ""),
      "brief": brief,
      "elements": [el for el in processed_elements if el is not None],
  }


def process_element(el: Dict[str, Any], page: Dict[str, Any], ctx: Dict[str, str], assets: "AssetManager") -> Optional[Dict[str, Any]]:
  normalized = normalize_type(el.get("type"))

  if normalized in {"", None}:
    return None

  if normalized == "synopsis":
    title = el.get("title") or "Synopsis"
    text = el.get("content") or el.get("text") or ""
    return {
        "template": "text",
        "title": title,
        "html": rich_text(text),
    }

  if normalized == "designbrief":
    title = el.get("title") or "Design Brief"
    if isinstance(el.get("items"), list):
      content = "\n".join(rich_text(item) for item in el["items"])
    else:
      content = rich_text(el.get("content") or "")
    return {
        "template": "text",
        "title": title,
        "html": content,
    }

  if normalized == "notes":
    title = el.get("title") or el.get("label") or "Notes"
    return {
        "template": "text",
        "title": title,
        "html": rich_text(el.get("content") or ""),
    }

  if normalized in {"image", "images"}:
    title = el.get("title") or el.get("label") or "Images"
    items_data = []
    for item in normalize_items(el):
      resolved = resolve_src(item.get("src"), page, ctx)
      if not resolved.href:
        continue
      img_href = assets.prepare_image(resolved)
      if not img_href:
        continue
      items_data.append({
          "label": item.get("label") or "Image",
          "alt": item.get("alt") or item.get("label") or page.get("title") or ctx["id"],
          "src": img_href,
          "description": rich_text(item.get("description")) if item.get("description") else "",
      })
    if not items_data:
      return None
    return {
        "template": "images",
        "title": title,
        "items": items_data,
    }

  if normalized == "script":
    title = el.get("title") or el.get("label") or "Script"
    items_data = []
    for item in normalize_items(el):
      code_text = ""
      language = item.get("language") or guess_lang(item.get("src") or "")
      if item.get("code") is not None:
        code_text = str(item["code"])
      else:
        resolved = resolve_src(item.get("src"), page, ctx)
        if resolved.fs_path and resolved.fs_path.exists():
          code_text = resolved.fs_path.read_text(encoding="utf-8", errors="replace")
        else:
          code_text = f"// Missing script: {item.get('src')}"
      items_data.append({
          "label": item.get("label") or language or "Script",
          "language": language,
          "code": code_text,
      })
    return {
        "template": "script",
        "title": title,
        "items": items_data,
    }

  if normalized == "pdf":
    title = el.get("title") or el.get("label") or "PDF"
    items_data = []
    for item in normalize_items(el):
      resolved = resolve_src(item.get("src"), page, ctx)
      if not resolved.href:
        continue
      filename = Path(item.get("src") or "").name
      items_data.append({
          "label": item.get("label") or "PDF",
          "filename": filename,
          "src": resolved.href,
      })
    if not items_data:
      return None
    return {
        "template": "pdf",
        "title": title,
        "items": items_data,
    }

  if normalized == "video":
    title = el.get("title") or el.get("label") or "Video"
    items_data = []
    for item in normalize_items(el):
      resolved = resolve_src(item.get("src"), page, ctx)
      if not resolved.href:
        continue
      items_data.append({
          "label": item.get("label") or "Video",
          "src": resolved.href,
      })
    if not items_data:
      return None
    return {
        "template": "video",
        "title": title,
        "items": items_data,
    }

  return {
      "template": "unknown",
      "title": el.get("title") or el.get("label") or "Unknown Element",
  }


def rich_text(value: Any) -> str:
  text = html.escape(str(value or "").strip())

  def linkify(match: re.Match[str]) -> str:
    url = match.group(1)
    return f'<a href="{url}" class="inline-link">{url}</a>'

  url_pattern = re.compile(r"(https?://[^\s)]+)")
  text = url_pattern.sub(linkify, text)

  text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
  text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)

  paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
  if not paragraphs:
    return ""

  rendered = []
  for para in paragraphs:
    para = para.replace("\n", "<br>")
    rendered.append(f"<p>{para}</p>")
  return "\n".join(rendered)


def normalize_items(el: Dict[str, Any]) -> List[Dict[str, Any]]:
  items = el.get("items")
  if isinstance(items, list):
    return [item for item in items if isinstance(item, dict)]
  if el.get("src"):
    return [{"src": el.get("src"), "label": el.get("label") }]
  return []


def normalize_type(value: Any) -> str:
  return str(value or "").lower().replace(" ", "")


def strip_ext(name: str) -> str:
  return re.sub(r"\.[^.]+$", "", name)


def guess_lang(path: str) -> str:
  lower = (path or "").lower()
  mapping = {
      ".py": "python",
      ".js": "javascript",
      ".mjs": "javascript",
      ".cjs": "javascript",
      ".ts": "typescript",
      ".cpp": "cpp",
      ".cc": "cpp",
      ".cxx": "cpp",
      ".c": "c",
      ".java": "java",
      ".json": "json",
      ".md": "markdown",
      ".html": "html",
      ".css": "css",
  }
  for ext, lang in mapping.items():
    if lower.endswith(ext):
      return lang
  return ""


@dataclass
class ResolvedSrc:
  href: str
  fs_path: Optional[Path]


def ensure_rgb(image: Image.Image) -> Image.Image:
  if image.mode == "RGB":
    return image
  if image.mode in ("RGBA", "LA"):
    background = Image.new("RGB", image.size, (255, 255, 255))
    alpha = image.getchannel("A") if "A" in image.getbands() else image.split()[-1]
    background.paste(image, mask=alpha)
    return background
  if image.mode == "P":
    converted = image.convert("RGBA")
    return ensure_rgb(converted)
  return image.convert("RGB")


class AssetManager:
  def __init__(self, output_dir: Path, log: logging.Logger):
    self.output_dir = output_dir
    self.assets_dir = self.output_dir / "assets"
    self.assets_dir.mkdir(parents=True, exist_ok=True)
    self._image_cache: Dict[Path, str] = {}
    self._log = log
    self._total_original = 0
    self._total_output = 0
    self._images_processed = 0
    self._images_copied = 0

  def prepare_image(self, resolved: ResolvedSrc) -> str:
    if not resolved.href:
      return ""
    if not resolved.fs_path or not resolved.fs_path.exists():
      return resolved.href

    source = resolved.fs_path.resolve()
    cached = self._image_cache.get(source)
    if cached:
      return cached

    try:
      rel = source.relative_to(REPO_ROOT)
    except ValueError:
      return resolved.href

    suffix = source.suffix.lower()
    raster_exts = {".jpg", ".jpeg", ".png", ".bmp", ".gif", ".tif", ".tiff", ".webp"}

    if suffix not in raster_exts:
      target = self.assets_dir / rel
      target.parent.mkdir(parents=True, exist_ok=True)
      if not target.exists() or target.stat().st_mtime < source.stat().st_mtime:
        shutil.copy2(source, target)
        self._log.debug("Copied asset without resize: %s -> %s", source, target)
      self._images_copied += 1
      self._total_original += source.stat().st_size
      self._total_output += target.stat().st_size if target.exists() else source.stat().st_size
      href = encode_local_href(str(target.relative_to(REPO_ROOT)))
      self._image_cache[source] = href
      return href

    target_rel = rel.with_suffix(".jpg")
    target = self.assets_dir / target_rel
    target.parent.mkdir(parents=True, exist_ok=True)

    if target.exists() and target.stat().st_mtime >= source.stat().st_mtime:
      href = encode_local_href(str(target.relative_to(REPO_ROOT)))
      self._image_cache[source] = href
      return href

    try:
      with Image.open(source) as img:
        img.load()
        img = ensure_rgb(img)
        img.thumbnail((1600, 1200), RESAMPLE_FILTER)
        img.save(target, format="JPEG", quality=85, optimize=True)
        self._log.debug("Resized image %s -> %s (original %.1f KB, output %.1f KB)",
                        source, target, source.stat().st_size/1024, target.stat().st_size/1024)
        self._images_processed += 1
        self._total_original += source.stat().st_size
        self._total_output += target.stat().st_size
    except Exception as exc:
      self._log.warning("Failed to resize %s (%s); copying original", source, exc)
      shutil.copy2(source, target)
      self._images_copied += 1
      self._total_original += source.stat().st_size
      self._total_output += target.stat().st_size if target.exists() else source.stat().st_size

    href = encode_local_href(str(target.relative_to(REPO_ROOT)))
    self._image_cache[source] = href
    return href

  def report(self) -> None:
    if self._images_processed or self._images_copied:
      total_images = self._images_processed + self._images_copied
      delta = self._total_original - self._total_output
      self._log.info(
          "Processed %d image assets (%d resized, %d copied). Original %.1f MB -> Output %.1f MB (saved %.1f MB)",
          total_images,
          self._images_processed,
          self._images_copied,
          self._total_original / (1024 * 1024),
          self._total_output / (1024 * 1024),
          delta / (1024 * 1024),
      )
    else:
      self._log.info("No local image assets required processing.")


def resolve_src(src: Any, page: Dict[str, Any], ctx: Dict[str, str]) -> ResolvedSrc:
  raw = expand_template_path(src, page, ctx)
  if not raw:
    return ResolvedSrc(href="", fs_path=None)

  if is_http(raw):
    return ResolvedSrc(href=raw, fs_path=None)

  normalized = raw.lstrip("/")
  fs_path = (REPO_ROOT / normalized).resolve()
  try:
    fs_path.relative_to(REPO_ROOT)
  except ValueError:
    fs_path = None

  href = encode_local_href(normalized)
  return ResolvedSrc(href=href, fs_path=fs_path)


def expand_template_path(value: Any, page: Dict[str, Any], ctx: Dict[str, str]) -> str:
  if value is None:
    return ""
  raw = str(value)
  id_str = ctx.get("id", "")
  file_name = strip_ext(Path(id_str).name)
  templated_title = str(page.get("title") or id_str)
  templated_title = templated_title.replace("{file}", file_name)
  templated_title = templated_title.replace("{class}", ctx.get("cls", ""))
  templated_title = templated_title.replace("{id}", id_str)

  replacements = {
      "{title}": templated_title,
      "{class}": ctx.get("cls", ""),
      "{type}": page.get("type", ""),
      "{id}": id_str,
      "{file}": file_name,
  }

  for key, val in replacements.items():
    raw = raw.replace(key, val)
  return raw


def is_http(value: str) -> bool:
  return value.lower().startswith("http://") or value.lower().startswith("https://")


def encode_local_href(path: str) -> str:
  segments = [quote(seg) if seg else "" for seg in path.split("/")]
  return "/".join(segments)


def apply_placeholders(raw: str, page: Dict[str, Any], ctx: Dict[str, str]) -> str:
  result = str(raw)
  id_str = ctx.get("id", "")
  file_name = strip_ext(Path(id_str).name)
  replacements = {
      "{file}": file_name,
      "{class}": ctx.get("cls", ""),
      "{id}": id_str,
  }
  for key, val in replacements.items():
    result = result.replace(key, val)
  return result


def slugify(value: str) -> str:
  value = value.lower()
  value = re.sub(r"[^a-z0-9]+", "-", value)
  return value.strip('-') or "section"


def first_truthy(*values: Any) -> Any:
  for value in values:
    if value:
      return value
  return ""


def generate_pdf(html_path: Path, pdf_path: Path, log: logging.Logger) -> None:
  try:
    from playwright.sync_api import sync_playwright
  except ImportError as exc:
    raise RuntimeError("Playwright is not installed. Run 'pip install -r compilation/requirements.txt' and 'playwright install chromium'.") from exc

  html_uri = html_path.resolve().as_uri()
  log.info("Generating PDF from %s", html_uri)

  with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page()
    page.goto(html_uri, wait_until="load")
    page.pdf(path=str(pdf_path), print_background=True, format="Letter", prefer_css_page_size=True)
    browser.close()
  if pdf_path.exists():
    log.info("Wrote PDF to %s (%.1f MB)", pdf_path, pdf_path.stat().st_size / (1024 * 1024))


if __name__ == "__main__":
  raise SystemExit(main())
