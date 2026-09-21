# Pilot 200 — загрузка CSV на Google Drive

**Статус: PASS**

## Файл на Drive

| | |
|---|---|
| Путь | `My Drive / Classification / pilot-200-expert-export.csv` |
| Folder ID | `1XKKGehpwYPMelnrYEkwn9E6JjnnlftCn` |
| File ID | `1nT2BuKo2habQacr741zOdjAg4eboR5MT` |
| Размер | 45 874 байт |
| Open / share link | https://drive.google.com/file/d/1nT2BuKo2habQacr741zOdjAg4eboR5MT/view?usp=drivesdk |
| Download | https://drive.google.com/uc?id=1nT2BuKo2habQacr741zOdjAg4eboR5MT&export=download |
| Доступ | anyone with link → reader |

Локальная копия: `docs/pilot-200-expert-export.csv`.

## OAuth probe (после Reconnect)

| Credential | Результат |
|---|---|
| **Google Drive account** (`S7mhg7CBYGpInlHx`) | **PASS** — `drive/v3/about` → `sergesychov@gmail.com` |
| **Google Sheets account 2** (`v2NiEo8MpFLub2Fq`) | **FAIL** — всё ещё «needs to be reconnected» (`invalid_grant` / revoked) |

Upload шёл через Drive OAuth (не Sheets 2). Для HITL / batch-acceptance Sheets 2 нужно отдельно переподключить в n8n Credentials.

## Как сделано

1. Минимальный probe `drive/v3/about` + поиск/создание папки `Classification` + upload CSV + permission `anyone`/`reader`.
2. Временный `[TMP] Pilot200 Drive Upload …` удалён после успеха; util `[UTIL] NPr11 — Drive Upload Package` остаётся inactive.
3. Stage 2 / hierarchy / пороги не трогались. Секреты не коммитились.

## Предыдущий FAIL

Все Google OAuth давали `invalid_grant`. После ручного reconnect **Google Drive account** ожил; CSV загружен.

## См. также

Полное зеркало Project docs: [`google-drive-project-mirror.md`](./google-drive-project-mirror.md)  
Папка: https://drive.google.com/drive/folders/1gYqGzZ2hc_YYdCtLl4kQnurEc4FuRHSo?usp=sharing
