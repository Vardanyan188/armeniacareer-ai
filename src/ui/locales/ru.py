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
}
