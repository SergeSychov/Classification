# Google Drive — зеркало Project Classification docs

**Статус: PASS** (2026-09-21)

Обзор user-facing документов Project Classification на Drive. Канон store остаётся в Agent Store; Drive — зеркало для чтения/шаринга.

## Папки

| Папка | Path | Folder ID | Shareable link |
|---|---|---|---|
| Корень | `My Drive / Classification` | `1XKKGehpwYPMelnrYEkwn9E6JjnnlftCn` | https://drive.google.com/drive/folders/1XKKGehpwYPMelnrYEkwn9E6JjnnlftCn?usp=sharing |
| Docs mirror | `Classification / Project docs` | `1gYqGzZ2hc_YYdCtLl4kQnurEc4FuRHSo` | https://drive.google.com/drive/folders/1gYqGzZ2hc_YYdCtLl4kQnurEc4FuRHSo?usp=sharing |
| Key evidence | `Classification / internal-evidence` | `1bPUlG9klAxnxH98wzrQ8uu3-Zky1vXg2` | https://drive.google.com/drive/folders/1bPUlG9klAxnxH98wzrQ8uu3-Zky1vXg2?usp=sharing |

Доступ папок/файлов: **anyone with link → reader**.

Главная точка входа для обзора: **Project docs**.

## Project docs — загруженные файлы

| Файл | Op | File link |
|---|---|---|
| `product-goal-and-plan.md` | upload | https://drive.google.com/file/d/1vRZIy2PVVtNEC01SLZAJ_B8YWYoXknh-/view?usp=drivesdk |
| `project-context.md` | upload | https://drive.google.com/file/d/1yYOM6OXFtjfz1UpXX88fT9AxW3lvec-6/view?usp=drivesdk |
| `ops-readiness-stage-b.md` | upload | https://drive.google.com/file/d/1NZZScilH5VgsePG1pqkspw5dSeCRtK-0/view?usp=drivesdk |
| `llm-failover-deepseek-qwen.md` | upload | https://drive.google.com/file/d/1AZyYTuydBUaG0DueCS1Y6YrU5PReLSrl/view?usp=drivesdk |
| `fin-auto-close-fix.md` | upload | https://drive.google.com/file/d/1iml1MEDjPl8oUltoJ1m-aVYAKPLgp7QJ/view?usp=drivesdk |
| `pilot-200-report.md` | upload | https://drive.google.com/file/d/1yuhw6R6hiJU-gBvZjC0hPpIW9-pnQlls/view?usp=drivesdk |
| `pilot-200-expert-export.csv` | upload | https://drive.google.com/file/d/1KBP6g6Efwq3oTabojHth0_MWfGkcgzmu/view?usp=drivesdk |
| `pilot-200-drive-upload.md` | upload | https://drive.google.com/file/d/1jOuzGPV69QdibAjHUEXE2MkBmMqw6hN2/view?usp=drivesdk |
| `classification-scheme-prompts.md` | upload | https://drive.google.com/file/d/1T-P5VUrrU5yBOQLsJldX-QOQVp-FBSUA/view?usp=drivesdk |
| `pilot-200-full-export.csv` | upload | https://drive.google.com/file/d/1MNUwiZKFH-hXqmNwPh7fMe7dYaP-vc2w/view?usp=drivesdk |
| `classification-pipeline-diagram.png` | upload | https://drive.google.com/file/d/1QOgcDPuGajYpttwVcMS9mk7W9SCAEFuC/view?usp=drivesdk |
| `classification-pipeline.drawio` | upload | https://drive.google.com/file/d/1NTQuLSgyh-vODat6URQmr2kX2VJQ_3N7/view?usp=drivesdk |
| `classification-pipeline-diagram.md` | update | https://drive.google.com/file/d/1pb2SJ66g6LnC_5v2gG1YcV57W1nJedRk/view?usp=drivesdk |
| `notes.md` | upload | https://drive.google.com/file/d/1HE2g9-eGzRfkcoU4j-YwqI6deDVY4G9b/view?usp=drivesdk |
| `google-drive-project-mirror.md` | upload | https://drive.google.com/file/d/19LIm93ALtUM2yjttYNn_WSA0e92WzX1i/view?usp=drivesdk |

## Корень Classification (continuity)

| Файл | Op | File link |
|---|---|---|
| `pilot-200-expert-export.csv` | update (без дубля) | https://drive.google.com/file/d/1nT2BuKo2habQacr741zOdjAg4eboR5MT/view?usp=drivesdk |

Тот же CSV также лежит в `Project docs` (копия для единого обзора docs).

## internal-evidence (кратко)

| Файл | File link |
|---|---|
| `pilot-200-runs.md` | https://drive.google.com/file/d/1ibKJbz5TDtu8PvhRefYdVkjX-fvy3fcy/view?usp=drivesdk |
| `pilot-200-selection.md` | https://drive.google.com/file/d/13k92RGsPoHX5HaBVTDOKN1cYzKSkfobj/view?usp=drivesdk |

Остальной `internal/` на Drive не зеркалился.

## OAuth probe

| Credential | Результат |
|---|---|
| **Google Drive account** (`S7mhg7CBYGpInlHx`) | **PASS** — `drive/v3/about` → `sergesychov@gmail.com` |
| **Google Sheets account 2** (`v2NiEo8MpFLub2Fq`) | **PASS** — about → тот же аккаунт (после reconnect) |

Upload шёл через Drive OAuth. Sheets 2 проверен отдельно (нужен для HITL / batch-acceptance).

## Как сделано

1. Переиспользована папка `Classification`; созданы подпапки `Project docs` и `internal-evidence`.
2. Все user-facing `docs/*` + `notes.md` залиты в `Project docs`; корневой CSV обновлён in-place.
3. TMP workflow удалён после успеха; `[UTIL] NPr11 — Drive Upload Package` остаётся inactive.
4. Stage 2 / hierarchy / пороги не трогались. Секреты не коммитились.

## Preference

Новые user-facing docs в store → также зеркалить в `Classification / Project docs` (upsert по имени, без хаотичных дублей).
