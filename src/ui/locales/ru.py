# src/ui/locales/ru.py
# Russian translations (professional, hand-authored — not machine-translated).

STRINGS = {
    # Brand
    "app.name": "ArmeniaCareer AI",
    "app.tagline": "Карьерная аналитика",

    # Sidebar
    "sidebar.workspace": "Рабочая область",
    "sidebar.how_it_works": "Как это работает",
    "sidebar.language": "Язык",
    "sidebar.status": "Статус",
    "sidebar.disclaimer": (
        "Только поддержка решений. Перед любым решением о найме обязательна "
        "проверка человеком. Файлы обрабатываются локально и не сохраняются."
    ),

    # Modes
    "mode.candidate": "Кандидат",
    "mode.recruiter": "Рекрутер / HR",
    "mode.admin": "Админ · Демо",
    "mode.candidate.intro": "Проанализируйте и улучшите своё резюме (CV).",
    "mode.recruiter.intro": "Оцените кандидатов по вакансии.",
    "mode.admin.intro": "Внутреннее демо с локальными тестовыми данными.",
    "mode.admin.badge": "Внутренний демо-режим",

    # Heroes
    "hero.candidate.title": "Улучшите резюме и подготовьтесь к собеседованию",
    "hero.candidate.subtitle": (
        "Загрузите своё резюме для приватного локального анализа — "
        "качество, навыки, пробелы и практика."
    ),
    "hero.recruiter.title": "Ранжируйте кандидатов и проверяйте доказательства",
    "hero.recruiter.subtitle": (
        "Укажите описание вакансии, загрузите резюме кандидатов и просмотрите "
        "безопасное для рекрутера ранжирование."
    ),
    "hero.admin.title": "Внутреннее демо и инструменты управления",
    "hero.admin.subtitle": (
        "Запустите детерминированный конвейер на локальных тестовых данных и "
        "проверьте каждый слой."
    ),

    # Steppers
    "steps.candidate": ["CV", "Сравнить", "Результаты", "Практика", "Тест"],
    "steps.recruiter": ["JD", "Резюме", "Ранжирование", "Обзор", "Проверка"],
    "steps.admin": ["Выбрать данные", "Анализ", "Проверка", "Управление"],

    # Trust chips
    "trust.offline_ready": "Работает офлайн",
    "trust.deterministic_fallback": "Детерминированный резерв",
    "trust.private_excluded": "Приватные данные исключены",
    "trust.decision_support": "Только поддержка решений",
    "trust.no_auto_hiring": "Без автоматического найма",

    # Utility bar
    "util.reset": "Сбросить",
    "util.focus_mode": "Режим фокуса",
    "util.presentation_ready": "Готово к презентации",
    "util.print_hint": "Печать: Ctrl/Cmd + P",
    "util.workspace_prefix": "Область",

    # Status chips
    "status.local_only": "Только локально · не сохраняется",
    "status.local_data_safe": "Локальные данные защищены",
    "status.pool_protected": "Пул кандидатов защищён",
    "status.ingest_enabled": "Импорт: включён",
    "status.ingest_disabled": "Импорт: выключен",
    "status.fallback_ready": "Резерв готов · API опционально",
    "status.decision_support": "Только поддержка решений",
    "status.mode_prefix": "Режим",
    "status.provider_active": "ИИ-провайдер активен",
    "status.provider_fallback": "ИИ-провайдер недоступен — активен детерминированный резерв",

    # Candidate mode
    "candidate.cv_step": "Ваше резюме",
    "candidate.upload_cv": "Загрузите своё резюме",
    "candidate.format_caption": (
        "Принимается: PDF, DOCX, TXT, MD. Лучше всего работают текстовые PDF — "
        "сканированные/графические PDF могут быть помечены как низкое качество "
        "(OCR пока не реализован)."
    ),
    "candidate.no_cv_title": "Резюме ещё не загружено",
    "candidate.no_cv_hint": "Загрузите резюме, чтобы увидеть отчёт по нему.",
    "candidate.compare_step": "Сравнить с конкретной вакансией (опционально)",
    "candidate.results": "Результаты",
    "candidate.compare_button": "Сравнить с этой вакансией",

    # Recruiter mode
    "recruiter.no_cv_title": "Резюме кандидатов пока нет",
    "recruiter.no_cv_hint": "Загрузите хотя бы одно резюме кандидата, чтобы продолжить.",

    # Admin mode
    "admin.internal_notice": (
        "Внутренний демо-режим — использует локальные тестовые наборы в data/raw. "
        "Не для реальных кандидатов. Все четыре вкладки показаны для тестирования."
    ),
    "admin.disabled_notice": "Инструменты Админ / Демо отключены в этой среде.",

    # CV intelligence report (Candidate Mode)
    "cv.report.title": "Отчёт по анализу резюме",
    "cv.report.scanned_warning": (
        "Низкое качество извлечения — похоже на сканированный/графический PDF без "
        "текстового слоя. Загрузите текстовый PDF или DOCX для точного анализа."
    ),
    "cv.report.low_warning": (
        "Низкое качество извлечения — найдено очень мало читаемого текста. "
        "Результаты могут быть ненадёжными."
    ),
    "cv.report.partial_warning": (
        "Частичное извлечение — некоторые разделы могли быть не распознаны."
    ),
    "cv.report.quality_score": "Оценка качества резюме",
    "cv.report.skills_detected": "Найдено навыков",
    "cv.report.word_count": "Количество слов",
    "cv.report.sections": "Разделы",
    "cv.report.contact_info": "Контактные данные",
    "cv.report.work_experience": "Опыт работы",
    "cv.report.education": "Образование",
    "cv.report.skills": "Навыки",
    "cv.report.summary": "Резюме",
    "cv.report.present": "Да",
    "cv.report.missing": "Отсутствует",
    "cv.report.detected_skills": "Обнаруженные навыки",
    "cv.report.no_skills": (
        "Технические навыки не обнаружены. Добавьте чёткий раздел «Навыки»."
    ),
    "cv.report.languages": "Языки",
    "cv.report.role_directions": "Возможные направления ролей",
    "cv.report.improvement": "Рекомендации по улучшению",
    "cv.report.no_issues": (
        "Серьёзных структурных проблем не обнаружено. Прочная основа резюме."
    ),

    # CV layout / readability advisory (24.3E)
    "cv.layout.title": "Вёрстка и читаемость",
    "cv.layout.warn_template": (
        "Похоже, это резюме использует шаблонную/двухколоночную вёрстку. Сейчас оно "
        "читаемо, но некоторые ATS-системы могут распознавать его менее надёжно."
    ),
    "cv.layout.warn_visual_levels": (
        "Используйте чёткие текстовые обозначения уровней языков (например, B2, "
        "Свободно) вместо только визуальных звёзд/точек/полос."
    ),
    "cv.layout.warn_headings": (
        "Делайте заголовки разделов стандартными и выделяемыми текстом для надёжного "
        "распознавания."
    ),
    "cv.layout.warn_char_spaced": (
        "Текст извлечён с необычными межсимвольными пробелами; он был автоматически "
        "исправлен, но более чистый экспорт PDF или DOCX повышает надёжность."
    ),

    # Interview (candidate practice + recruiter verification)
    "interview.practice_title": "Практика собеседования",
    "interview.practice_notice": (
        "Режим практики — приватный, поддерживающий тренинг. Ваши ответы не сохраняются "
        "и не передаются."
    ),
    "interview.question": "Вопрос",
    "interview.answered": "Отвечено",
    "interview.avg_score": "Средний балл",
    "interview.target": "Цель",
    "interview.session_progress": "Прогресс сессии",
    "interview.on_track": "Вы на верном пути — средний балл достигает цели.",
    "interview.keep_going": "Продолжайте — стремитесь поднять средний балл к цели.",
    "interview.current_question": "Текущий вопрос",
    "interview.your_answer": "Ваш ответ",
    "interview.your_answer_prefix": "Ваш ответ",
    "interview.submit": "Отправить ответ",
    "interview.skip": "Пропустить вопрос",
    "interview.end": "Завершить сессию",
    "interview.write_answer": "Напишите ответ перед отправкой.",
    "interview.complete": "Сессия практики завершена. Просмотрите отзывы выше.",
    "interview.avg_answer_score": "Средний балл ответа",
    "interview.restart": "Начать практику заново",
    "interview.followup": "Уточняющий вопрос",
    "interview.verify_title": "Проверочное собеседование",
    "interview.verify_notice": (
        "Структурированное, основанное на доказательствах руководство для ручной оценки. "
        "Только поддержка решений — ответы оценивает рекрутер."
    ),
    "interview.no_questions": "Для этого анализа проверочные вопросы не сформированы.",
    "interview.strong_header": "Сильный ответ должен содержать",
    "interview.weak_header": "Слабые / неясные ответы могут указывать на",
    "interview.followups_header": "Рекомендуемые уточняющие вопросы",
    "interview.must_ask": "Обязательно спросить",
    "interview.recommended": "Рекомендуется",
    "interview.optional": "Опционально",

    # Interview rubric / evaluation quality (24.3D)
    "interview.rubric.title": "Оценка ответа",
    "interview.rubric.confidence": "Уверенность оценки",
    "interview.rubric.strengths": "Сильные стороны",
    "interview.rubric.improvements": "Области для улучшения",
    "interview.rubric.better": "Как сделать сильнее",
    "interview.rubric.learning": "Рекомендуемый фокус обучения",
    "interview.rubric.followup": "Полезный уточняющий вопрос",
    "interview.evidence_title": "Уверенность доказательств и что проверить",
    "interview.risk_signals": "Сигналы риска / пробелов",
    "interview.validate": "Что проверить на живом собеседовании",
    "interview.distinction_title": "Сигналы, рассматриваемые отдельно",
    "interview.dim.technical_correctness": "Техническая корректность",
    "interview.dim.depth": "Глубина",
    "interview.dim.relevance": "Релевантность",
    "interview.dim.clarity": "Ясность",
    "interview.dim.practical_example": "Практический пример",
    "interview.dim.communication": "Коммуникация",
    "interview.dim.confidence": "Выраженная уверенность",
    "interview.dim.gap_risk": "Риск пробела",
}
