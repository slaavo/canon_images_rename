# Code Review: Testy i README (Re-review)

## Stan po zmianach

- **108 testów**, wszystkie przechodzą (było 57)
- Wydzielono `plan_moves()` z `process_files()` — czysta logika routingu jest teraz testowalna bez mocków
- README naprawione (niespójności, brakujące sekcje)
- Wszystkie uwagi z pierwszego review zostały zaadresowane

---

## Co zostało naprawione

### Kod

| Uwaga | Status |
|-------|--------|
| Brak testowalnej logiki routingu w `process_files()` | Wydzielono `plan_moves()` — czysta funkcja, 11 testów |

### README

| Uwaga | Status |
|-------|--------|
| Niespójność fallback mtime vs "skips file" | Naprawione — obie sekcje opisują pełny flow |
| Brak wyjaśnienia folderu `!jpg/` | Dodano komentarz: "reserved for external JPEG processing tools" |
| Brak sekcji "Development" / jak uruchomić testy | Dodano sekcję z `pip install`, `pytest`, `pytest --cov` |
| Niejasny diagram `-r` | Dodano opis nad diagramem + komentarze w strukturze |
| Trzy różne nazwy projektu | Tytuł zmieniony na `# Photo Organizer (rename_and_move_files.py)` |

### Testy — nowe

| Plik | Klasa / zakres | Testów |
|------|----------------|--------|
| `test_plan_moves.py` | `TestPlanMoves` — routing JPEG/RAW, fallback mtime, skip, formaty nazw | 11 |
| `test_process_files.py` | `TestProcessFiles` — integracja pipeline (JPEG, RAW, dry-run, duplikaty) | 7 |
| `test_main.py` | `TestMain` — CLI args, workers walidacja, verbose, dry-run, output dir | 9 |
| `test_misc.py` | `TestInterruptHandler` — flagi, signal restore, context manager | 5 |
| `test_misc.py` | `TestPrintProgress` — interval, 100%, skip, format | 4 |
| `test_misc.py` | `TestColorFormatter` — kolory per level, brak mutacji rekordu | 4 |
| `test_exif.py` | `TestRunExiftoolBatch` — abs path parsing, stderr, malformed, timeout | 4 |

### Testy — poprawione

| Uwaga | Status |
|-------|--------|
| `test_batching` zależny od hardcoded 7500 | Używa importowanej `EXIFTOOL_BATCH_SIZE` |
| `test_hidden_file` nieoczywiste zachowanie | Dodano docstring wyjaśniający logikę `rfind` |
| `test_nonexistent_directory` brak sprawdzenia log.error | Dodano `mock_error.assert_called_once()` |
| `test_move_to_subdirectory` niekompletne asercje | Dodano sprawdzenie `source_name`, `dest_path`, treści pliku |
| Fixture `exiftool_output_*` jako pytest fixture | Zamienione na stałe modułowe w `conftest.py` |
| `sample_photos` brak wszystkich formatów | Dodano `jpeg`, `arw`, `nef`, `orf`, `raf`, `rw2` (11 plików) |
| Brak testu cross-device move | Dodano `test_cross_device_move_falls_back_to_shutil` |
| Brak testu stderr logowania | Dodano `test_logs_stderr` w `TestRunExiftoolBatch` |

---

## Dodatkowe poprawki (runda 2)

| Zmiana | Status |
|--------|--------|
| Dodano `--version` / `-V` do CLI | `__version__ = "1.0.0"` + argparse `action="version"` + test |
| `validate_date` — walidacja semantyczna | Dodano `strptime` sprawdzający poprawność dat (miesiąc 13, dzień 32, godz 25 → `None`) + 4 testy |
| Folder `!jpg/` | Potrzebny — zostawiony bez zmian |

## Co pozostało (niski priorytet)

| Uwaga | Komentarz |
|-------|-----------|
| `setup_logging()` wywoływane na poziomie modułu | Efekt uboczny przy importie — utrudnia testowanie logowania, ale nie blokuje |
| `__version__` zduplikowane z `pyproject.toml` | Można by czytać z `importlib.metadata`, ale dodaje złożoność |

---

## Runda 3 — poprawki po dokładnym review

Po zmianach: **114 testów**, wszystkie przechodzą.

| # | Uwaga | Status |
|---|-------|--------|
| 1 | `--dry-run` tworzył katalog wyjściowy mimo „no changes will be made" | Naprawione — `mkdir` korzenia outputu pominięty w dry-run + test `test_dry_run_does_not_create_output_folder` |
| 3 | `DEFAULT_WORKERS = 12`, a docstring/README/komentarz mówiły „8" | Ujednolicone do 12 (docstring CLI, komentarz przy stałej, README) |
| 4 | Ścieżka przerwania w pętli kopiowania nieprzetestowana | Dodano test `test_interrupt_cancels_pending_moves` (anulowanie pending tasks) |
| 5 | Handler sygnału robił I/O (`print` + `log.warning`) | Handler ustawia tylko flagę; komunikaty przeniesione do głównej pętli (async-signal-safe) |
| 2 | Docstring modułu pokazywał JPEG w `!jpg/`, a kod routuje JPEG do `!orig/` | Poprawiona **tylko dokumentacja** — układ folderów jest zamierzony |

