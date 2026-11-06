#!/usr/bin/env python3
"""
Batch convert SVG / EPS files in a folder using Inkscape.

1. Asks for a folder path
2. Asks for the output format (eps, svg, jpg, png)
3. Runs: inkscape input.svg --export-filename=output.<ext>   for each file
4. Saves everything in a new sub-folder inside the same folder

Shows an overall progress bar plus a live timer for the current file.
Files that take longer than the timeout are skipped (and listed at the end).
"""

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

INPUT_EXTS = {".svg", ".eps"}
FORMATS = ["eps", "svg", "jpg", "png"]
DEFAULT_TIMEOUT = 120  # seconds per file


def check_inkscape():
    if shutil.which("inkscape") is None:
        sys.exit("Error: 'inkscape' was not found in PATH. Install it or add it to PATH.")


def status_line(done, total, name, elapsed, width=24):
    filled = int(width * done / total) if total else width
    bar = "█" * filled + "░" * (width - filled)
    pct = int(100 * done / total) if total else 100
    line = f"[{bar}] {pct:3d}% ({done}/{total}) {name} {elapsed:.0f}s"
    cols = shutil.get_terminal_size((100, 20)).columns - 1
    sys.stdout.write("\r" + line[:cols].ljust(cols))
    sys.stdout.flush()


def run_inkscape(src: Path, dst: Path, done, total, timeout):
    """Run inkscape, updating the progress line. Returns (ok, error_message)."""
    cmd = ["inkscape", str(src), f"--export-filename={dst}"]
    start = time.time()
    with tempfile.TemporaryFile(mode="w+") as err_file:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err_file, text=True)
        try:
            while proc.poll() is None:
                elapsed = time.time() - start
                if elapsed > timeout:
                    proc.kill()
                    proc.wait()
                    return False, f"timed out after {timeout}s"
                status_line(done, total, src.name, elapsed)
                time.sleep(0.2)
        except KeyboardInterrupt:
            proc.kill()
            proc.wait()
            raise
        err_file.seek(0)
        err = err_file.read().strip()
    if proc.returncode != 0 or not dst.exists():
        return False, err[:200] or f"exit code {proc.returncode}"
    return True, ""


def png_to_jpg(png_path: Path, jpg_path: Path):
    """Inkscape cannot export JPG directly, so PNG -> JPG via Pillow."""
    from PIL import Image

    img = Image.open(png_path)
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))  # white background
        bg.paste(img, mask=img.split()[-1])
        img = bg
    else:
        img = img.convert("RGB")
    img.save(jpg_path, "JPEG", quality=95)


def main():
    check_inkscape()

    # 1. Folder path
    folder = Path(input("Enter the folder path: ").strip().strip('"').strip("'")).expanduser()
    if not folder.is_dir():
        sys.exit(f"Error: '{folder}' is not a valid folder.")

    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in INPUT_EXTS)
    if not files:
        sys.exit("No .svg or .eps files found in that folder.")
    print(f"Found {len(files)} file(s).")

    # 2. Format
    fmt = ""
    while fmt not in FORMATS:
        fmt = input(f"Output format ({', '.join(FORMATS)}): ").strip().lower().lstrip(".")
        if fmt == "jpeg":
            fmt = "jpg"

    if fmt == "jpg":
        try:
            import PIL  # noqa: F401
        except ImportError:
            sys.exit("JPG needs Pillow. Install it with:  pip install pillow")

    t = input(f"Timeout per file in seconds [{DEFAULT_TIMEOUT}]: ").strip()
    timeout = int(t) if t.isdigit() and int(t) > 0 else DEFAULT_TIMEOUT

    # 3. Output folder (created inside the same folder)
    out_dir = folder / f"converted_{fmt}"
    out_dir.mkdir(exist_ok=True)

    # 4. Convert loop
    total = len(files)
    ok, failed = 0, []
    try:
        for i, src in enumerate(files):
            dst = out_dir / f"{src.stem}.{fmt}"
            status_line(i, total, src.name, 0)

            if fmt == "jpg":
                with tempfile.TemporaryDirectory() as tmp:
                    tmp_png = Path(tmp) / f"{src.stem}.png"
                    success, err = run_inkscape(src, tmp_png, i, total, timeout)
                    if success:
                        png_to_jpg(tmp_png, dst)
            else:
                success, err = run_inkscape(src, dst, i, total, timeout)

            if success:
                ok += 1
            else:
                failed.append((src.name, err))
                if dst.exists():
                    dst.unlink()  # remove partial output
    except KeyboardInterrupt:
        print("\n\nCancelled by user.")

    status_line(ok + len(failed), total, "done", 0)
    print(f"\n\nDone. {ok} converted, {len(failed)} failed/skipped.")
    print(f"Output folder: {out_dir}")
    for name, err in failed:
        print(f"  SKIPPED: {name}  ({err})")


if __name__ == "__main__":
    main()
