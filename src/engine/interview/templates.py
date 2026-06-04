# src/engine/interview/templates.py
#
# Phase 24.3C — curated, natural multilingual interview templates (EN/HY/RU).
#
# These are HAND-AUTHORED for natural, professional phrasing — especially
# Armenian — rather than machine translation. They are deterministic (no LLM,
# no network) and contain no prompts, secrets, or provider logic. Placeholders:
# {skill}, {target}, {role}.

from __future__ import annotations

LANGS = ("en", "hy", "ru")

# ── Candidate practice questions, keyed by QuestionKind value ────────────────
CANDIDATE_QUESTIONS = {
    "missing_skill": {
        "en": ("This role expects {skill}, but it isn't clearly shown in your CV. Have you "
               "used it (or something similar), and how would you approach a task that needs it?"),
        "hy": ("Այս դերը ենթադրում է {skill}, սակայն դա հստակ չի երևում քո ինքնակենսագրականում։ "
               "Օգտագործե՞լ ես այն (կամ նմանատիպ բան), և ինչպե՞ս կմոտենայիր այդ հմտությունը "
               "պահանջող խնդրին։"),
        "ru": ("Эта роль предполагает {skill}, но это не отражено явно в вашем резюме. "
               "Использовали ли вы это (или нечто похожее) и как бы подошли к задаче, "
               "которая этого требует?"),
    },
    "matched_skill": {
        "en": ("Walk me through a project where you applied {skill}. What was your specific "
               "contribution and the measurable result?"),
        "hy": ("Մանրամասն ներկայացրո՛ւ մի նախագիծ, որտեղ կիրառել ես {skill}-ը։ Ո՞րն էր քո "
               "կոնկրետ ներդրումը և չափելի արդյունքը։"),
        "ru": ("Расскажите подробно о проекте, где вы применяли {skill}. В чём был ваш "
               "конкретный вклад и измеримый результат?"),
    },
    "general": {
        "en": "Tell me about a professional achievement you are proud of, and why it mattered.",
        "hy": "Պատմի՛ր մի մասնագիտական ձեռքբերման մասին, որով հպարտ ես, և ինչո՞ւ էր այն կարևոր։",
        "ru": "Расскажите о профессиональном достижении, которым вы гордитесь, и почему оно важно.",
    },
}

# ── Weak-dimension behavioral questions, keyed by the engine's dimension label ─
WEAK_DIMENSION = {
    "Technical Skills": {
        "en": "Walk me through the most technically challenging problem you solved recently and how you approached it.",
        "hy": "Քայլ առ քայլ ներկայացրո՛ւ վերջերս լուծած ամենաբարդ տեխնիկական խնդիրը և թե ինչպես մոտեցար դրան։",
        "ru": "Пошагово опишите самую сложную техническую задачу, которую вы недавно решили, и как вы к ней подошли.",
    },
    "Experience Depth": {
        "en": "Tell me about the most complex project you owned end to end — your role and the result.",
        "hy": "Պատմի՛ր ամենաբարդ նախագծի մասին, որը վարել ես սկզբից մինչև վերջ՝ քո դերը և արդյունքը։",
        "ru": "Расскажите о самом сложном проекте, который вы вели от начала до конца — вашу роль и результат.",
    },
    "Education": {
        "en": "How has your education or self-learning prepared you for this role's core tasks?",
        "hy": "Ինչպե՞ս են քո կրթությունը կամ ինքնակրթությունը նախապատրաստել քեզ այս դերի հիմնական խնդիրներին։",
        "ru": "Как ваше образование или самообучение подготовили вас к основным задачам этой роли?",
    },
    "Domain Knowledge": {
        "en": "What do you understand about this role's industry or domain, and how did you build that understanding?",
        "hy": "Ի՞նչ գիտես այս դերի ոլորտի մասին, և ինչպե՞ս ես ձեռք բերել այդ գիտելիքը։",
        "ru": "Что вы понимаете об отрасли этой роли и как вы сформировали это понимание?",
    },
    "Soft Skills": {
        "en": "Describe a time you handled a disagreement or a difficult collaboration on a team.",
        "hy": "Նկարագրի՛ր մի դեպք, երբ կարգավորել ես տարաձայնություն կամ բարդ համագործակցություն թիմում։",
        "ru": "Опишите случай, когда вы урегулировали разногласие или сложное сотрудничество в команде.",
    },
    "Seniority Fit": {
        "en": "What scope of responsibility have you held, and how has it grown over time?",
        "hy": "Ի՞նչ ծավալի պատասխանատվություն ես կրել, և ինչպե՞ս է այն աճել ժամանակի ընթացքում։",
        "ru": "Какой объём ответственности вы несли и как он рос со временем?",
    },
    "Contextual Alignment": {
        "en": "Why are you a fit for this specific role? Use concrete examples from your experience.",
        "hy": "Ինչո՞ւ ես հարմար հենց այս դերի համար։ Օգտագործի՛ր կոնկրետ օրինակներ քո փորձից։",
        "ru": "Почему вы подходите именно для этой роли? Приведите конкретные примеры из опыта.",
    },
}

