#!/usr/bin/env python3
"""Save a book you purchased on taaghche.com as a PDF.

The script drives a real Chrome window with Selenium: you log in and open the
book yourself, then it screenshots every page of the reader and stitches the
screenshots into one PDF.

    python downloader.py                 # interactive, the common case
    python downloader.py --help          # all options
"""

import argparse
import base64
import io
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

from PIL import Image

try:  # optional: lossless PDF output
    import img2pdf
except ImportError:
    img2pdf = None
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    NoSuchDriverException,
    NoSuchElementException,
    SessionNotCreatedException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

SCRIPT_DIR = Path(__file__).resolve().parent

LOGIN_URL = "https://taaghche.com/login"
LIBRARY_URL = "https://taaghche.com/mylibrary?type=text"

# Element ids used by the Taaghche web reader. If the site changes, fix them here.
ID_CURRENT_PAGE = "pageNo"
ID_TOTAL_PAGES = "totalPages"
ID_PAGE_CANVAS = "canvas0"
ID_LOADERS = ("book-loading", "text-loading")  # spinners shown while the book re-flows
ID_NEXT = "___nextPage"
ID_PREV = "___prevPage"
MOBILE_SUFFIX = "Mobile"  # mobile layout ids are the desktop ids + this suffix

# Physical paper sizes in millimetres (portrait). The reader viewport and the
# PDF pages both follow the chosen paper, so a book comes out like a printed one.
PAPERS = {
    "a3": (297, 420), "a4": (210, 297), "a5": (148, 210), "a6": (105, 148),
    "b5": (176, 250), "letter": (215.9, 279.4),
}

FA_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")

DRIVER_HELP = """
Could not start Chrome with a matching chromedriver.

  * Make sure Google Chrome is installed and up to date.
  * Selenium normally downloads the right driver by itself. If that is blocked
    (for example a 403 error from storage.googleapis.com), download a driver
    that matches your Chrome version manually:
        https://googlechromelabs.github.io/chrome-for-testing/
    (mirror: https://registry.npmmirror.com/binary.html?path=chrome-for-testing/)
  * Then either put chromedriver(.exe) next to downloader.py, or point to it:
        python downloader.py --driver-path /path/to/chromedriver
    or set the CHROMEDRIVER_PATH environment variable.
"""


