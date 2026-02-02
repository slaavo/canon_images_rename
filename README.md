# Photo Organizer

Szybkie batch'owe organizowanie zdjęć według daty EXIF.

## Funkcje

- **Szybkość**: Pojedyncze wywołanie exiftool + wielowątkowe przenoszenie (10-50x szybciej niż sekwencyjnie)
- **Formaty**: CR3, DNG, ARW, NEF, ORF, RAF, RW2, JPG, JPEG
- **Struktura folderów**: `YYYY_MM_DD/` z podfolderami `!orig/` i `!jpg/`
- **Nazewnictwo**: `YYYY_MM_DD_HHMMSS_oryginalna_nazwa.rozszerzenie`
- **Bezpieczeństwo**: dry-run, obsługa duplikatów, graceful Ctrl+C

## Wymagania

- Python 3.8+
- exiftool

```bash
# Ubuntu/Debian
sudo apt install libimage-exiftool-perl

# macOS
brew install exiftool

# Windows
# Pobierz z https://exiftool.org
```

## Użycie

```bash
# Podstawowe - organizuj bieżący folder
./rename_and_move_files.py

# Wskaż folder
./rename_and_move_files.py /ścieżka/do/zdjęć

# Inny folder wyjściowy
./rename_and_move_files.py -o /wyjście /zdjęcia

# Dry-run - podgląd zmian bez przenoszenia
./rename_and_move_files.py -d /zdjęcia

# RAW do !orig (domyślnie tylko JPEG idzie do !orig)
./rename_and_move_files.py -r /zdjęcia

# Więcej wątków (szybciej na NVMe)
./rename_and_move_files.py -w 8 /zdjęcia

# Mniej wątków (bezpieczniej na HDD)
./rename_and_move_files.py -w 1 /zdjęcia

# Verbose - szczegółowe logi
./rename_and_move_files.py -v /zdjęcia
```

## Opcje

| Opcja | Opis |
|-------|------|
| `-o, --output DIR` | Folder wyjściowy (domyślnie: ten sam co wejściowy) |
| `-d, --dry-run` | Podgląd zmian bez przenoszenia plików |
| `-r, --raw-subfolder` | Przenieś RAW do `!orig/` (domyślnie tylko JPEG) |
| `-w, --workers N` | Liczba wątków (domyślnie: 4) |
| `-v, --verbose` | Szczegółowe logi |

## Struktura wyjściowa

```
/wyjście/
├── 2024_01_15/
│   ├── !jpg/                    # (tworzony, ale nieużywany w tej wersji)
│   ├── !orig/
│   │   ├── 2024_01_15_143052_IMG_1234.JPG
│   │   └── 2024_01_15_143052_IMG_1234.CR3   # tylko z -r
│   ├── 2024_01_15_143052_IMG_1234.CR3       # bez -r
│   └── 2024_01_15_143105_IMG_1235.CR3
├── 2024_01_16/
│   └── ...
```

## Jak to działa

1. **Skanowanie** — `os.scandir()` znajduje pliki z obsługiwanymi rozszerzeniami
2. **EXIF** — Jedno wywołanie `exiftool` pobiera daty wszystkich plików naraz
3. **Fallback** — Brak EXIF? Używa daty modyfikacji pliku
4. **Konflikty** — Duplikaty nazw dostają suffix `_2`, `_3`, itd.
5. **Przenoszenie** — `ThreadPoolExecutor` przenosi pliki równolegle

## Wydajność

| Dysk | Zalecane wątki | Przyspieszenie |
|------|----------------|----------------|
| NVMe | 8-16 | 5-10x |
| SATA SSD | 4-8 | 3-5x |
| HDD | 1-2 | 1x (sekwencyjny lepszy) |

## Obsługa błędów

- **Brak exiftool** — Czytelny komunikat z instrukcją instalacji
- **Brak uprawnień** — Loguje błąd, kontynuuje z resztą
- **Ctrl+C** — Kończy bieżące operacje, raportuje postęp
- **Brak daty** — Pomija plik z ostrzeżeniem

## Kody wyjścia

| Kod | Znaczenie |
|-----|-----------|
| 0 | Sukces |
| 1 | Błędy (brak exiftool, nieprawidłowa ścieżka, nieudane przeniesienia) |
| 2 | Błąd argumentów |
| 130 | Przerwane przez Ctrl+C |

## Licencja

MIT