_GENERIC_DIMENSION = {
    "en": "Describe a concrete example from your experience that shows your strength in this area.",
    "hy": "Նկարագրի՛ր քո փորձից մի կոնկրետ օրինակ, որը ցույց է տալիս քո ուժեղ կողմն այս ոլորտում։",
    "ru": "Опишите конкретный пример из опыта, показывающий вашу сильную сторону в этой области.",
}

# ── Candidate follow-ups, keyed by weakness reason ───────────────────────────
FOLLOWUPS = {
    "specificity": {
        "en": "Can you give a concrete example — with numbers, tools, and the outcome?",
        "hy": "Կարո՞ղ ես կոնկրետ օրինակ բերել՝ թվերով, գործիքներով և արդյունքով։",
        "ru": "Можете привести конкретный пример — с цифрами, инструментами и результатом?",
    },
    "relevance": {
        "en": "Let's focus specifically on {target}: describe one concrete example.",
        "hy": "Կենտրոնանա՛նք հատկապես {target}-ի վրա. նկարագրի՛ր մեկ կոնկրետ օրինակ։",
        "ru": "Давайте сфокусируемся именно на {target}: опишите один конкретный пример.",
    },
    "structure": {
        "en": "Re-tell that using STAR: Situation, Task, Action, Result.",
        "hy": "Վերապատմի՛ր այն STAR մեթոդով՝ Իրավիճակ, Խնդիր, Գործողություն, Արդյունք։",
        "ru": "Перескажите это по методу STAR: Ситуация, Задача, Действие, Результат.",
    },
}

# ── Answer feedback bands ────────────────────────────────────────────────────
BANDS = {
    "strong": {"en": "Strong answer.", "hy": "Ուժեղ պատասխան։", "ru": "Сильный ответ."},
    "adequate": {"en": "Adequate — it can be sharper.",
                 "hy": "Բավարար — կարող է ավելի սեղմ լինել։",
                 "ru": "Достаточно — можно сделать чётче."},
    "weak": {"en": "Needs work — add specifics.",
             "hy": "Կարիք ունի բարելավման — ավելացրո՛ւ մանրամասներ։",
             "ru": "Требует доработки — добавьте конкретику."},
}