**#2 — decyzja:** układ folderów jest celowy. `!jpg/` jest świadomie rezerwowany (pozostaje pusty) dla zewnętrznych narzędzi do obróbki JPEG; JPEG-i trafiają do `!orig/`. Poprawiono jedynie docstring modułu, który się z tym kłócił.

## Co pozostało (świadome kompromisy)

| Uwaga | Komentarz |
|-------|-----------|
| `setup_logging()` na poziomie modułu | Efekt uboczny przy imporcie — zostawione (zmiana komplikuje ergonomię importu) |
| `__version__` zduplikowane z `pyproject.toml` | Zostawione — `importlib.metadata` dodaje złożoność |

---

## Runda 4 — optymalizacja architektury i wydajności

Po zmianach: **116 testów**, wszystkie przechodzą. Wersja podbita do **1.1.0**.

| # | Zmiana | Szczegóły |
|---|--------|-----------|
| 1 | `exiftool -fast2` | Pomija skan trailera JPEG i maker notes — czytamy tylko DateTimeOriginal/CreateDate (standardowe bloki EXIF/QuickTime na początku pliku). Największy realny zysk na folderach z JPEG (karta SD, NAS). Test `test_uses_fast2_flag`. |
| 2 | `plan_moves()` w pełni czysta | Nowy `ScannedFile(path, mtime_date)` — mtime formatowany już w `find_files()` z cache'owanego stat-a scandir. Usunięto `get_file_mod_date()` (jeden `stat()` mniej na plik bez EXIF), testy routingu nie potrzebują żadnych mocków (usunięty mock z `test_skips_file_without_any_date`). Nowy test `test_no_io_for_nonexistent_paths`. |
| 3 | Równoległe batche exiftool | Przy >`EXIFTOOL_BATCH_SIZE` (5000) plików batche idą przez `ThreadPoolExecutor` (max `EXIFTOOL_MAX_PARALLEL = 4` procesy). Ścieżka jedno-batchowa bez zmian. Test `test_multiple_batches_merge_results`. |

Weryfikacja end-to-end z prawdziwym exiftool: pliki z `DateTimeOriginal` trafiają do
`YYYY_MM_DD/!orig/` z poprawną nazwą (`-fast2` nadal wyciąga daty), plik bez EXIF
używa mtime, `!jpg/` tworzony i pusty, dry-run bez efektów ubocznych.

---

## Runda 5 — uwaga z GitHub: `-fast2` a CR3 (kontener QuickTime)

