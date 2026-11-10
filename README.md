# Taaghche downloader

**Save books you purchased on [taaghche.com](https://taaghche.com) as a PDF.**

A small Python script that drives a real Chrome window with Selenium. You log in and open your book; the script then screenshots every page of the web reader and stitches the screenshots into a single PDF.

> For personal backups of books you have legitimately bought. Respect the publishers' and authors' copyright; don't redistribute the result.

## Features

- Works on Windows, macOS and Linux
- Finds / downloads the right `chromedriver` automatically (or use your own)
- Stays logged in between runs (dedicated Chrome profile)
- Asks which paper size you want when it starts (A5, A4, A6, B5, Letter or the reader's own shape)
- Waits for the reader instead of using blind sleeps, and retries page turns the reader ignores
- Ctrl+C or a crash still gives you a PDF of the pages captured so far
- Sharp output: reads the reader's own canvas pixels at 3x scale and embeds them losslessly (no JPEG re-compression)
- Paper-shaped output: the reader is laid out in the proportions of your chosen paper and the PDF pages have that real physical size
- Low memory use, even for books with hundreds of pages
- Save only a page range, choose the output name and resolution

## Requirements

- Python 3.8+
- Google Chrome (up to date)

## Installation

```bash
git clone https://github.com/hctilg/taaghche-dl.git
cd taaghche-dl
pip install -r requirements.txt
```

## Usage

```bash
python downloader.py
```

1. **Choose the paper size** from the menu (just press Enter for A5). Skip the menu with `--paper a4`.
2. A Chrome window opens on the Taaghche login page. Log in, then press **Enter** in the terminal.
3. The library opens. Open the book's **reading page** and set the reader the way you want the PDF to look (font, size, theme), then press **Enter** again.
4. The script re-flows the book to the paper's shape (up to a minute), rewinds to the first page, and saves every page. Don't touch the browser window while it runs.
5. When it finishes, the PDF is written to the current folder and its path is printed.

Your login is remembered in `.chrome-profile/`, so next time you can skip straight to step 3.

> **Page count changes.** Taaghche books are reflowable text, so the number of pages depends on the paper shape and the reader's font size. A book that shows 33 pages in your normal window may come out as 25 A5 pages; that is expected. `--start`/`--end` refer to the new numbering that the script prints.
>
> **Your reading position moves.** The script turns the pages of your real reader, so the book's "last read" bookmark ends up at the last page it visited.

### Options

| Option | Default | Description |
| --- | --- | --- |
| `-o, --output NAME` | timestamp | Output PDF name |
| `--start N` / `--end N` | 1 / last page | Save only a range of pages |
| `--paper SIZE` | asked at start | Page shape and PDF page size: `a3`, `a4`, `a5`, `a6`, `b5`, `letter`, or `native` (keep the reader's own shape) |
| `--page-width PX` | `800` | Reader width in CSS px; the height follows the paper ratio. **Smaller = bigger text on the page** (text size is the reader's font size relative to this width). Not limited by your screen |
| `--scale X` | `3` | Render scale (device pixel ratio). Higher = sharper pages and a bigger PDF |
| `--delay SECONDS` | `1.0` | How long a page must stay unchanged before it is captured. Raise it if pages come out blank or half-drawn |
| `--retries N` | `5` | Clicks tried per page turn before giving up (the reader ignores about one click in five) |
| `--timeout SECONDS` | `90` | How long to wait for the reader to settle (re-flowing a book is slow) |
| `--quality N` | `95` | JPEG quality (1-100); only used if `img2pdf` isn't installed |
| `--images-dir DIR` | temp, deleted | Keep the page PNGs in this folder |
| `--driver-path PATH` | auto | Path to a `chromedriver` executable (or set `CHROMEDRIVER_PATH`) |
| `--profile DIR` | `.chrome-profile` | Chrome profile folder used to stay logged in |
| `--fresh` | off | Use a throwaway profile (log in every time) |

Examples:

```bash
python downloader.py -o "my-book.pdf"
python downloader.py --paper a4
python downloader.py --start 10 --end 40 --delay 2.5
python downloader.py --driver-path "C:\tools\chromedriver.exe"
```

## Troubleshooting

**`Unable to obtain driver for chrome` / `403 Forbidden` from `storage.googleapis.com`**
Selenium couldn't download a driver (common when Google's download host is blocked in your region, even with a VPN, because Selenium may not use your proxy). Download the `chromedriver` that matches your Chrome version manually from the [Chrome for Testing](https://googlechromelabs.github.io/chrome-for-testing/) page or a [mirror](https://registry.npmmirror.com/binary.html?path=chrome-for-testing/), then either:

- put `chromedriver` (`chromedriver.exe` on Windows) next to `downloader.py`, or
- pass `--driver-path /path/to/chromedriver`, or set the `CHROMEDRIVER_PATH` environment variable.

Check your Chrome version at `chrome://version`; the driver's major version must match.

**`session not created: This version of ChromeDriver only supports Chrome version X`**
Driver and Chrome versions differ. Update Chrome or download the matching driver.

**Chrome fails to start / "user data directory is already in use"**
Another Chrome window is using the same profile folder. Close it, or run with `--fresh`.

**"Could not find the reader"**
You pressed Enter before the book's reading page was open. Open the book first, then press Enter.

**The first pages are missing / it starts in the middle of the book**
The script rewinds by turning pages back until the reader stops moving. If it prints a warning that it could not confirm the first page, run it again; if it keeps happening, pass a larger `--retries`.

**Text looks blurry / low quality**
Make sure `img2pdf` is installed (`pip install -r requirements.txt`); without it the PDF falls back to JPEG. Then raise `--scale` (e.g. `--scale 3`) and/or increase the font size in the reader settings before pressing Enter. At start the script prints the canvas' native resolution, which is the most detail the reader provides.

**Text is too small / too big on the page**
Text size is the reader's font size relative to the page width. Make it bigger by lowering `--page-width` (e.g. `--page-width 650`) or by increasing the font in the reader settings before pressing Enter; do the opposite to make it smaller. Defaults are tuned so A5 text prints at a normal book size.

**The page shape is not the paper shape**
The script prints a warning when the reader's page isn't within 3% of the paper proportions (then PDF pages get thin white bars). Run it again, or use `--paper native`.

**Blank or half-rendered pages**
Raise `--delay` (e.g. `--delay 3`).

**Some pages are reported missing, or "looks identical to the previous one"**
Re-run just those pages with `--start`/`--end`, or raise `--delay`.

**The reader stopped working after a Taaghche update**
The element ids the script relies on are listed in constants at the top of `downloader.py`; update them there.

## How it works (for the curious)

The reader is a canvas that is redrawn for every page. The script changes the browser's emulated viewport to the paper's proportions (so it works on any screen), waits for the reader to re-flow, reloads so the reader maps your position into the new layout, rewinds to page 1, then for each page reads the canvas' native pixels and clicks "next". Because the reader's own page counter is unreliable, page turns are detected from the page *content* changing.

## License

See [LICENSE](LICENSE).
