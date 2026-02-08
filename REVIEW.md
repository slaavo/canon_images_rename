# Code Review: Testy i README

## Ogólna ocena

Projekt jest dobrze napisany — czysty, czytelny kod, dobra struktura testów, sensowne README.
Wszystkie 57 testów przechodzą. Poniżej szczegółowe uwagi.

---

## README.md

### Co jest dobrze
- Zwięzłe, czytelne, konkretne
- Tabela opcji, struktura folderów, kody wyjścia — wszystko w jednym miejscu
- Instrukcja instalacji exiftool na 3 platformach

### Uwagi

1. **Brak informacji o `-r` w diagramie struktury** — opis struktury pokazuje `# only with -r` jako komentarz inline, ale nie jest jasne, że _domyślnie_ pliki RAW trafiają do głównego folderu daty, a JPG-i zawsze do `!orig/`. Ktoś czytający diagram bez wcześniejszego kontekstu może się zgubić.

2. **Brak sekcji "How to run tests"** — skoro projekt ma `pyproject.toml` z konfiguracją pytest, warto dodać choćby jednolinijkowy `pip install -e ".[dev]" && pytest`.

3. **Folder `!jpg/` nie jest wyjaśniony** — w strukturze jest `!jpg/` z komentarzem "created on demand, used downstream", ale nigdzie nie wyjaśniono co oznacza "downstream". Skrypt tworzy ten folder (`ensure_folders_exist`), ale nigdy sam go nie używa. Jeśli to dla innego narzędzia — warto wyjaśnić. Jeśli nieużywany artefakt — usunąć z kodu.

4. **Niespójność: fallback na mtime vs "skips file"** — sekcja "How it works" mówi "No EXIF data? Uses the file modification date instead", ale "Error handling" mówi "No date — Skips file with a warning". Skrypt _najpierw_ próbuje fallback na `mtime`, a dopiero gdy i to zawiedzie, pomija plik. README powinno to odzwierciedlać.

5. **Brak `--version` w CLI** — w `pyproject.toml` jest `version = "1.0.0"`, ale skrypt nie eksponuje wersji przez CLI.

6. **Trzy różne nazwy projektu** — README mówi "Photo Organizer", plik to `rename_and_move_files.py`, repo to `canon_images_rename`. Warto ujednolicić.

---

## Testy

### Co jest dobrze
- Dobrze zorganizowane w klasy tematyczne
- Sensowne fixture w `conftest.py`
- Testy edge-case'ów (brak plików, timeout, puste katalogi, symlinki)
- Testy nie zależą od siebie nawzajem
- Wszystkie 57 testów przechodzą

### Uwagi krytyczne (brakujące testy)

1. **Brak testów dla `process_files()`** — główna funkcja orkiestrująca cały flow (`rename_and_move_files.py:433-605`). Łączy `find_files`, `get_exif_dates`, `UniqueFilenameGenerator`, `ensure_folders_exist`, `move_single_file` i `InterruptHandler`. Żaden test nie sprawdza integracji tych elementów. **To najważniejsza brakująca część test suite.**

2. **Brak testów dla `main()`** — parsowanie argumentów CLI, walidacja `--workers` (min/max), zachowanie przy braku exiftoola.

3. **Brak testów dla `InterruptHandler`** — klasa obsługi Ctrl+C nie jest testowana. Można sprawdzić czy flag `interrupted` jest poprawnie ustawiany po sygnale.

4. **Brak testów dla `print_progress()`** — funkcja ma logikę `update_interval`, nie jest testowana.

5. **Brak testów dla `_run_exiftool_batch()`** — testy `get_exif_dates` mockują `subprocess.run`, ale nie testują bezpośrednio parsowania w `_run_exiftool_batch` — np. co gdy exiftool zwróci ścieżkę absolutną zamiast nazwy pliku (linia 194).

6. **Brak testów dla `ColorFormatter`** — formatter logów nie jest testowany.

### Uwagi mniejsze

7. **`test_batching_large_file_list`** (`test_exif.py:101`) — test zależy od wartości stałej `EXIFTOOL_BATCH_SIZE=5000`. Gdyby ktoś zmienił stałą, test się wysypie bez jasnego komunikatu. Lepiej importować `EXIFTOOL_BATCH_SIZE` i użyć jej w teście.

8. **`test_hidden_file`** (`test_filename_gen.py:101`) — test sprawdza `.hidden` -> `.hidden_2`. Logika `generate()` traktuje `.hidden` jako plik bez rozszerzenia (bo `rfind(".")` zwraca 0, warunek to `> 0`). Zachowanie poprawne, ale nieoczywiste — warto dodać komentarz.

9. **Brak testu dla `stderr` logowania** — `_run_exiftool_batch` loguje `stderr` jako debug (linia 181-182), żaden test tego nie weryfikuje.

10. **`test_nonexistent_directory`** (`test_file_operations.py:75`) — test przechodzi poprawnie, ale nie weryfikuje czy `log.error` został wywołany.

11. **Brak testu cross-device move** — `move_single_file` używa `shutil.move` jako fallback gdy `os.rename` rzuci `OSError` (linia 384). Nie ma testu pokrywającego tę ścieżkę.

12. **`test_move_to_subdirectory`** (`test_file_operations.py:130`) — nie sprawdza `source_name` ani `dest_path` w `MoveResult`. Niekompletna asercja.

### Uwagi do `conftest.py`

13. **Fixture `exiftool_output_*` to stałe** — nie potrzebują być fixture'ami pytest (brak setup/teardown). Można je zdefiniować jako zmienne modułowe.

14. **`sample_photos` nie obejmuje wszystkich formatów** — brakuje `arw`, `nef`, `orf`, `raf`, `rw2`, `jpeg`. Test `test_finds_supported_extensions` weryfikuje tylko podzbiór.

---

## Podsumowanie priorytetów

| Priorytet | Uwaga |
|-----------|-------|
| **Wysoki** | Brak testów integracyjnych dla `process_files()` |
| **Wysoki** | Brak testów dla `main()` (CLI, walidacja argumentów) |
| **Średni** | Niespójność README (fallback mtime vs "skips file") |
| **Średni** | Folder `!jpg/` tworzony ale nigdy nieużywany |
| **Średni** | Brak testu cross-device move (shutil.move fallback) |
| **Niski** | Fixture'y jako stałe, brak testu ColorFormatter, brak --version |
| **Niski** | Trzy różne nazwy projektu |
