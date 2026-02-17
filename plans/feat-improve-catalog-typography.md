Improve catalog typography with curated editorial fonts from Google Fonts and Fontshare.

## Acceptance Criteria

- [ ] Download TTF/OTF font files into a `fonts/` directory in the project
- [ ] Add `@font-face` declarations in `catalog.css` pointing to local font files
- [ ] Update `main.py` to pass `FontConfiguration` to both `CSS()` and `write_pdf()`
- [ ] Apply heading font to: cover title, section divider headings, card titles
- [ ] Apply body/utility font to: metadata, genres, ratings, page numbers, captions
- [ ] Verify all 125 items still render correctly in the PDF
- [ ] Add `fonts/` directory to `.gitignore` (large binary files)
- [ ] Commit and push

## Font Pairing

**Heading / Display: Cormorant Garamond** (Google Fonts)
- Weights needed: Light (300), Regular (400), SemiBold (600)
- Download TTF from: https://fonts.google.com/specimen/Cormorant+Garamond
- Role: cover title, section dividers, card titles
- Why: High-contrast display Garamond with elegant Light weight. Tracked uppercase in Light 300 = Criterion Collection aesthetic.

**Body / Utility: General Sans** (Fontshare)
- Weights needed: Light (300), Regular (400), Medium (500)
- Download from: https://www.fontshare.com/fonts/general-sans
- Role: metadata, genres, ratings, duration, page numbers, cover stats
- Why: Rationalist neo-grotesque with compact proportions. Clean at 7pt, editorial but not cold.

## Technical Notes

- **WeasyPrint requires `FontConfiguration`** passed to both `CSS()` and `write_pdf()` — silent fallback if either is missing
- **Use TTF/OTF, not WOFF2** — WeasyPrint converts WOFF2 to TTF at render time, adding overhead
- **Use `base_url`** for relative path resolution in `@font-face` `url()` declarations
- **Font subsetting** is automatic — only used glyphs are embedded, keeping file size reasonable

## Implementation

### fonts/ directory structure

```
fonts/
  CormorantGaramond-Light.ttf
  CormorantGaramond-Regular.ttf
  CormorantGaramond-SemiBold.ttf
  GeneralSans-Light.ttf
  GeneralSans-Regular.ttf
  GeneralSans-Medium.ttf
```

### catalog.css — add @font-face blocks at top

```css
@font-face {
  font-family: 'Cormorant Garamond';
  src: url('../fonts/CormorantGaramond-Light.ttf') format('truetype');
  font-weight: 300;
  font-style: normal;
}
@font-face {
  font-family: 'Cormorant Garamond';
  src: url('../fonts/CormorantGaramond-Regular.ttf') format('truetype');
  font-weight: 400;
  font-style: normal;
}
@font-face {
  font-family: 'Cormorant Garamond';
  src: url('../fonts/CormorantGaramond-SemiBold.ttf') format('truetype');
  font-weight: 600;
  font-style: normal;
}
@font-face {
  font-family: 'General Sans';
  src: url('../fonts/GeneralSans-Light.ttf') format('truetype');
  font-weight: 300;
  font-style: normal;
}
@font-face {
  font-family: 'General Sans';
  src: url('../fonts/GeneralSans-Regular.ttf') format('truetype');
  font-weight: 400;
  font-style: normal;
}
@font-face {
  font-family: 'General Sans';
  src: url('../fonts/GeneralSans-Medium.ttf') format('truetype');
  font-weight: 500;
  font-style: normal;
}
```

### catalog.css — update font-family references

```css
/* Heading elements: cover h1, section-divider h2, card-title */
font-family: 'Cormorant Garamond', 'Helvetica Neue', serif;

/* Body/utility elements: body, card-meta, card-genres, card-detail, page numbers */
font-family: 'General Sans', 'Helvetica Neue', sans-serif;
```

### main.py — update generate_pdf()

```python
from weasyprint.text.fonts import FontConfiguration

def generate_pdf(...) -> None:
    font_config = FontConfiguration()
    # ...
    css = CSS(filename=TEMPLATE_DIR / "catalog.css", font_config=font_config)
    HTML(string=html_str, base_url=str(BASE_DIR)).write_pdf(
        target=str(output_path),
        stylesheets=[css],
        font_config=font_config,  # must pass to both CSS() and write_pdf()
        optimize_images=True,
        jpeg_quality=85,
        dpi=150,
    )
```

## References

- WeasyPrint font docs: https://doc.courtbouillon.org/weasyprint/latest/first_steps.html
- Cormorant Garamond: https://fonts.google.com/specimen/Cormorant+Garamond
- General Sans: https://www.fontshare.com/fonts/general-sans
- Using Google Fonts with WeasyPrint: https://tamarisk.it/using-google-fonts-with-weasyprint
