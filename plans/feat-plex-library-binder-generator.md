# feat: Plex Library Binder Generator

A Python CLI tool that connects to a Plex Media Server, pulls the movie and TV show libraries, downloads poster artwork, and generates a print-ready PDF catalog formatted for a 3-hole-punch binder so kids can flip through and pick what to watch.

## Acceptance Criteria

- [ ] Connects to a Plex server using URL + token (CLI args or env vars)
- [ ] Retrieves all movies and TV shows with metadata (title, year, content rating, genres, duration/season count, poster)
- [ ] Downloads poster images with local caching (skips already-downloaded posters on re-run)
- [ ] Generates a US Letter PDF with 1" left margin (for 3-hole punch) and 0.75" other margins
- [ ] PDF contains: cover page, table of contents, "Movies" section divider, movie cards, "TV Shows" section divider, show cards
- [ ] Card layout: 2-column grid, each card has poster image + title + year + content rating + genres
- [ ] Movies sorted alphabetically by title; TV shows sorted alphabetically by title
- [ ] TV shows displayed at show level (not per-season), with season & episode counts on the card
- [ ] Missing posters render a placeholder (colored box with title text) instead of blank space
- [ ] Progress output to console during poster download and PDF generation
- [ ] Works on macOS (primary), should work on Linux

## Context

**Why**: Kids have access to a curated Plex server but can't independently browse and choose. A physical binder lets them flip through posters and titles to pick something, then ask a parent to put it on.

**Tech stack**:
- `python-plexapi` (v4.15+) — Plex server connection and metadata retrieval
- `Jinja2` + `WeasyPrint` — HTML/CSS templated PDF generation (flexbox layout, `@page` CSS for print)
- `requests` — poster image downloading
- `argparse` — CLI interface

**Key constraints**:
- WeasyPrint does NOT support CSS Grid — use flexbox with `flex-wrap: wrap` for the card grid
- Plex `thumb` attribute is a relative path; must construct full URL with `?X-Plex-Token=`
- Plex `duration` is in milliseconds (divide by 60000 for minutes)
- Poster images are typically 1000x1500 (2:3 ratio); 150 DPI in PDF is sufficient for print quality

## MVP

### Project structure

```
plex-catalog/
  main.py
  templates/
    catalog.html.j2
    catalog.css
  posters/
    movies/
    shows/
  output/
```

### `requirements.txt`

```
PlexAPI>=4.15.0
weasyprint>=62.0
Jinja2>=3.1.0
requests>=2.31.0
```

### `main.py`

