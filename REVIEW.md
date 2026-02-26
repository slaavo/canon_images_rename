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
