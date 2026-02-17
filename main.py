#!/usr/bin/env python3
"""Generate a printable PDF catalog from a Plex Media Server library."""

from __future__ import annotations

import argparse
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader
from PIL import Image
from plexapi.server import PlexServer
from weasyprint import CSS, HTML
from weasyprint.text.fonts import FontConfiguration

BASE_DIR = Path(__file__).resolve().parent
POSTER_DIR = BASE_DIR / "posters"
TEMPLATE_DIR = BASE_DIR / "templates"


@dataclass
class CatalogItem:
    title: str
    year: int | None
    content_rating: str
    genres: list[str]
    rating_key: int
    thumb: str | None
    poster_path: str | None = None
    duration_minutes: int | None = None
    season_count: int | None = None
    episode_count: int | None = None


def connect(url: str, token: str) -> PlexServer:
    try:
        plex = PlexServer(url, token)
    except Exception as e:
        raise SystemExit(f"Failed to connect to Plex at {url}: {e}")
    print(f"Connected to {plex.friendlyName}")
    return plex


def extract_items(plex: PlexServer, section_name: str) -> list[CatalogItem]:
    try:
        section = plex.library.section(section_name)
    except Exception:
        available = [s.title for s in plex.library.sections()]
        raise SystemExit(
            f"Library section '{section_name}' not found. "
            f"Available sections: {', '.join(available)}"
        )

    items: list[CatalogItem] = []
    for item in section.all():
        ci = CatalogItem(
            title=item.title,
            year=item.year,
            content_rating=item.contentRating or "NR",
            genres=[g.tag for g in item.genres][:3],
            rating_key=item.ratingKey,
            thumb=item.thumb,
        )
        if section.type == "movie":
            ci.duration_minutes = item.duration // 60000 if item.duration else None
        elif section.type == "show":
            ci.season_count = item.childCount
            ci.episode_count = item.leafCount
        items.append(ci)

    return sorted(items, key=lambda x: (x.title or "").lower())


def download_posters(
    plex: PlexServer, items: list[CatalogItem], subdir: str, max_workers: int = 8
) -> None:
    poster_dir = POSTER_DIR / subdir
    poster_dir.mkdir(parents=True, exist_ok=True)
    total = len(items)
    session = requests.Session()

    def _download_one(i: int, item: CatalogItem) -> tuple[int, str, str]:
        if not item.thumb:
            return i, item.title, "no poster"

        safe_name = re.sub(r"[^\w\-() ]", "", item.title)
        safe_name = re.sub(r"\s+", " ", safe_name).strip()
        if not safe_name:
            safe_name = f"media_{item.rating_key}"
        year = f" ({item.year})" if item.year else ""
        filepath = poster_dir / f"{safe_name}{year}_{item.rating_key}.jpg"

        if filepath.exists():
            item.poster_path = str(filepath.resolve())
            return i, item.title, "cached"

        try:
            url = plex.url(item.thumb, includeToken=True)
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            filepath.write_bytes(resp.content)
            item.poster_path = str(filepath.resolve())
            return i, item.title, "downloaded"
        except Exception as e:
            safe_msg = str(e)
            if hasattr(plex, "_token") and plex._token:
                safe_msg = safe_msg.replace(plex._token, "[REDACTED]")
            return i, item.title, f"FAILED: {safe_msg}"

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_download_one, i, item): item
            for i, item in enumerate(items, 1)
        }
        for future in as_completed(futures):
            i, title, status = future.result()
            print(f"  [{i}/{total}] {title} -- {status}")


def resize_posters(items: list[CatalogItem], target_width: int = 250) -> None:
    target_height = int(target_width * 1.5)
    for item in items:
        if not item.poster_path:
            continue
        path = Path(item.poster_path)
        resized = path.with_stem(path.stem + "_sm")
        if resized.exists():
            item.poster_path = str(resized)
            continue
        try:
            with Image.open(path) as img:
                img.thumbnail((target_width, target_height), Image.LANCZOS)
                img.save(resized, "JPEG", quality=85)
            item.poster_path = str(resized)
        except Exception:
            pass  # keep original


def generate_pdf(
    movies: list[CatalogItem],
    shows: list[CatalogItem],
    output_path: Path,
    title: str,
) -> None:
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=True,
    )
    template = env.get_template("catalog.html.j2")

    html_str = template.render(
        movies=movies,
        shows=shows,
        catalog_title=title,
        generated_date=date.today().strftime("%Y"),
    )

    font_config = FontConfiguration()
    css = CSS(filename=TEMPLATE_DIR / "catalog.css", font_config=font_config)
    HTML(string=html_str, base_url=str(BASE_DIR)).write_pdf(
        target=str(output_path),
        stylesheets=[css],
        font_config=font_config,
        optimize_images=True,
        jpeg_quality=85,
        dpi=150,
    )
    print(f"PDF saved to {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a Plex library binder PDF."
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("PLEX_URL"),
        help="Plex server URL, e.g. http://192.168.1.100:32400 (or set PLEX_URL)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("PLEX_TOKEN"),
        help="Plex auth token (or set PLEX_TOKEN)",
    )
    parser.add_argument(
        "--title", default="Movie & TV Library", help="Catalog title"
    )
    parser.add_argument(
        "--output", default="output/catalog.pdf", help="Output PDF path"
    )
    args = parser.parse_args()

    if not args.url:
        parser.error("--url is required (or set PLEX_URL environment variable)")
    if not args.token:
        parser.error("--token is required (or set PLEX_TOKEN environment variable)")

    output_path = Path(args.output)
    if not output_path.is_absolute():
        output_path = BASE_DIR / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)

    plex = connect(args.url, args.token)

    print("Pulling movies...")
    movies = extract_items(plex, "Movies")
    print(f"  Found {len(movies)} movies")

    print("Pulling TV shows...")
    shows = extract_items(plex, "TV Shows")
    print(f"  Found {len(shows)} shows")

    print("Downloading movie posters...")
    download_posters(plex, movies, "movies")

    print("Downloading show posters...")
    download_posters(plex, shows, "shows")

    print("Resizing posters for print...")
    resize_posters(movies)
    resize_posters(shows)

    print("Generating PDF...")
    generate_pdf(movies, shows, output_path, args.title)
    print("Done!")


if __name__ == "__main__":
    main()