# --------------------------------------------------------------------------- #
# Command line
# --------------------------------------------------------------------------- #
def parse_args():
    p = argparse.ArgumentParser(
        description="Save a purchased Taaghche book as a PDF.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("-o", "--output", help="PDF file name (default: timestamp-based name)")
    p.add_argument("--driver-path", default=os.environ.get("CHROMEDRIVER_PATH"),
                   help="path to a chromedriver executable (default: auto-detect / download)")
    p.add_argument("--start", type=int, default=1, help="first page to save")
    p.add_argument("--end", type=int, default=None, help="last page to save (default: last page of the book)")
    p.add_argument("--delay", type=float, default=1.0,
                   help="seconds a page must stay unchanged before it is captured "
                        "(raise it if pages come out blank or half-drawn)")
    p.add_argument("--retries", type=int, default=5,
                   help="clicks to try per page turn before giving up (the reader ignores some clicks)")
    p.add_argument("--timeout", type=float, default=90,
                   help="seconds to wait for the reader to settle (re-flowing a book takes a while)")
    p.add_argument("--paper", default=None, choices=sorted(PAPERS) + ["native"],
                   help="paper size: the reader and the PDF pages get this shape "
                        "('native' keeps the reader as it is). If omitted you are asked at start")
    p.add_argument("--page-width", type=int, default=800, metavar="PX",
                   help="reader width in CSS px; the height follows the paper ratio. Smaller = "
                        "bigger text relative to the page")
    p.add_argument("--scale", type=float, default=3.0,
                   help="render scale (device pixel ratio); higher = sharper pages, bigger PDF")
    p.add_argument("--quality", type=int, default=95,
                   help="JPEG quality (1-100), only used if img2pdf is not installed")
    p.add_argument("--images-dir", help="keep the page PNGs in this folder (default: temporary, deleted)")
    p.add_argument("--profile", default=str(SCRIPT_DIR / ".chrome-profile"),
                   help="Chrome profile folder; keeps you logged in between runs")
    p.add_argument("--fresh", action="store_true", help="use a temporary profile (log in every time)")
    args = p.parse_args()

    if args.page_width < 300:
        p.error("--page-width must be at least 300")
    if args.start < 1:
        p.error("--start must be >= 1")
    if args.paper is None:
        args.paper = choose_paper()
    args.paper_mm = PAPERS.get(args.paper)
    return args


def choose_paper():
    """Ask which paper size to use (A5 if the user just presses Enter or input is not a terminal)."""
    options = ["a5", "a4", "a6", "b5", "letter", "native"]
    if not sys.stdin.isatty():
        return options[0]
    print("Choose the page size of the PDF:")
    for i, name in enumerate(options, 1):
        if name in PAPERS:
            w, h = PAPERS[name]
            label = f"{name.upper():7} {w:g} x {h:g} mm"
        else:
            label = "NATIVE  keep the reader's own shape"
        print(f"  {i}) {label}" + ("   [default]" if i == 1 else ""))
    while True:
        answer = input("Paper [1-6, Enter = A5] > ").strip().lower()
        if not answer:
            return options[0]
        if answer.isdigit() and 1 <= int(answer) <= len(options):
            return options[int(answer) - 1]
        if answer in options:
            return answer
        print("Please type a number from the list.")


# --------------------------------------------------------------------------- #
# Browser
# --------------------------------------------------------------------------- #
def find_local_driver(explicit):
    """Return a chromedriver path if one is given or sits next to the script."""
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            sys.exit(f"--driver-path / CHROMEDRIVER_PATH is not a file: {path}")
        return str(path)
    for name in ("chromedriver.exe", "chromedriver"):
        candidate = SCRIPT_DIR / name
        if candidate.is_file():
            return str(candidate)
    return None  # let Selenium Manager find or download one


def start_browser(args):
    options = webdriver.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    # Auto-accept "are you still there?"-style JS alerts instead of crashing.
    options.set_capability("unhandledPromptBehavior", "accept")
    if not args.fresh:
        options.add_argument(f"--user-data-dir={Path(args.profile).resolve()}")

    driver_path = find_local_driver(args.driver_path)
    service = Service(executable_path=driver_path) if driver_path else Service()

    try:
        driver = webdriver.Chrome(service=service, options=options)
    except NoSuchDriverException:
        sys.exit(DRIVER_HELP)
    except SessionNotCreatedException as e:
        sys.exit(f"Chrome refused to start:\n{e.msg}\n\nIf the message mentions a version mismatch, "
                 f"update Chrome or use a matching chromedriver.\n{DRIVER_HELP}")
    except WebDriverException as e:
        sys.exit(f"Could not start Chrome: {e.msg}\n"
                 f"If another Chrome window is using the profile '{args.profile}', close it "
                 f"or pass --fresh.\n{DRIVER_HELP}")

    return driver


# --------------------------------------------------------------------------- #
# Reader helpers
# --------------------------------------------------------------------------- #
STATE_JS = """
const text = id => { const e = document.getElementById(id); return e ? e.textContent.trim() : null; };
const shown = id => { const e = document.getElementById(id); return !!e && getComputedStyle(e).display !== 'none'; };
const c = document.getElementById(arguments[0]);
let sig = null, size = [0, 0, 0, 0];
if (c && c.width && c.height) {
  const r = c.getBoundingClientRect();
  size = [c.width, c.height, r.width, r.height];
  // cheap fingerprint of the drawn page (48x48 downsample) to notice content changes
  const t = document.createElement('canvas'); t.width = t.height = 48;
  const x = t.getContext('2d'); x.drawImage(c, 0, 0, 48, 48);
  const px = x.getImageData(0, 0, 48, 48).data; let h = 0;
  for (let i = 0; i < px.length; i++) h = (h * 31 + px[i]) | 0;
  sig = h;
}
return {page: text(arguments[1]), total: text(arguments[2]), size: size, sig: sig,
        busy: arguments[3].some(shown), mobile: document.body.classList.contains('mobile')};
"""


def to_int(text):
    digits = "".join(c for c in (text or "").translate(FA_DIGITS) if c.isdigit())
    return int(digits) if digits else None


def reader_state(driver):
    """Snapshot of the reader: current page, total pages, canvas size, spinner, content fingerprint."""
    s = driver.execute_script(STATE_JS, ID_PAGE_CANVAS, ID_CURRENT_PAGE, ID_TOTAL_PAGES, list(ID_LOADERS))
    s["page"], s["total"] = to_int(s["page"]), to_int(s["total"])
    return s


def wait_settled(driver, window, timeout):
    """Block until the reader is idle: no spinner, and nothing changed for `window` seconds.

    After a resize or a page turn the reader re-lays out / redraws for a while and
    ignores clicks meanwhile, so every action is followed by this wait.
    """
    deadline = time.time() + timeout
    last_key, since = None, None
    while time.time() < deadline:
        state = reader_state(driver)
        now = time.time()
        key = (state["page"], state["total"], tuple(state["size"]), state["sig"])
        if state["busy"] or not state["size"][0] or state["total"] is None:
            last_key, since = None, None
        elif key != last_key:
            last_key, since = key, now
        elif now - since >= window:
            return state
        time.sleep(0.25)
    raise TimeoutException("the reader did not settle (still loading?)")


def click_nav(driver, button_id):
    """Click next/prev, using the mobile button in mobile layout; fall back to a JS click
    if an overlay (e.g. the loading spinner) covers the button."""
    suffix = MOBILE_SUFFIX if driver.execute_script("return document.body.classList.contains('mobile')") else ""
    button = driver.find_element(By.ID, button_id + suffix)
    try:
        button.click()
    except (ElementClickInterceptedException, ElementNotInteractableException):
        driver.execute_script("arguments[0].click();", button)


def moved(before, after):
    """Did the page turn? Only the page *content* counts: the reader's page counter lags
    and jumps around (it can read 12, 12, 14 for three consecutive pages)."""
    return before["sig"] != after["sig"]


CLICK_WAIT = 2.5  # a real page turn shows up in ~0.3 s; after this the click is assumed lost


def step(driver, button_id, args, attempts=None, wait=CLICK_WAIT):
    """Turn one page.

    Roughly one click in five is silently ignored by the reader, so a click is only
    considered lost after CLICK_WAIT seconds without the page changing, then it is
    repeated (clicking sooner could turn two pages).
    Raises TimeoutException if the page never turns (e.g. first/last page).
    """
    before = reader_state(driver)
    for _ in range(attempts or args.retries):
        click_nav(driver, button_id)
        stop = time.time() + wait
        while time.time() < stop:
            time.sleep(0.25)
            if moved(before, reader_state(driver)):
                return wait_settled(driver, args.delay, args.timeout)
    raise TimeoutException("the page did not turn after clicking")


def goto_start(driver, start, args):
    """Go to page `start` (1-based).

    The reader's page counter is not trustworthy, so walk back until the reader stops
    turning pages (= first page), then walk forward counting our own clicks.
    """
    steps_back = 0
    for _ in range(2):  # the second round only runs if the counter says we are not at the start
        while True:
            try:
                step(driver, ID_PREV, args, attempts=6)
                steps_back += 1
                if steps_back % 10 == 0:
                    print(f"   ...rewinding to the first page ({steps_back} pages back so far)")
            except TimeoutException:
                break  # six clicks in a row did nothing: this is the first page
        page = reader_state(driver)["page"]
        if page is None or page <= 3:  # counter lags by a page or two, so allow a little slack
            break
        print(f"   the reader says page {page}, double-checking that this is the first page...")
    else:
        print("WARNING: could not confirm that the first page was reached; "
              "page numbers in this run may be off.")
    state = reader_state(driver)
    for _ in range(start - 1):
        state = step(driver, ID_NEXT, args)
    return state


def save_canvas(driver, canvas, path):
    """Save the page canvas as an RGB PNG.

    Reads the canvas' own pixels (full native resolution, no window-size or
    screenshot scaling involved); falls back to a screenshot if the browser
    refuses to export the canvas.
    """
    try:
        data_url = driver.execute_script("return arguments[0].toDataURL('image/png');", canvas)
        data = base64.b64decode(data_url.split(",", 1)[1])
    except (WebDriverException, IndexError, ValueError):
        data = canvas.screenshot_as_png
    with Image.open(io.BytesIO(data)) as im:
        if im.mode in ("RGBA", "LA", "P"):  # flatten transparency onto white
            im = im.convert("RGBA")
            page = Image.new("RGB", im.size, "white")
            page.paste(im, mask=im.getchannel("A"))
        else:
            page = im.convert("RGB")
        page.save(path, "PNG")
    return True


def apply_viewport(driver, width, height, scale):
    """Emulate a viewport of width x height CSS px at the given device pixel ratio.

    Done through Chrome's device emulation, so the size is not limited by the
    screen: a tall A4/A5-shaped page works even on a small monitor.
    """
    driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
        "width": width, "height": height, "deviceScaleFactor": scale, "mobile": False})