**Uwaga (PR #8):** dla CR3, których metadane QuickTime leżą *za* danymi obrazu,
`-fast2` może pominąć DateTimeOriginal/CreateDate i po cichu wpaść na fallback
mtime — zdjęcie ląduje pod złą datą. Dokumentacja ExifTool: `-fast2` „stops
processing at … the mdat atom of QuickTime-format files”.

**Potwierdzenie w źródłach ExifTool 12.76:** `QuickTime.pm:9505` —
`last if $fast > 1 and $tag eq 'mdat'`; `ExifTool.pm:268` — CR3 czytany przez
parser MOV/QuickTime. Poziom `-fast` (1) nie uruchamia tego skrótu.

| # | Zmiana | Szczegóły |
|---|--------|-----------|
| 1 | `QUICKTIME_EXTENSIONS = {".cr3"}` | Formaty w kontenerze ISOBMFF/QuickTime — czytane z `-fast` zamiast `-fast2`. |
| 2 | `_run_exiftool_batch(batch, fast_flag)` | Flaga `-fast*` jako parametr; usunięty mylący komentarz o „bezpieczeństwie” `-fast2`. |
| 3 | `get_exif_dates()` grupuje po fladze | Pliki dzielone na grupy `-fast2` (JPEG, TIFF-owe RAW) i `-fast` (CR3), potem na batche; folder CR3+JPG to dwa równoległe wywołania exiftool (istniejący pool), więc czas ścienny nie rośnie. |
| 4 | Testy | `test_jpeg_uses_fast2_flag`, `test_quicktime_raw_uses_fast_not_fast2`, `test_mixed_cr3_and_jpeg_use_separate_invocations`, `test_passes_fast_flag_to_exiftool`. |

**Reprodukcja na prawdziwym exiftool:** syntetyczny plik `.cr3` (ftyp `crx `,
`mdat`, dopiero potem `moov/mvhd` z creation_time). `exiftool -fast2` → brak
daty; `exiftool -fast` → `2024_06_15_143022`. Po poprawce narzędzie umieszcza
taki plik pod datą QuickTime, a nie pod mtime (sprawdzone dry-run + realny run).

Bez podbicia wersji — 1.1.0 nie została jeszcze wydana (ta sama gałąź / PR #8).


---

## Runda 6 — druga tura review PR #8 (7 uwag)

Po zmianach: wszystkie testy przechodzą (patrz liczba w commicie). Bez podbicia
wersji — 1.1.0 nadal niewydana na tej gałęzi.

Ocena: **wszystkie 7 uwag prawdziwe**, o bardzo różnym prawdopodobieństwie.
Najgroźniejsza w praktyce była para #3+#4: Ctrl+C w trakcie skanu EXIF zabija
proces exiftool, skrypt dostawał pusty słownik, ostrzegał „using file
modification date" i przenosił wszystko według mtime.

| # | Uwaga | Prawdziwa? | Prawdop. | Poprawka |
|---|-------|-----------|----------|----------|
| 1 | `os.rename` nadpisuje plik utworzony po skanie nazw (utrata danych) | tak | niskie | `_move_no_clobber()`: `os.link`+`unlink` (atomowo odmawia, gdy cel istnieje); na FS bez hardlinków (FAT/exFAT) placeholder `O_EXCL` + `os.replace`; między urządzeniami kopia z ekskluzywnym utworzeniem pliku. `FileExistsError` → błąd, nigdy nadpisanie. |
| 2 | Katalog o nazwie pliku docelowego → `shutil.move` wrzuca zdjęcie do niego | tak | znikome | `_get_existing()` liczy każdy wpis katalogu; `shutil.move` usunięty z ścieżki przenoszenia. |
| 3 | Timeout exiftool → `{}` → wszystko po mtime | tak | średnie | `ExifToolError` przy timeoucie, kodzie < 0 (sygnał) lub kodzie ≠ 0 bez wyjścia; `process_files()` przerywa **przed** jakimkolwiek przeniesieniem, exit 1. Kod ≠ 0 *z* wyjściem = częściowy sukces exiftool (sprawdzone: brakujący plik → rc=1, reszta wypisana) → tylko ostrzeżenie. |
| 4 | Ctrl+C w trakcie skanu EXIF nie zatrzymuje przenoszenia | tak | **wysokie** | Flaga sprawdzana zaraz po skanie EXIF, przed `ensure_folders_exist()`; zabity exiftool przy ustawionej fladze raportowany jako przerwanie (exit 130), nie awaria. |
| 5 | Symlinki traktowane jak zdjęcia | tak | niskie | `find_files()` pomija `entry.is_symlink()` (debug per link + jedno ostrzeżenie zbiorcze). |
| 6 | Limit 5000 plików nie ogranicza bajtów argv (Linux 2 MiB, macOS 1 MiB, Windows ~32K znaków) | tak | średnie | Lista plików idzie na stdin przez `-@ -` (sprawdzone na exiftool 12.76); `EXIFTOOL_BATCH_SIZE` zostaje jako granica pracy jednego procesu i jednostka równoległości. Ścieżka z `\n` pomijana z ostrzeżeniem. |
| 7 | `PermissionError` przy skanie → „brak plików" → exit 0 | tak | średnie | `find_files()` rzuca `ScanError`; `main()` zwraca 1. |

Nowe testy: odmowa nadpisania (link / EXDEV / EPERM), katalog jako kolizja,
brak placeholdera po nieudanym przenoszeniu, symlinki, `ScanError`,
`ExifToolError` (timeout, kod -2, kod 1 bez wyjścia) vs częściowy sukces,
`-@ -` na stdin, przerwanie podczas skanu EXIF, exit 1 z `main()`.


---

## Runda 7 — trzecie review Codexa (commit `d3ff890`), 2 uwagi P2

Obie prawdziwe, obie są konsekwencją poprawek z rundy 6.

| # | Uwaga | Poprawka |
|---|-------|----------|
| 1 | Plik, którego exiftool nie zdołał otworzyć, nie ma wpisu w `file_dates`, a `plan_moves()` traktował brak wpisu jak „brak EXIF" → fallback mtime, niezweryfikowana data. | Sonda na exiftool 12.76: dla każdego **otwartego** pliku (nawet uszkodzonego/pustego) jest wiersz `nazwa\t-\t-`; **brak wiersza** tylko dla plików nieotwieralnych (brak/uprawnienia). Stąd status per plik bez dodatkowego wywołania: `_run_exiftool_batch()` zwraca `dict[str, str \| None]` — wpis dla każdego wiersza (`None` = zbadany, bez daty), brak wpisu = niezbadany. `plan_moves()` zwraca dodatkowo `unreadable_count`; taki plik jest logowany jako błąd, liczony w `errors` (exit 1) i **zostaje na miejscu**. |
| 2 | Po udanym `os.link` i nieudanym `os.unlink(source)` (katalog źródłowy bez prawa zapisu) w wyjściu zostawał hardlink mimo zgłoszonego błędu; to samo na ścieżce kopii między urządzeniami. | `_unlink_source_or_rollback()`: przy nieudanym usunięciu źródła usuwa świeżo utworzony cel i przepuszcza wyjątek. Ścieżka `os.replace` jest atomowa — bez zmian. |

Nowe testy: wiersz `-` → `None`, brak wiersza → brak wpisu, `plan_moves` z `{}` →
`unreadable == 1` bez fallbacku, `process_files` z jednym nieczytelnym plikiem →
`(1, 1)` i plik na miejscu (także dry-run), rollback linku i kopii EXDEV przy
nieudanym `unlink` źródła.
