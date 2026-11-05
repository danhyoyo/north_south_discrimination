from __future__ import annotations

from pathlib import Path
import argparse
from urllib.error import URLError
from urllib.request import urlopen


BASE_URL = (
    "https://raw.githubusercontent.com/anhuynh219/"
    "Vietnamese-Regional-Discrimination-Detection/main/"
    "Dataset/Reginal%20Discrimination/Tiktok"
)
FILES = ("train.csv", "val.csv", "test.csv", "tiktok.csv")
OUTPUT_DIR = Path("data/source")
ALL_DATA_URL = (
    "https://raw.githubusercontent.com/anhuynh219/"
    "Vietnamese-Regional-Discrimination-Detection/main/"
    "Dataset/Reginal%20Discrimination/All%20Data/alldata.csv"
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Download published ViRDC CSV files")
    parser.add_argument("--include-all-sources", action="store_true", help="Also download aggregated TikTok, YouTube and Reddit data")
    args = parser.parse_args()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    downloads = [(filename, f"{BASE_URL}/{filename}") for filename in FILES]
    if args.include_all_sources:
        downloads.append(("alldata.csv", ALL_DATA_URL))
    for filename, url in downloads:
        target = OUTPUT_DIR / filename
        print(f"Downloading {filename} ...")
        try:
            with urlopen(url, timeout=30) as response:  # nosec B310 - fixed GitHub URL
                target.write_bytes(response.read())
        except URLError as exc:
            raise SystemExit(
                "Không tải được dataset từ GitHub. Hãy kiểm tra Internet/DNS rồi chạy lại.\n"
                f"URL: {url}\nLỗi: {exc}"
            ) from exc
        print(f"  -> {target} ({target.stat().st_size:,} bytes)")

    print("Dataset download complete.")


if __name__ == "__main__":
    main()
