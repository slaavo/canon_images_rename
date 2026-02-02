# Photo Organizer

Fast batch photo organization by EXIF date.

## Features

- **Speed**: Single exiftool call + multithreaded file moves (10-50x faster than sequential)
- **Formats**: CR3, DNG, ARW, NEF, ORF, RAF, RW2, JPG, JPEG
- **Folder structure**: `YYYY_MM_DD/` with `!orig/` and `!jpg/` subfolders
- **Naming**: `YYYY_MM_DD_HHMMSS_original_name.extension`
- **Safety**: dry-run mode, duplicate handling, graceful Ctrl+C

## Requirements

- Python 3.10+
- exiftool

```bash
# Ubuntu/Debian
sudo apt install libimage-exiftool-perl

# macOS
brew install exiftool

# Windows
# Download from https://exiftool.org
```

## Usage

```bash
# Basic — organize current folder
./rename_and_move_files.py

# Specify input folder
./rename_and_move_files.py /path/to/photos

# Different output folder
./rename_and_move_files.py -o /output /path/to/photos

# Dry run — preview changes without moving files
./rename_and_move_files.py -d /path/to/photos

# Move RAW files to !orig (by default only JPEGs go to !orig)
./rename_and_move_files.py -r /path/to/photos

# More workers (faster on NVMe)
./rename_and_move_files.py -w 16 /path/to/photos

# Fewer workers (safer on HDD)
./rename_and_move_files.py -w 1 /path/to/photos

# Verbose — detailed logs
./rename_and_move_files.py -v /path/to/photos
```

## Options

| Option | Description |
|--------|-------------|
| `-o, --output DIR` | Output folder (default: same as input) |
| `-d, --dry-run` | Preview changes without moving files |
| `-r, --raw-subfolder` | Move RAW files to `!orig/` (by default only JPEGs) |
| `-w, --workers N` | Number of parallel workers (default: 8, range: 1-64) |
| `-v, --verbose` | Detailed log output |

## Output structure

```
/output/
├── 2024_01_15/
│   ├── !jpg/                    # (created on demand, used downstream)
│   ├── !orig/
│   │   ├── 2024_01_15_143052_IMG_1234.JPG
│   │   └── 2024_01_15_143052_IMG_1234.CR3   # only with -r
│   ├── 2024_01_15_143052_IMG_1234.CR3       # without -r
│   └── 2024_01_15_143105_IMG_1235.CR3
├── 2024_01_16/
│   └── ...
```

## How it works

1. **Scan** — `os.scandir()` finds files with supported extensions
2. **EXIF** — A single `exiftool` call reads dates for all files at once
3. **Fallback** — No EXIF data? Uses the file modification date instead
4. **Conflicts** — Duplicate filenames get a `_2`, `_3`, etc. suffix
5. **Move** — `ThreadPoolExecutor` moves files in parallel

## Performance

| Storage | Recommended workers | Speedup |
|---------|---------------------|---------|
| NVMe | 8-16 | 5-10x |
| SATA SSD | 4-8 | 3-5x |
| HDD | 1-2 | 1x (sequential is better) |

## Error handling

- **Missing exiftool** — Clear message with installation instructions
- **Permission denied** — Logs error, continues with remaining files
- **Ctrl+C** — Finishes current operations, reports progress
- **No date** — Skips file with a warning

## Exit codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Errors (missing exiftool, invalid path, failed moves) |
| 2 | Argument error |
| 130 | Interrupted by Ctrl+C |

## License

MIT
