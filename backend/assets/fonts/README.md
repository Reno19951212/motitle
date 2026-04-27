# Subtitle Fonts (`backend/assets/fonts/`)

Drop `.ttf` or `.otf` files into this directory and they will be:

1. **Burnt into video** by the renderer — the path is passed to FFmpeg
   `ass` filter via `:fontsdir=<this dir>` so libass can resolve any family
   referenced by `font_config.family` from these files.
2. **Loaded into the browser preview** via `@font-face` injected by
   `frontend/js/font-preview.js`, which fetches `/api/fonts` and serves
   each file from `/fonts/<filename>`. The live overlay therefore uses
   the **exact same glyphs** as the burnt-in output.

Without any font in this directory, both the renderer and the preview
fall back to system fonts (libass via fontconfig, browser via the
font-family fallback chain). Glyph drift between preview and burn-in is
likely in that mode — bundling the font here is the recommended setup.

## Recommended fonts (Traditional Chinese broadcast use)

| Family                 | Source                                           | License |
|------------------------|--------------------------------------------------|---------|
| **Noto Sans TC**       | https://fonts.google.com/noto/specimen/Noto+Sans+TC | SIL OFL |
| **Source Han Sans TC** | https://github.com/adobe-fonts/source-han-sans   | SIL OFL |
| **Noto Sans HK**       | https://fonts.google.com/noto/specimen/Noto+Sans+HK | SIL OFL |

Download the static `.ttf` (or `.otf`) variant — variable fonts work but
libass has had historical hiccups with them in some FFmpeg builds. Place
the file directly in this directory; subdirectories are not scanned.

## Optional: richer family-name extraction

By default the backend extracts the family name from each file's basename
(e.g. `NotoSansTC-Regular.ttf` → `NotoSansTC-Regular`). To resolve the
real family name embedded in the font's `name` table (e.g. `Noto Sans TC`),
install `fonttools` in the backend venv:

```bash
source venv/bin/activate
pip install fonttools
```

The next call to `/api/fonts` will return the canonical family name as
declared by the font itself.

## Restart required?

No — both the renderer and the `/api/fonts` endpoint scan the directory
on every call, so adding/removing fonts takes effect immediately. The
browser preview will pick up new fonts on the next page reload.