def settle_layout(driver, width, args):
    """Wait until the reader has re-laid itself out for a viewport `width` px wide.

    Right after a resize the old layout (and its canvas) is still there for a moment,
    and looks 'settled'. The page canvas fills the viewport width in the portrait
    layout, so wait until it does before trusting any measurement.
    """
    deadline = time.time() + max(args.timeout, 30)
    while True:
        time.sleep(0.5)
        state = wait_settled(driver, args.delay, args.timeout)
        if abs(state["size"][2] - width) <= 2 or time.time() > deadline:
            return state


def fit_paper(driver, args):
    """Size the reader so the *page canvas* has exactly the paper's proportions.

    The reader reserves space for its toolbars, so the viewport has to be a bit
    taller than the paper ratio suggests; measure that and correct it. Every
    change re-flows the whole book, so wait for it to settle each time.
    """
    width = args.page_width
    if not args.paper_mm:
        apply_viewport(driver, width, round(width * 1.414), args.scale)
        return settle_layout(driver, width, args)
    ratio = args.paper_mm[1] / args.paper_mm[0]
    first_guess = height = round(width * ratio)
    for _ in range(3):
        apply_viewport(driver, width, height, args.scale)
        state = settle_layout(driver, width, args)
        css_w, css_h = state["size"][2], state["size"][3]
        wanted = round(height + css_w * ratio - css_h)  # add the missing/excess canvas height
        if not first_guess * 0.8 < wanted < first_guess * 1.4:  # implausible: measurement glitch
            print(f"   (ignoring odd measurement: canvas {css_w:.0f}x{css_h:.0f})")
            height = first_guess + 128  # typical toolbar height
            apply_viewport(driver, width, height, args.scale)
            return settle_layout(driver, width, args)
        if abs(wanted - height) <= 2:
            break
        height = wanted
    return state