# ── Recruiter verification, keyed by category (probe_gap | verify) ───────────
VERIFICATION = {
    "verify": {
        "question": {
            "en": ("Ask the candidate to describe a specific project where they used {skill}, "
                   "including their role and the key decisions they made."),
            "hy": ("Խնդրի՛ր թեկնածուին նկարագրել կոնկրետ նախագիծ, որտեղ օգտագործել է {skill}-ը՝ "
                   "նշելով իր դերն ու կայացրած հիմնական որոշումները։"),
            "ru": ("Попросите кандидата описать конкретный проект, где он использовал {skill}, "
                   "включая его роль и ключевые принятые решения."),
        },
        "strong": {
            "en": ["a concrete project that genuinely used {skill}",
                   "specific decisions and the candidate's personal role",
                   "measurable outcomes (numbers, performance, impact)"],
            "hy": ["կոնկրետ նախագիծ, որտեղ իրապես օգտագործվել է {skill}-ը",
                   "հստակ որոշումներ և թեկնածուի անձնական դերը",
                   "չափելի արդյունքներ (թվեր, արդյունավետություն, ազդեցություն)"],
            "ru": ["конкретный проект, где действительно использовался {skill}",
                   "конкретные решения и личная роль кандидата",
                   "измеримые результаты (цифры, эффективность, влияние)"],
        },
        "weak": {
            "en": ["vague or generic description with no specifics",
                   "no measurable outcome or unclear personal contribution",
                   "cannot explain {skill} choices → possibly overstated"],
            "hy": ["անորոշ կամ ընդհանրական նկարագրություն՝ առանց մանրամասների",
                   "չափելի արդյունքի բացակայություն կամ անհասկանալի անձնական ներդրում",
                   "չի կարողանում բացատրել {skill}-ի ընտրությունները → հնարավոր է չափազանցված"],
            "ru": ["расплывчатое или общее описание без конкретики",
                   "нет измеримого результата или неясен личный вклад",
                   "не может объяснить выбор {skill} → возможно, преувеличено"],
        },
        "followups": {
            "en": ["What problems did you hit with {skill}, and how did you resolve them?",
                   "What would you do differently in that {skill} work today?"],
            "hy": ["Ի՞նչ խնդիրների հանդիպեցիր {skill}-ի հետ, և ինչպե՞ս լուծեցիր դրանք։",
                   "Ի՞նչ կանեիր այլ կերպ այդ {skill}-ի աշխատանքում այսօր։"],
            "ru": ["С какими проблемами вы столкнулись с {skill} и как их решили?",
                   "Что бы вы сделали иначе в той работе с {skill} сегодня?"],
        },
    },
    "probe_gap": {
        "question": {
            "en": ("{skill} is required but not evident in the CV. Probe whether the candidate "
                   "can already do it or could ramp up quickly."),
            "hy": ("{skill}-ը պահանջվում է, բայց չի երևում ինքնակենսագրականում։ Ստուգի՛ր՝ արդյոք "
                   "թեկնածուն արդեն կարող է դա անել, թե կարող է արագ յուրացնել։"),
            "ru": ("{skill} требуется, но не виден в резюме. Выясните, умеет ли кандидат это уже "
                   "или сможет быстро освоить."),
        },
        "strong": {
            "en": ["prior exposure to {skill} or a close equivalent",
                   "a clear, realistic plan to become productive",
                   "transferable reasoning from related work"],
            "hy": ["{skill}-ի կամ նմանատիպ բանի հետ նախկին փորձ",
                   "հստակ, իրատեսական ծրագիր՝ արագ արդյունավետ դառնալու համար",
                   "փոխանցելի փորձ՝ հարակից աշխատանքից"],
            "ru": ["прежний опыт с {skill} или близким аналогом",
                   "чёткий реалистичный план быстро стать продуктивным",
                   "переносимые навыки из смежной работы"],
        },
        "weak": {
            "en": ["no awareness of {skill} and no related experience",
                   "overconfidence asserted without any evidence",
                   "no credible plan to close the gap"],
            "hy": ["{skill}-ի մասին պատկերացման բացակայություն և հարակից փորձ չունենալ",
                   "ինքնավստահություն՝ առանց որևէ ապացույցի",
                   "բացը փակելու հավաստի ծրագրի բացակայություն"],
            "ru": ["отсутствие представления о {skill} и смежного опыта",
                   "самоуверенность без каких-либо доказательств",
                   "нет убедительного плана закрыть пробел"],
        },
        "followups": {
            "en": ["Have you used anything functionally similar to {skill}?",
                   "How would you approach learning {skill} on the job?"],
            "hy": ["Օգտագործե՞լ ես {skill}-ին գործառականորեն նման որևէ բան։",
                   "Ինչպե՞ս կմոտենայիր {skill}-ը աշխատանքի ընթացքում սովորելուն։"],
            "ru": ["Использовали ли вы что-то функционально похожее на {skill}?",
                   "Как бы вы подошли к изучению {skill} в процессе работы?"],
        },
    },
}


def get_generic_dimension(lang: str) -> str:
    return _GENERIC_DIMENSION.get(lang, _GENERIC_DIMENSION["en"])