```python
#!/usr/bin/env python3
"""Generate a printable PDF catalog from a Plex Media Server library."""

import argparse
import os
import re
from datetime import date
from pathlib import Path

import requests
from jinja2 import Environment, FileSystemLoader
from plexapi.server import PlexServer
from weasyprint import HTML, CSS


POSTER_DIR = Path("./posters")
OUTPUT_DIR = Path("./output")
TEMPLATE_DIR = Path("./templates")


def connect(url, token):
    plex = PlexServer(url, token)
    print(f"Connected to {plex.friendlyName}")
    return plex


def extract_movies(plex, section_name):
    items = []
    for m in plex.library.section(section_name).all():
        items.append({
            "title": m.title,
            "year": m.year,
            "content_rating": m.contentRating or "NR",
            "genres": [g.tag for g in m.genres][:3],
            "duration_minutes": m.duration // 60000 if m.duration else None,
            "thumb": m.thumb,
            "poster_path": None,
        })
    return sorted(items, key=lambda x: (x["title"] or "").lower())


def extract_shows(plex, section_name):
    items = []
    for s in plex.library.section(section_name).all():
        items.append({
            "title": s.title,
            "year": s.year,
            "content_rating": s.contentRating or "NR",
            "genres": [g.tag for g in s.genres][:3],
            "season_count": s.childCount,
            "episode_count": s.leafCount,
            "thumb": s.thumb,
            "poster_path": None,
        })
    return sorted(items, key=lambda x: (x["title"] or "").lower())


def download_posters(plex, items, subdir):
    poster_dir = POSTER_DIR / subdir
    poster_dir.mkdir(parents=True, exist_ok=True)
    total = len(items)

    for i, item in enumerate(items, 1):
        if not item["thumb"]:
            print(f"  [{i}/{total}] {item['title']} — no poster, skipping")
            continue

        safe_name = re.sub(r'[^\w\s\-()]', '', item["title"]).strip()
        year = f" ({item['year']})" if item.get("year") else ""
        filepath = poster_dir / f"{safe_name}{year}.jpg"

        if filepath.exists():
            item["poster_path"] = str(filepath.resolve())
            print(f"  [{i}/{total}] {item['title']} — cached")
            continue

        try:
            url = f"{plex._baseurl}{item['thumb']}?X-Plex-Token={plex._token}"
            resp = requests.get(url, stream=True, timeout=30)
            resp.raise_for_status()
            with open(filepath, "wb") as f:
                for chunk in resp.iter_content(8192):
                    f.write(chunk)
            item["poster_path"] = str(filepath.resolve())
            print(f"  [{i}/{total}] {item['title']} — downloaded")
        except Exception as e:
            print(f"  [{i}/{total}] {item['title']} — FAILED: {e}")

    return items


def generate_pdf(movies, shows, output_path, title):
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)))
    template = env.get_template("catalog.html.j2")

    html_str = template.render(
        movies=movies,
        shows=shows,
        catalog_title=title,
        generated_date=date.today().strftime("%B %d, %Y"),
    )

    css = CSS(filename=str(TEMPLATE_DIR / "catalog.css"))
    HTML(string=html_str, base_url=str(Path(".").resolve())).write_pdf(
        target=str(output_path),
        stylesheets=[css],
        optimize_images=True,
        jpeg_quality=85,
        dpi=150,
    )
    print(f"PDF saved to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="Generate a Plex library binder PDF.")
    parser.add_argument("--url", required=True, help="Plex server URL (e.g. http://192.168.1.100:32400)")
    parser.add_argument("--token", required=True, help="Plex auth token")
    parser.add_argument("--title", default="Our Movie & TV Library", help="Catalog title")
    parser.add_argument("--output", default="output/catalog.pdf", help="Output PDF path")
    parser.add_argument("--movies-section", default="Movies", help="Movies library section name")
    parser.add_argument("--shows-section", default="TV Shows", help="TV Shows library section name")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    plex = connect(args.url, args.token)

    print(f"Pulling movies from '{args.movies_section}'...")
    movies = extract_movies(plex, args.movies_section)
    print(f"  Found {len(movies)} movies")

    print(f"Pulling shows from '{args.shows_section}'...")
    shows = extract_shows(plex, args.shows_section)
    print(f"  Found {len(shows)} shows")

    print("Downloading movie posters...")
    movies = download_posters(plex, movies, "movies")

    print("Downloading show posters...")
    shows = download_posters(plex, shows, "shows")

    print("Generating PDF...")
    generate_pdf(movies, shows, args.output, args.title)
    print("Done!")


if __name__ == "__main__":
    main()
```

### `templates/catalog.html.j2`

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>{{ catalog_title }}</title>
</head>
<body>

  <!-- COVER -->
  <div class="cover">
    <h1>{{ catalog_title }}</h1>
    <p class="subtitle">{{ generated_date }}</p>
    <p class="stats">{{ movies|length }} Movies &bull; {{ shows|length }} TV Shows</p>
  </div>

  <!-- TABLE OF CONTENTS -->
  <div class="toc">
    <h2>What's Inside</h2>
    <ul>
      <li>Movies ({{ movies|length }})</li>
      <li>TV Shows ({{ shows|length }})</li>
    </ul>
  </div>

  <!-- MOVIES -->
  <div class="section-divider"><h2>Movies</h2><p>{{ movies|length }} titles</p></div>

  <div class="card-grid">
    {% for movie in movies %}
    <div class="card">
      <div class="card-poster">
        {% if movie.poster_path %}
        <img src="file://{{ movie.poster_path }}" alt="{{ movie.title }}">
        {% else %}
        <div class="no-poster"><span>{{ movie.title }}</span></div>
        {% endif %}
      </div>
      <div class="card-info">
        <h3>{{ movie.title }}</h3>
        <p class="meta">{{ movie.year or '' }} &bull; {{ movie.content_rating }}</p>
        <p class="genres">{{ movie.genres | join(', ') }}</p>
        {% if movie.duration_minutes %}<p class="runtime">{{ movie.duration_minutes }} min</p>{% endif %}
      </div>
    </div>
    {% endfor %}
  </div>

  <!-- TV SHOWS -->
  <div class="section-divider"><h2>TV Shows</h2><p>{{ shows|length }} titles</p></div>

  <div class="card-grid">
    {% for show in shows %}
    <div class="card">
      <div class="card-poster">
        {% if show.poster_path %}
        <img src="file://{{ show.poster_path }}" alt="{{ show.title }}">
        {% else %}
        <div class="no-poster"><span>{{ show.title }}</span></div>
        {% endif %}
      </div>
      <div class="card-info">
        <h3>{{ show.title }}</h3>
        <p class="meta">{{ show.year or '' }} &bull; {{ show.content_rating }}</p>
        <p class="genres">{{ show.genres | join(', ') }}</p>
        <p class="seasons">{{ show.season_count }} season{{ 's' if show.season_count != 1 else '' }} &bull; {{ show.episode_count }} episodes</p>
      </div>
    </div>
    {% endfor %}
  </div>