def capture_page(driver, path, args):
    """Save the current page canvas to `path`, retrying a few times."""
    last_error = None
    for attempt in range(1, args.retries + 1):
        try:
            canvas = driver.find_element(By.ID, ID_PAGE_CANVAS)
            if save_canvas(driver, canvas, path):
                return True
        except WebDriverException as e:
            last_error = e
        print(f"   retry {attempt}/{args.retries}...")
        time.sleep(args.delay)
    print(f"   giving up on this page ({type(last_error).__name__ if last_error else 'empty image'})")
    return False


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def build_pdf(image_paths, output, quality, paper_mm=None):
    """Write the PDF, one image per page.

    With paper_mm the pages get that physical size (e.g. A5), so the PDF opens
    and prints as a real A5/A4 document. Lossless (PNG embedded as-is) with
    img2pdf, otherwise JPEG via Pillow.
    """
    if img2pdf:
        kwargs = {}
        if paper_mm:
            size = tuple(img2pdf.mm_to_pt(v) for v in paper_mm)
            kwargs["layout_fun"] = img2pdf.get_layout_fun(size, fit=img2pdf.FitMode.into)
        with open(output, "wb") as f:
            f.write(img2pdf.convert([str(p) for p in image_paths], **kwargs))
        return

    print("Tip: `pip install img2pdf` gives a lossless, sharper PDF (using JPEG fallback).")

    def rest():  # one page at a time so big books don't exhaust memory
        for path in image_paths[1:]:
            with Image.open(path) as im:
                yield im.convert("RGB")

    with Image.open(image_paths[0]) as im:
        first = im.convert("RGB")
    dpi = first.width / (paper_mm[0] / 25.4) if paper_mm else 72
    first.save(output, "PDF", save_all=True, append_images=rest(), quality=quality,
               subsampling=0, resolution=dpi)


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main():
    args = parse_args()

    if args.images_dir:
        images_dir = Path(args.images_dir)
        images_dir.mkdir(parents=True, exist_ok=True)
        temp_dir = None
    else:
        temp_dir = tempfile.mkdtemp(prefix="taaghche-")
        images_dir = Path(temp_dir)

    output = Path(args.output) if args.output else Path(time.strftime("%Y-%m-%d-%H-%M-%S") + ".pdf")
    if output.suffix.lower() != ".pdf":
        output = output.with_suffix(".pdf")

    driver = start_browser(args)
    saved = []
    try:
        driver.get(LOGIN_URL)
        input("Log in to your Taaghche account in the browser window, then press Enter here > ")

        driver.get(LIBRARY_URL)
        input("Open the book's reading page and adjust the reader settings "
              "(font, theme...), then press Enter here > ")

        try:
            WebDriverWait(driver, args.timeout).until(
                EC.presence_of_element_located((By.ID, ID_PAGE_CANVAS)))
            wait_settled(driver, args.delay, args.timeout)
        except (TimeoutException, NoSuchElementException):
            sys.exit("Could not find the reader. Make sure the book is open on its "
                     "reading page (not the library) before pressing Enter.")

        # The book is reflowable text: changing the viewport changes the pagination,
        # so apply the paper shape first and only then read the page count.
        print(f"Setting up the reader for {args.paper.upper()} pages "
              f"(re-flowing the book, this can take up to a minute)...")
        fit_paper(driver, args)
        # The reader keeps the page *index* when it re-flows, so a position near the end
        # of the old layout can land past the end of the new one (a stuck, blank page).
        # Reloading makes it map the position into the new layout properly; the emulated
        # viewport survives the reload.
        driver.refresh()
        WebDriverWait(driver, args.timeout).until(
            EC.presence_of_element_located((By.ID, ID_PAGE_CANVAS)))
        time.sleep(1)
        state = wait_settled(driver, args.delay, args.timeout)
        total = state["total"]
        if not total:
            sys.exit("Could not read the page count from the reader.")
        native_w, native_h = state["size"][:2]
        paper_ratio = (args.paper_mm[1] / args.paper_mm[0]) if args.paper_mm else None
        print(f"Reader ready: {total} pages, page image {native_w}x{native_h}px "
              f"(height/width {native_h / native_w:.3f}"
              + (f", {args.paper.upper()} is {paper_ratio:.3f})" if paper_ratio else ")"))
        if paper_ratio and abs(native_h / native_w - paper_ratio) > 0.03 * paper_ratio:
            print(f"WARNING: the page shape ({native_h / native_w:.3f}) is not the {args.paper.upper()} "
                  f"shape ({paper_ratio:.3f}); pages will be letterboxed in the PDF. "
                  f"Try again, or use --paper native.")

        end = min(args.end or total, total)
        if args.start > end:
            sys.exit(f"--start ({args.start}) is after the last page ({end}).")

        print(f"Saving pages {args.start}-{end} of {total}. Don't touch the browser window; "
              f"press Ctrl+C to stop and keep what was saved.")
        print("Going to the first page...")
        state = goto_start(driver, args.start, args)

        missing = []
        previous_sig = None
        for page in range(args.start, end + 1):
            path = images_dir / f"{page:05d}.png"
            print(f"[{page}/{end}] saving {path.name}")
            if previous_sig is not None and state["sig"] == previous_sig:
                print("   warning: this page looks identical to the previous one")
            previous_sig = state["sig"]
            if capture_page(driver, path, args):
                saved.append(path)
            else:
                missing.append(page)
            if page < end:
                try:
                    state = step(driver, ID_NEXT, args)
                except TimeoutException as e:
                    print(f"The reader stopped turning pages after page {page} ({e}); stopping here.")
                    break

        if missing:
            print(f"WARNING: pages missing from the PDF: {missing}")
    except KeyboardInterrupt:
        print("\nInterrupted - saving the pages captured so far.")
    except (WebDriverException, ValueError) as e:
        print(f"\nStopped by an error ({type(e).__name__}) - saving the pages captured so far.")
        print(getattr(e, "msg", None) or e)
    finally:
        try:
            driver.quit()
        except WebDriverException:
            pass

    try:
        if not saved:
            print("No pages were captured, so no PDF was created.")
            return 1
        print(f"Building PDF from {len(saved)} pages...")
        build_pdf(saved, output, args.quality, args.paper_mm)
        print(f"Done! Book saved to: {output.resolve()}")
        return 0
    finally:
        if temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
