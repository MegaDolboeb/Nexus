"""Переводы интерфейса панели (раздел 10 задания: Давид любит немецкий, китайцев много — но
пока только ru/en, см. config.LANGUAGES). Важное правило: это только про ОБОЛОЧКУ панели.

Темы (personal/interests.json) и то, что уже написал Nexus — выжимки, выводы, память —
НЕ переводятся задним числом. Они остаются на том языке, на котором были написаны. Новые
материалы после смены языка пишутся уже на нём (см. research_mode/язык в jobs.py)."""
from __future__ import annotations

from .. import config

STRINGS: dict[str, dict[str, str]] = {
    "nav.home": {"ru": "Главная", "en": "Home"},
    "nav.research": {"ru": "Исследования", "en": "Research"},
    "nav.conductor": {"ru": "Дирижёр", "en": "Conductor"},
    "nav.interests": {"ru": "Интересы", "en": "Interests"},
    "nav.memory": {"ru": "Память", "en": "Memory"},
    "nav.sources": {"ru": "Источники", "en": "Sources"},
    "nav.settings": {"ru": "Настройки", "en": "Settings"},
    "nav.sections": {"ru": "Разделы", "en": "Sections"},

    "engine.on": {"ru": "Движок работает", "en": "Engine running"},
    "engine.off": {"ru": "Движок выключен", "en": "Engine off"},
    "engine.foot": {"ru": "Движок: {state}", "en": "Engine: {state}"},
    "engine.running_with_model": {"ru": "работает · {model}", "en": "running · {model}"},

    "control.start": {"ru": "Запустить", "en": "Start"},
    "control.pause": {"ru": "Пауза", "en": "Pause"},
    "control.stop": {"ru": "Остановить с сохранением", "en": "Stop and save"},
    "control.running": {"ru": "Работает", "en": "Running"},
    "control.paused": {"ru": "На паузе", "en": "Paused"},
    "control.stopped": {"ru": "Остановлен", "en": "Stopped"},
    "control.unavailable": {"ru": "Управление недоступно", "en": "Control unavailable"},

    "priority.default_title": {"ru": "Приоритетная программа", "en": "Priority app"},
    "priority.free": {"ru": "Работа идёт — {name} сейчас свободна", "en": "Working — {name} is free right now"},
    "priority.busy": {"ru": "Работа прекращена — {name} сейчас занята", "en": "Paused — {name} is busy right now"},
    "priority.unknown": {"ru": "Не знаем — Nexus на всякий случай ждёт.", "en": "Unknown — Nexus waits just in case."},
    "priority.not_configured": {"ru": "Приоритетная программа не настроена — Nexus работает свободно",
                                 "en": "No priority app configured — Nexus runs freely"},
    "priority.vram_free": {"ru": "Видеокарта свободна для Nexus.", "en": "GPU is free for Nexus."},
    "priority.photo_hint": {"ru": "Фото выбирается в настройках", "en": "Photo is chosen in settings"},

    "home.title": {"ru": "Главная", "en": "Home"},
    "home.updated": {"ru": "Обновлено в {time}", "en": "Updated at {time}"},
    "home.interests": {"ru": "Интересы", "en": "Interests"},
    "home.all_materials": {"ru": "Все материалы →", "en": "All materials →"},
    "home.topics_empty": {"ru": "Темы ещё не настроены.", "en": "No topics configured yet."},
    "home.recent": {"ru": "Свежее", "en": "Recent"},
    "home.recent_empty": {"ru": "Пока ничего не готово — Nexus ещё изучает собранное.",
                           "en": "Nothing ready yet — Nexus is still studying what it gathered."},
    "home.materials_count": {"ru": "материал(ов)", "en": "material(s)"},
    "home.tasks_foot": {"ru": "Задач: {running} выполняется, {total} всего", "en": "Tasks: {running} running, {total} total"},

    "research.title": {"ru": "Исследования", "en": "Research"},
    "research.subtitle": {"ru": "Всё, что Nexus собрал и разобрал по вашим темам",
                           "en": "Everything Nexus gathered and analyzed on your topics"},
    "research.all": {"ru": "Все", "en": "All"},
    "research.details": {"ru": "Подробно →", "en": "Details →"},
    "research.source_link": {"ru": "Источник ↗", "en": "Source ↗"},
    "research.empty": {"ru": "Пока здесь пусто — Nexus ещё изучает собранное.",
                        "en": "Still empty here — Nexus is still studying what it gathered."},
    "research.go_to_date": {"ru": "Перейти к дате", "en": "Go to date"},
    "research.clear_date": {"ru": "Сбросить дату", "en": "Clear date"},
    "research.overview_btn": {"ru": "Коротко", "en": "Brief"},
    "research.overview_loading": {"ru": "Делаю короткую выжимку…", "en": "Making a short overview…"},
    "research.overview_error": {"ru": "ошибка", "en": "error"},
    "research.overview_network_error": {"ru": "Сеть недоступна.", "en": "Network unavailable."},

    "interests.title": {"ru": "Интересы", "en": "Interests"},
    "interests.subtitle": {"ru": "Темы Nexus, по приоритету. Изменить список можно в personal/interests.json.",
                            "en": "Nexus topics, by priority. Edit the list in personal/interests.json."},
    "interests.priority": {"ru": "Приоритет {n}", "en": "Priority {n}"},
    "interests.selected_now": {"ru": "отобрано сейчас", "en": "selected now"},
    "interests.total_in_work": {"ru": "всего в работе", "en": "total in progress"},
    "interests.empty": {"ru": "Темы ещё не настроены.", "en": "No topics configured yet."},

    "memory.title": {"ru": "Память", "en": "Memory"},
    "memory.subtitle": {"ru": "Темы, которые Nexus изучил; выводы обновляются со временем",
                         "en": "Topics Nexus has studied; conclusions update over time"},
    "memory.search_placeholder": {"ru": "Поиск по словам (пока без смысла — это отдельная кнопка появится позже)",
                                   "en": "Search by words (no semantic search yet — a separate button will come later)"},
    "memory.find": {"ru": "Найти", "en": "Find"},
    "memory.sources_count": {"ru": "источник(ов)", "en": "source(s)"},
    "memory.related_count": {"ru": "связанных тем", "en": "related topics"},
    "memory.updated": {"ru": "обновлено {time}", "en": "updated {time}"},
    "memory.details": {"ru": "Подробно →", "en": "Details →"},
    "memory.empty_query": {"ru": "Ничего не нашлось по запросу «{q}».", "en": "Nothing found for “{q}”."},
    "memory.empty": {"ru": "Память пока пуста.", "en": "Memory is empty so far."},
    "memory.back": {"ru": "← Назад к памяти", "en": "← Back to memory"},
    "memory.conclusions": {"ru": "Выводы", "en": "Conclusions"},
    "memory.full_report": {"ru": "Подробный отчёт", "en": "Full report"},
    "memory.related": {"ru": "Связанные темы", "en": "Related topics"},
    "memory.history": {"ru": "История изменений", "en": "Change history"},

    "material.back": {"ru": "← Назад к исследованиям", "en": "← Back to research"},
    "material.open_source": {"ru": "Открыть источник ↗", "en": "Open source ↗"},
    "material.to_memory": {"ru": "В памяти →", "en": "In memory →"},

    "sources.title": {"ru": "Источники", "en": "Sources"},
    "sources.subtitle": {"ru": "Список настраивается в personal/sources.json",
                          "en": "The list is configured in personal/sources.json"},
    "sources.col_source": {"ru": "Источник", "en": "Source"},
    "sources.col_reliability": {"ru": "Надёжность", "en": "Reliability"},
    "sources.col_status": {"ru": "Статус", "en": "Status"},
    "sources.col_count": {"ru": "Материалов", "en": "Materials"},
    "sources.col_last_ok": {"ru": "Последний успех", "en": "Last success"},
    "sources.primary": {"ru": "ПЕРВОИСТОЧНИК", "en": "PRIMARY SOURCE"},
    "sources.ok": {"ru": "работает", "en": "working"},
    "sources.error": {"ru": "ошибка", "en": "error"},
    "sources.never": {"ru": "никогда", "en": "never"},
    "sources.empty": {"ru": "Источники не настроены.", "en": "No sources configured."},
    "reliability.high": {"ru": "высокая", "en": "high"},
    "reliability.medium": {"ru": "средняя", "en": "medium"},
    "reliability.low": {"ru": "низкая", "en": "low"},

    "sources.add_title": {"ru": "Добавить источник", "en": "Add a source"},
    "sources.add_hint": {"ru": "Название, ссылка на RSS-ленту и пару слов зачем. Nexus попробует её прочитать "
                               "и спросит модель, похож ли источник на нормальный — решаете вы.",
                          "en": "Name, RSS feed link and a couple words why. Nexus will try to read it and ask "
                               "the model if it looks like a solid source — the decision is yours."},
    "sources.add_name_placeholder": {"ru": "Название источника", "en": "Source name"},
    "sources.add_url_placeholder": {"ru": "Ссылка на RSS-ленту", "en": "RSS feed link"},
    "sources.add_note_placeholder": {"ru": "Почему хотите добавить (коротко)", "en": "Why you want to add it (briefly)"},
    "sources.add_check": {"ru": "Проверить", "en": "Check"},
    "sources.add_checking": {"ru": "Проверяю…", "en": "Checking…"},
    "sources.add_id_placeholder": {"ru": "Короткий id (латиницей)", "en": "Short id (latin letters)"},
    "sources.add_confirm": {"ru": "Добавить в список", "en": "Add to the list"},
    "sources.add_added": {"ru": "Добавлено.", "en": "Added."},
    "sources.add_error": {"ru": "ошибка", "en": "error"},
    "sources.add_network_error": {"ru": "Сеть недоступна.", "en": "Network unavailable."},
    "sources.verdict.good": {"ru": "Выглядит нормально", "en": "Looks fine"},
    "sources.verdict.caution": {"ru": "Есть повод насторожиться", "en": "There's reason for caution"},
    "sources.verdict.unclear": {"ru": "По этим данным не разобрать", "en": "Can't tell from this"},
    "sources.sample_titles": {"ru": "Примеры заголовков из ленты", "en": "Sample titles from the feed"},
    "sources.fetch_failed": {"ru": "Не удалось прочитать ленту", "en": "Couldn't read the feed"},
    "sources.col_actions": {"ru": "Действия", "en": "Actions"},
    "sources.delete": {"ru": "Удалить", "en": "Delete"},
    "sources.delete_confirm": {"ru": "Точно?", "en": "Sure?"},
    "sources.delete_error": {"ru": "Не удалось удалить", "en": "Couldn't delete"},

    "settings.topics_add_title": {"ru": "Добавить свою тему", "en": "Add your own topic"},
    "settings.topics_add_hint": {
        "ru": "Название, короткое описание и ключевые слова (через запятую, можно и по-русски, и по-английски). "
              "Без ключевых слов тема никогда ничего не найдёт — дешёвый отбор ищет по ним до того, как позвать модель.",
        "en": "Name, a short description and keywords (comma-separated, Russian and English both welcome). "
              "Without keywords the topic will never catch anything — the cheap pre-filter searches by them before the model is involved."},
    "settings.topics_name_placeholder": {"ru": "Название темы", "en": "Topic name"},
    "settings.topics_about_placeholder": {"ru": "Короткое описание, о чём тема", "en": "Short description of the topic"},
    "settings.topics_keywords_placeholder": {"ru": "Ключевые слова через запятую", "en": "Keywords, comma-separated"},
    "settings.topics_add_btn": {"ru": "Добавить тему", "en": "Add topic"},
    "settings.topics_delete": {"ru": "Удалить", "en": "Delete"},
    "settings.topics_delete_confirm": {"ru": "Точно?", "en": "Sure?"},
    "settings.topics_add_error": {"ru": "ошибка", "en": "error"},
    "settings.col_actions": {"ru": "Действия", "en": "Actions"},

    "conductor.title": {"ru": "Дирижёр", "en": "Conductor"},
    "conductor.subtitle": {"ru": "Поручения обычными словами — важнее обычных планов Nexus",
                            "en": "Plain-language errands — they outrank Nexus's regular plans"},
    "conductor.intro": {"ru": "Напишите, что изучить. Nexus сначала проверит поручение на подготовку вреда, "
                              "а если всё в порядке — ответит, как только освободится видеокарта и приоритетная "
                              "программа не будет против.",
                         "en": "Write what to look into. Nexus first checks the errand for harmful intent, "
                              "then answers once the GPU is free and the priority app doesn't mind."},
    "conductor.no_notify": {"ru": "Придёт уведомление Windows", "en": "A Windows notification will arrive"},
    "conductor.no_notify_rest": {"ru": " — полный ответ появится здесь же.",
                                  "en": " — the full answer appears right here."},
    "conductor.placeholder": {"ru": "Например: сначала изучи гуманоидных роботов, потом нейросети",
                               "en": "For example: first look into humanoid robots, then neural networks"},
    "conductor.submit": {"ru": "Поручить", "en": "Submit"},
    "conductor.checking": {"ru": "Проверяю…", "en": "Checking…"},
    "conductor.denied": {"ru": "Отказано: {reason}", "en": "Denied: {reason}"},
    "conductor.queued": {"ru": "Поставлено в очередь (задача №{id}). Ждём, пока Nexus сможет взяться — обновляю само.",
                          "en": "Queued (task #{id}). Waiting for Nexus to pick it up — updates automatically."},
    "conductor.network_error": {"ru": "Сеть недоступна, попробуйте ещё раз.", "en": "Network unavailable, try again."},
    "conductor.ask": {"ru": "Нужно уточнение: {why}", "en": "Needs clarification: {why}"},
    "conductor.no_answer": {"ru": "Задача завершилась без ответа ({state}): {reason}",
                             "en": "Task finished without an answer ({state}): {reason}"},
    "conductor.error": {"ru": "ошибка", "en": "error"},

    "settings.title": {"ru": "Настройки", "en": "Settings"},
    "settings.subtitle": {"ru": "Своё под себя: темы, расписание, как именно Nexus исследует",
                           "en": "Make it yours: topics, schedule, how exactly Nexus researches"},
    "settings.photo_title": {"ru": "Фото приоритетной программы", "en": "Priority app's photo"},
    "settings.photo_hint": {"ru": "Выбираете только вы — Nexus не скачивает случайные картинки. PNG, JPEG или WEBP, до 8 МБ.",
                             "en": "Only you choose it — Nexus never downloads random pictures. PNG, JPEG or WEBP, up to 8 MB."},
    "settings.photo_not_chosen": {"ru": "Файл не выбран", "en": "No file chosen"},
    "settings.photo_uploading": {"ru": "Загружаю…", "en": "Uploading…"},
    "settings.photo_saved": {"ru": "Сохранено.", "en": "Saved."},
    "settings.photo_error": {"ru": "ошибка", "en": "error"},
    "settings.photo_network_error": {"ru": "Сеть недоступна.", "en": "Network unavailable."},
    "settings.language_title": {"ru": "Язык", "en": "Language"},
    "settings.language_hint": {"ru": "Интерфейс и новые материалы — на этом языке. Старые записи как были, так и останутся.",
                                "en": "The interface and new materials use this language. Old entries stay as they are."},
    "settings.research_title": {"ru": "Как Nexus исследует", "en": "How Nexus researches"},
    "settings.custom_style": {"ru": "Свой стиль (по желанию) — добавляется к каждой выжимке и ответу Дирижёра",
                               "en": "Your own style (optional) — added to every digest and Conductor answer"},
    "settings.custom_style_placeholder": {"ru": "Например: пиши совсем коротко, без списков",
                                           "en": "For example: write very short, no bullet lists"},
    "settings.segment_min": {"ru": "Отрезок работы, мин", "en": "Work segment, min"},
    "settings.rest_min": {"ru": "Пауза между отрезками, мин", "en": "Pause between segments, min"},
    "settings.after_priority_min": {"ru": "Ждать после занятости приоритетной программы, мин", "en": "Wait after priority app is busy, min"},
    "settings.save": {"ru": "Сохранить", "en": "Save"},
    "settings.saved": {"ru": "Сохранено. {note}", "en": "Saved. {note}"},
    "settings.topics_title": {"ru": "Темы", "en": "Topics"},
    "settings.col_topic": {"ru": "Тема", "en": "Topic"},
    "settings.col_enabled": {"ru": "Включена", "en": "Enabled"},
    "settings.col_priority": {"ru": "Приоритет", "en": "Priority"},
    "settings.priority_1": {"ru": "1 — главное", "en": "1 — main"},
    "settings.priority_2": {"ru": "2 — обычное", "en": "2 — regular"},
    "settings.priority_3": {"ru": "3 — дополнительное", "en": "3 — extra"},
    "settings.save_topics": {"ru": "Сохранить темы", "en": "Save topics"},
    "settings.save_error": {"ru": "Ошибка сохранения.", "en": "Save failed."},
    "settings.model_work": {"ru": "Главная модель (видеокарта)", "en": "Main model (GPU)"},
    "settings.model_cpu": {"ru": "Модель для процессора (игры)", "en": "CPU model (during games)"},
    "settings.model_embed": {"ru": "Поиск по смыслу", "en": "Semantic search"},
    "settings.priority_vram": {"ru": "Нужно свободной видеопамяти для неё", "en": "VRAM it needs free"},
    "settings.priority_ram": {"ru": "Нужно свободной оперативной памяти для неё", "en": "RAM it needs free"},
    "settings.min_free_ram": {"ru": "Минимум свободной памяти, чтобы начать работу", "en": "Minimum free RAM to start working"},
    "settings.games_list": {"ru": "Игры (список)", "en": "Games (list)"},
    "settings.priority_title": {"ru": "Приоритетная программа", "en": "Priority app"},
    "settings.priority_hint": {
        "ru": "Пока эта программа занята, Nexus не трогает видеокарту — так же, как во время игр. "
              "Оставь название пустым, чтобы выключить эту функцию — тогда Nexus просто работает свободно.",
        "en": "While this program is busy, Nexus leaves the GPU alone — same as during games. "
              "Leave the name empty to turn this off — Nexus then just runs freely."},
    "settings.priority_name": {"ru": "Название (как показывать)", "en": "Name (how to display it)"},
    "settings.priority_name_placeholder": {"ru": "Например: Моя программа", "en": "e.g.: My companion app"},
    "settings.priority_processes": {"ru": "Процессы, означающие «занята» (через запятую)", "en": "Processes meaning \"busy\" (comma-separated)"},
    "settings.priority_processes_placeholder": {"ru": "например: app.exe, helper.exe", "en": "e.g.: app.exe, helper.exe"},
    "settings.priority_ports": {"ru": "Порты, означающие «занята» (через запятую)", "en": "Ports meaning \"busy\" (comma-separated)"},
    "settings.priority_ports_placeholder": {"ru": "например: 11434, 8765", "en": "e.g.: 11434, 8765"},
    "settings.priority_status_file": {"ru": "Файл состояния (необязательно)", "en": "Status file (optional)"},
    "settings.priority_status_file_placeholder": {"ru": "путь к JSON-файлу с {\"state\":..., \"updated\":...}", "en": "path to a JSON file with {\"state\":..., \"updated\":...}"},
    "settings.priority_vram_mb": {"ru": "Нужно видеопамяти, МБ", "en": "VRAM it needs, MB"},
    "settings.priority_ram_gb": {"ru": "Нужно оперативной памяти, ГБ", "en": "RAM it needs, GB"},
    "settings.models_title": {"ru": "Модели", "en": "Models"},
    "settings.models_hint": {
        "ru": "Выбери, какая модель за что отвечает — из уже скачанных в папку Nexus. "
              "Подействует после «Остановить» → «Запустить».",
        "en": "Pick which model does what — from what's already downloaded into Nexus's own folder. "
              "Takes effect after Stop → Start."},
    "settings.models_refresh": {"ru": "Обновить список", "en": "Refresh list"},
    "settings.models_unavailable": {
        "ru": "Список недоступен — похоже, движок Nexus сейчас не запущен. Можно ввести имя модели вручную.",
        "en": "List unavailable — Nexus's engine doesn't seem to be running right now. You can still type a model name by hand."},
    "settings.models_pull_title": {"ru": "Скачать новую модель", "en": "Download a new model"},
    "settings.models_pull_hint": {
        "ru": "Имя модели как в Ollama (например, qwen3.5:9b). Скачается в свою папку Nexus. "
              "Может занять долго и пойдёт в общую очередь задач.",
        "en": "Model name as in Ollama (e.g. qwen3.5:9b). Downloads into Nexus's own folder. "
              "Can take a while and goes through the normal task queue."},
    "settings.models_pull_placeholder": {"ru": "Имя модели", "en": "Model name"},
    "settings.models_pull_btn": {"ru": "Скачать", "en": "Download"},
    "settings.models_pulling": {"ru": "Скачивается… (не закрывай страницу)", "en": "Downloading… (don't close this page)"},
    "settings.models_pull_done": {"ru": "Готово. Обновляю список…", "en": "Done. Refreshing the list…"},
    "settings.models_pull_failed": {"ru": "Не удалось скачать", "en": "Download failed"},
    "settings.pause_programs_title": {"ru": "Свои программы для паузы", "en": "Your own pause programs"},
    "settings.pause_programs_hint": {
        "ru": "Пока запущена любая из них — Nexus тоже на паузе, как во время игр из списка выше.",
        "en": "While any of these runs, Nexus pauses too, same as during the games above."},
    "settings.pause_programs_placeholder": {"ru": "Имя файла, например: obs64.exe", "en": "File name, e.g.: obs64.exe"},
    "settings.pause_programs_add": {"ru": "Добавить", "en": "Add"},
    "settings.pause_programs_empty": {"ru": "Пока ничего своего не добавлено.", "en": "Nothing added yet."},
    "settings.pause_programs_remove": {"ru": "убрать", "en": "remove"},

    "mode.fast": {"ru": "Быстро, не так подробно", "en": "Fast, less detailed"},
    "mode.balanced": {"ru": "Сбалансированно", "en": "Balanced"},
    "mode.thorough": {"ru": "Дольше, но тщательнее", "en": "Slower, more thorough"},

    "status.confirmed": {"ru": "Подтверждено", "en": "Confirmed"},
    "status.partial": {"ru": "Частично", "en": "Partial"},
    "status.unverified": {"ru": "Не проверено", "en": "Unverified"},
    "status.disputed": {"ru": "Оспаривается", "en": "Disputed"},
    "status.pending": {"ru": "Ожидает проверки", "en": "Awaiting review"},
    "badge.low_reliability": {"ru": "НИЗКАЯ НАДЁЖНОСТЬ ИСТОЧНИКА", "en": "LOW SOURCE RELIABILITY"},

    "help.btn_label": {"ru": "Справка", "en": "Help"},
    "help.close": {"ru": "Закрыть", "en": "Close"},

    "help.home.title": {"ru": "Главная — как читать", "en": "Home — how to read it"},
    "help.home.body": {
        "ru": "• Карточка приоритетной программы показывает, не мешает ли ей Nexus прямо сейчас — это важнее всего.\n"
              "• «Запустить» / «Пауза» / «Остановить с сохранением» по-настоящему управляют работой, не для вида.\n"
              "• «Свежее» — последние разобранные материалы; «Подробно» открывает полный разбор, не просто ссылку.",
        "en": "• The priority-app card shows whether Nexus is bothering it right now — that's the most important thing.\n"
              "• Start / Pause / Stop-and-save really control the work, not just for show.\n"
              "• \"Recent\" shows the latest processed materials; \"Details\" opens the full write-up, not just a link."},

    "help.research.title": {"ru": "Исследования — как пользоваться", "en": "Research — how to use it"},
    "help.research.body": {
        "ru": "• Материалы сгруппированы по дням — кликни на день, чтобы развернуть или свернуть.\n"
              "• Сверху — переход к конкретной дате через обычный календарь.\n"
              "• «Коротко» у каждого дня просит модель сжать все материалы в несколько пунктов — не для чтения всего подряд.\n"
              "• Чипы сверху фильтруют по теме.",
        "en": "• Materials are grouped by day — click a day to expand or collapse it.\n"
              "• At the top, jump to a specific date with the regular calendar picker.\n"
              "• \"Brief\" on each day asks the model to compress all of that day's materials into a few points — no need to read everything.\n"
              "• The chips at the top filter by topic."},

    "help.conductor.title": {"ru": "Дирижёр — как пользоваться", "en": "Conductor — how to use it"},
    "help.conductor.body": {
        "ru": "• Пиши поручение обычными словами — Nexus сам возьмётся, как только освободится видеокарта и приоритетная программа не против.\n"
              "• Поручения важнее обычных планов Nexus, но не важнее приоритетной программы.\n"
              "• Чем конкретнее поручение («сравни X и Y», «объясни Z простыми словами»), тем точнее ответ — общие фразы дают общий ответ.\n"
              "• Когда готово — придёт уведомление Windows, не нужно сидеть и ждать на странице.",
        "en": "• Write an errand in plain words — Nexus picks it up once the GPU is free and the priority app doesn't mind.\n"
              "• Errands outrank Nexus's regular plans, but never the priority app.\n"
              "• The more specific the errand (\"compare X and Y\", \"explain Z simply\"), the sharper the answer — vague asks get vague answers.\n"
              "• A Windows notification arrives when it's done — no need to sit and watch the page."},

    "help.interests.title": {"ru": "Интересы — как пользоваться", "en": "Interests — how to use it"},
    "help.interests.body": {
        "ru": "• Список тем, которыми занимается Nexus, по приоритету.\n"
              "• Включать/выключать и менять приоритет — в Настройках.\n"
              "• Новую тему тоже добавляешь в Настройках: название, короткое описание и ключевые слова.\n"
              "• Ключевые слова — самое важное: без них тема никогда ничего не найдёт. Пиши и по-русски, и по-английски, частями слов («нейросет» поймает «нейросети»).",
        "en": "• The list of topics Nexus works on, by priority.\n"
              "• Enable/disable and change priority in Settings.\n"
              "• Add a new topic in Settings too: name, short description and keywords.\n"
              "• Keywords matter most — without them a topic never catches anything. Write both Russian and English, as word stems."},

    "help.memory.title": {"ru": "Память — как пользоваться", "en": "Memory — how to use it"},
    "help.memory.body": {
        "ru": "• Здесь выводы, которые Nexus уже сделал по темам — обновляются, когда появляется новое.\n"
              "• Поиск пока только по словам, не по смыслу (поиск по смыслу работает внутри, для объединения похожих тем).\n"
              "• «Подробно» показывает полный отчёт и историю изменений темы.",
        "en": "• The conclusions Nexus has already drawn per topic — updated whenever something new comes in.\n"
              "• Search is by words only for now, not meaning (semantic search runs internally, to merge similar topics).\n"
              "• \"Details\" shows the full report and the topic's change history."},

    "help.sources.title": {"ru": "Источники — как пользоваться", "en": "Sources — how to use it"},
    "help.sources.body": {
        "ru": "• Список источников, которые Nexus проверяет и собирает.\n"
              "• Можно добавить свой: название, ссылка на RSS-ленту и зачем он нужен — модель подскажет, похож ли он на надёжный (решение всегда за тобой).\n"
              "• Удаление — кнопка «Удалить», подтверждение вторым нажатием в течение нескольких секунд.",
        "en": "• The list of sources Nexus checks and gathers from.\n"
              "• You can add your own: name, RSS feed link and why you want it — the model will note whether it looks solid (the decision is always yours).\n"
              "• Deleting needs a second click within a few seconds to confirm."},

    "help.settings.title": {"ru": "Настройки — как пользоваться", "en": "Settings — how to use it"},
    "help.settings.body": {
        "ru": "• Приоритетная программа: название, процессы/порты, по которым её определять, фото — пустое название выключает всю функцию.\n"
              "• Язык панели, пресет исследования (быстро/сбалансированно/тщательно) и свой стиль письма.\n"
              "• Темы: включение, приоритет, добавление и удаление своих.\n"
              "• Свои программы для паузы — Nexus встанет на паузу, пока запущена любая из них (сверх списка игр).\n"
              "• Модели — выбираются прямо здесь, из уже скачанных в папку Nexus; новую можно скачать той же кнопкой.",
        "en": "• Priority app: name, processes/ports to detect it by, photo — leave the name empty to turn the whole feature off.\n"
              "• Panel language, research preset (fast/balanced/thorough) and your own writing style.\n"
              "• Topics: enable, priority, add and delete your own.\n"
              "• Your own pause programs — Nexus pauses while any of them runs (on top of the games list).\n"
              "• Models — pick right here, from what's already downloaded into Nexus's folder; the same button downloads a new one."},

    "nav.activity": {"ru": "Журнал", "en": "Activity"},
    "activity.title": {"ru": "Журнал", "en": "Activity"},
    "activity.subtitle": {"ru": "Что Nexus делал в последнее время — для прозрачности, не для красоты",
                           "en": "What Nexus has been doing lately — for transparency, not decoration"},
    "activity.col_time": {"ru": "Время", "en": "Time"},
    "activity.col_kind": {"ru": "Вид", "en": "Kind"},
    "activity.col_task": {"ru": "Задача", "en": "Task"},
    "activity.col_state": {"ru": "Стало", "en": "Became"},
    "activity.col_reason": {"ru": "Причина", "en": "Reason"},
    "activity.empty": {"ru": "Пока пусто — Nexus ещё ничего не делал.", "en": "Nothing yet — Nexus hasn't done anything."},
    "activity.kind.probe": {"ru": "Проверка", "en": "Probe"},
    "activity.kind.errand": {"ru": "Дирижёр", "en": "Conductor"},
    "activity.kind.source_review": {"ru": "Оценка источника", "en": "Source review"},
    "activity.kind.triage": {"ru": "Отбор", "en": "Triage"},
    "activity.kind.digest": {"ru": "Выжимка", "en": "Digest"},
    "activity.kind.credibility": {"ru": "Достоверность", "en": "Credibility"},
    "activity.kind.overview": {"ru": "Коротко", "en": "Overview"},
    "activity.kind.memory": {"ru": "Память", "en": "Memory"},
    "activity.kind.pull_model": {"ru": "Загрузка модели", "en": "Model download"},
    "activity.state.QUEUED": {"ru": "в очереди", "en": "queued"},
    "activity.state.RUNNING": {"ru": "выполняется", "en": "running"},
    "activity.state.PAUSED": {"ru": "на паузе", "en": "paused"},
    "activity.state.INTERRUPTED": {"ru": "прервано", "en": "interrupted"},
    "activity.state.COMPLETED": {"ru": "готово", "en": "completed"},
    "activity.state.FAILED": {"ru": "ошибка", "en": "failed"},
    "activity.state.CANCELLED": {"ru": "отменено", "en": "cancelled"},

    "help.activity.title": {"ru": "Журнал — как читать", "en": "Activity — how to read it"},
    "help.activity.body": {
        "ru": "• Каждая строка — переход задачи из одного состояния в другое: что это была за задача и почему.\n"
              "• Это просто прозрачность — что Nexus реально делал, без прикрас. Если что-то падало с ошибкой, здесь будет видно, почему.\n"
              "• Не вся история хранится вечно — показаны последние события.",
        "en": "• Each row is a task moving from one state to another: what the task was and why.\n"
              "• This is pure transparency — what Nexus actually did, no spin. If something failed, you'll see why here.\n"
              "• Not forever — this shows the most recent events."},

    "memory_detail.download": {"ru": "Скачать как текст", "en": "Download as text"},

    "integrity.warning_title": {"ru": "Защищённый код изменился с последней проверки",
                                 "en": "Protected code changed since the last check"},
    "integrity.warning_hint": {"ru": "Проверьте, кто и зачем это сделал, прежде чем продолжать. "
                                      "Если изменение ваше и осознанное — запустите: python -m nexus lock-integrity",
                                "en": "Check who did this and why before continuing. If the change is yours "
                                      "and intentional — run: python -m nexus lock-integrity"},
}

# Внутренний код статуса → ключ перевода (коды — на русском исторически, в БД их не менять).
STATUS_KEY = {
    "ПОДТВЕРЖДЕНО": "status.confirmed",
    "ЧАСТИЧНО": "status.partial",
    "НЕ ПРОВЕРЕНО": "status.unverified",
    "ОСПАРИВАЕТСЯ": "status.disputed",
}
CONTROL_KEY = {
    "running": "control.running", "paused": "control.paused", "stopped": "control.stopped",
    "недоступно": "control.unavailable",
}


def current_lang() -> str:
    lang = config.load_settings().language
    return lang if lang in config.LANGUAGES else "ru"


def t(key: str, lang: str | None = None, **kwargs) -> str:
    lang = lang or current_lang()
    row = STRINGS.get(key)
    text = (row.get(lang) or row.get("ru") or key) if row else key
    return text.format(**kwargs) if kwargs else text


def status_label(status: str | None, lang: str | None = None) -> str:
    return t(STATUS_KEY.get(status, "status.pending"), lang)


def control_label(state: str, lang: str | None = None) -> str:
    return t(CONTROL_KEY.get(state, state), lang) if state in CONTROL_KEY else state