</body>
</html>
```

### `templates/catalog.css`

```css
@page {
  size: Letter;
  margin: 0.75in 0.75in 0.75in 1in; /* extra left for 3-hole punch */
  @bottom-center {
    content: counter(page);
    font-size: 9pt;
    color: #999;
  }
}
@page :first { @bottom-center { content: none; } }

* { margin: 0; padding: 0; box-sizing: border-box; }

body {
  font-family: 'Helvetica Neue', Helvetica, Arial, sans-serif;
  font-size: 10pt;
  line-height: 1.3;
  color: #222;
}

/* ── Cover ── */
.cover {
  page-break-after: always;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  text-align: center;
}
.cover h1 { font-size: 32pt; color: #e5a00d; margin-bottom: 16pt; }
.cover .subtitle { font-size: 12pt; color: #666; }
.cover .stats { font-size: 14pt; color: #444; margin-top: 8pt; }

/* ── TOC ── */
.toc {
  page-break-after: always;
  padding-top: 48pt;
}
.toc h2 {
  font-size: 20pt;
  border-bottom: 2pt solid #e5a00d;
  padding-bottom: 8pt;
  margin-bottom: 16pt;
}
.toc ul { list-style: none; }
.toc li { font-size: 14pt; margin-bottom: 8pt; }

/* ── Section Dividers ── */
.section-divider {
  page-break-before: always;
  page-break-after: always;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  text-align: center;
}
.section-divider h2 { font-size: 36pt; color: #e5a00d; }
.section-divider p { font-size: 14pt; color: #666; margin-top: 8pt; }

/* ── Card Grid (flexbox, not CSS grid — WeasyPrint compat) ── */
.card-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10pt;
}

.card {
  width: 48%;
  display: flex;
  flex-direction: row;
  page-break-inside: avoid;
  border: 0.5pt solid #ddd;
  border-radius: 4pt;
  padding: 6pt;
  background: #fafafa;
}

/* ── Poster ── */
.card-poster {
  flex-shrink: 0;
  width: 80pt;
  height: 120pt;
  border-radius: 3pt;
  overflow: hidden;
  background: #e0e0e0;
}
.card-poster img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.no-poster {
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 4pt;
  font-size: 8pt;
  color: #888;
  background: #d0d0d0;
}

/* ── Card Info ── */
.card-info {
  padding-left: 8pt;
  flex: 1;
  overflow: hidden;
}
.card-info h3 { font-size: 10pt; font-weight: bold; margin-bottom: 3pt; }
.card-info .meta { font-size: 8pt; color: #555; margin-bottom: 2pt; }
.card-info .genres { font-size: 7.5pt; color: #777; margin-bottom: 2pt; }
.card-info .runtime,
.card-info .seasons { font-size: 7.5pt; color: #777; }
```

## Usage

```bash
# Install deps (macOS)
brew install pango gdk-pixbuf libffi
pip install -r requirements.txt

# Generate the binder
python main.py \
  --url http://YOUR_PLEX_IP:32400 \
  --token YOUR_PLEX_TOKEN \
  --title "Our Movie & TV Library"

# Output: output/catalog.pdf — print it and put it in a binder!
```

## References

- [python-plexapi docs](https://python-plexapi.readthedocs.io/en/latest/)
- [WeasyPrint docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps) — note: no CSS Grid support, use flexbox
- [Finding your Plex token](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)
- [Plex Forum thread requesting this exact feature](https://forums.plex.tv/t/can-you-export-or-print-pdf-a-list-of-library-contents/275856)
