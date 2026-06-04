# src/engine/interview/rubric.py
#
# Phase 24.3D — additive, deterministic interview RUBRIC layer.
#
# Produces a richer, multi-dimension evaluation on top of the interview engine
# WITHOUT modifying it: it derives eight bounded rubric dimensions, detects weak
# answer patterns, and emits localized (EN/HY/RU) candidate and recruiter
# feedback. No LLM, no network, no provider calls, no prompts/secrets.
#
# Anti-overclaim policy: recruiter-facing wording uses "suggests" / "may
# indicate" / "needs verification" and an explicit confidence band — never
# "definitely" / "proves".

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.engine.adapters import MVP_SKILL_ALIASES

_DEFAULT_LANG = "en"
_LANGS = ("en", "hy", "ru")

DIMENSIONS = [
    "technical_correctness", "depth", "relevance", "clarity",
    "practical_example", "communication", "confidence", "gap_risk",
]

_TOOL_NAMES = {name.lower() for name in MVP_SKILL_ALIASES}

_STAR_SITUATION = ("when", "at ", "during", "project", "team", "company", "role", "faced")
_STAR_ACTION = ("i ", "we ", "implemented", "built", "designed", "developed", "led",
                "created", "used", "wrote", "configured", "migrated", "optimized", "automated")
_STAR_RESULT = ("result", "outcome", "improved", "reduced", "increased", "achieved",
                "delivered", "saved", "grew", "%", "faster")
_REASON = ("because", "so that", "trade-off", "tradeoff", "decided", "therefore",
           "in order to", "chose", " why ")
_EXAMPLE = ("for example", "e.g", "such as", "we built", "i built", "client", "customer")
_HEDGE = ("maybe", "i think", "probably", "kind of", "sort of", "not sure", "i guess")
_ASSERT = ("definitely", "always", "expert", "best", "perfect", "mastered", "100%",
           "easily", "obviously", "everything")
_GENERIC = ("hard worker", "team player", "passionate", "fast learner",
            "good communication", "detail oriented", "i am motivated", "people person")


def _clamp(v: float) -> float:
    return round(max(0.0, min(1.0, v)), 3)


def _kind_value(kind: Any) -> str:
    return str(getattr(kind, "value", kind) or "general")


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------

@dataclass
class RubricResult:
    dimensions: Dict[str, float] = field(default_factory=dict)
    overall: float = 0.0
    band: str = "weak"               # strong | adequate | weak
    confidence_band: str = "low"     # low | medium | high (assessment confidence)
    flags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Deterministic evaluation
# ---------------------------------------------------------------------------

def evaluate_rubric(answer: str, question: Any = None) -> RubricResult:
    """Deterministically scores an answer across eight rubric dimensions. Never raises."""
    answer = answer or ""
    low = answer.lower()
    words = answer.split()
    wc = len(words)
    target = str(getattr(question, "target", "") or "")
    target_l = target.lower().strip()
    kind = _kind_value(getattr(question, "kind", "general"))

    has_number = bool(re.search(r"\d", answer))
    has_percent = "%" in answer
    tool_hits = sum(1 for n in _TOOL_NAMES if n in low)
    star = [
        any(c in low for c in _STAR_SITUATION),
        any(c in low for c in _STAR_ACTION),
        any(c in low for c in _STAR_RESULT),
    ]
    star_cats = sum(star)
    reasoning = any(c in low for c in _REASON)
    example_markers = any(c in low for c in _EXAMPLE) or has_number
    hedge = sum(1 for c in _HEDGE if c in low)
    assertive = sum(1 for c in _ASSERT if c in low)
    generic = any(c in low for c in _GENERIC)
    target_present = bool(target_l) and target_l in low
    target_tokens = [t for t in re.split(r"[^a-z0-9+#.]+", target_l) if len(t) > 2]
    target_token_hit = any(t in low for t in target_tokens)

    technical = _clamp(
        (0.5 if target_present else 0.0)
        + min(tool_hits, 3) * 0.13
        + (0.12 if any(c in low for c in _STAR_ACTION) else 0.0)
    )
    depth = _clamp(min(wc / 60.0, 1.0) * 0.5 + (star_cats / 3.0) * 0.3 + (0.2 if reasoning else 0.0))
    if target_present:
        relevance = 0.9
    elif target_token_hit:
        relevance = 0.6
    elif any(w in low for w in ("project", "experience", "role", "system", "data", "team", "code")):
        relevance = 0.4
    else:
        relevance = 0.2
    clarity = _clamp(0.8 if 15 <= wc <= 180 else 0.5 if wc >= 8 else 0.3)
    practical_example = _clamp(0.85 if example_markers else 0.2)
    communication = _clamp((star_cats / 3.0) * 0.6 + (0.2 if "i " in low else 0.0)
                           + (0.2 if star[2] else 0.0))
    confidence = _clamp(0.5 + assertive * 0.12 - hedge * 0.1)

    gap_risk = 0.0
    if relevance < 0.3:
        gap_risk += 0.5
    if wc < 8:
        gap_risk += 0.4
    if confidence > 0.6 and practical_example < 0.4:
        gap_risk += 0.4
    if generic and practical_example < 0.5:
        gap_risk += 0.2
    gap_risk = _clamp(gap_risk)

    dims = {
        "technical_correctness": technical, "depth": depth, "relevance": relevance,
        "clarity": clarity, "practical_example": practical_example,
        "communication": communication, "confidence": confidence, "gap_risk": gap_risk,
    }

    positive = ["technical_correctness", "depth", "relevance", "clarity",
                "practical_example", "communication"]
    overall = _clamp(sum(dims[d] for d in positive) / len(positive))
    band = "strong" if overall >= 0.62 else "adequate" if overall >= 0.40 else "weak"

    # Assessment confidence — how much we trust this evaluation, NOT a verdict.
    if wc < 12:
        confidence_band = "low"
    elif wc >= 40 and (has_number or star_cats >= 2):
        confidence_band = "high"
    else:
        confidence_band = "medium"

    flags: List[str] = []
    if wc < 12:
        flags.append("too_short_shallow")
    if practical_example < 0.4 and depth < 0.45:
        flags.append("vague")
    if generic and practical_example < 0.5:
        flags.append("generic_memorized")
    if relevance < 0.3:
        flags.append("irrelevant")
    if relevance < 0.4 and target_l and not target_present and not target_token_hit:
        flags.append("does_not_address")
    if practical_example < 0.4:
        flags.append("no_practical_example")
    if not has_number and not has_percent:
        flags.append("no_measurable_detail")
    if target_l and not target_present and kind in ("missing_skill", "matched_skill"):
        flags.append("missing_key_concept")
    if confidence > 0.6 and practical_example < 0.4:
        flags.append("overconfident_unsupported")

    return RubricResult(
        dimensions=dims, overall=overall, band=band,
        confidence_band=confidence_band, flags=flags,
    )


# ---------------------------------------------------------------------------
# Localized content
# ---------------------------------------------------------------------------

def _pick(block: Dict[str, str], lang: str) -> str:
    return block.get(lang) or block.get(_DEFAULT_LANG, "")


_BAND = {
    "strong": {"en": "Strong", "hy": "Ուժեղ", "ru": "Сильный"},
    "adequate": {"en": "Adequate", "hy": "Բավարար", "ru": "Достаточный"},
    "weak": {"en": "Needs work", "hy": "Կարիք ունի բարելավման", "ru": "Требует доработки"},
}
_CONF = {
    "low": {"en": "low", "hy": "ցածր", "ru": "низкая"},
    "medium": {"en": "medium", "hy": "միջին", "ru": "средняя"},
    "high": {"en": "high", "hy": "բարձր", "ru": "высокая"},
}
_DIM_STRENGTH = {
    "technical_correctness": {"en": "Technically grounded and specific.",
                              "hy": "Տեխնիկապես հիմնավորված և կոնկրետ։",
                              "ru": "Технически обоснованно и конкретно."},
    "depth": {"en": "Good depth and reasoning.",
              "hy": "Լավ խորություն և հիմնավորում։",
              "ru": "Хорошая глубина и аргументация."},
    "relevance": {"en": "Stays on topic and answers the question.",
                  "hy": "Մնում է թեմայի մեջ և պատասխանում հարցին։",
                  "ru": "По теме и отвечает на вопрос."},
    "clarity": {"en": "Clearly and concisely expressed.",
                "hy": "Հստակ և սեղմ ձևակերպված։",
                "ru": "Изложено ясно и кратко."},
    "practical_example": {"en": "Backed by a concrete example.",
                          "hy": "Հիմնված կոնկրետ օրինակի վրա։",
                          "ru": "Подкреплено конкретным примером."},
    "communication": {"en": "Well structured (situation → action → result).",
                      "hy": "Լավ կառուցված (իրավիճակ → գործողություն → արդյունք)։",
                      "ru": "Хорошо структурировано (ситуация → действие → результат)."},
}
_DIM_IMPROVE = {
    "technical_correctness": {"en": "Name the specific tools/techniques you used.",
                              "hy": "Նշի՛ր կոնկրետ գործիքները/մեթոդները, որ օգտագործել ես։",
                              "ru": "Назовите конкретные инструменты/методы, которые вы использовали."},
    "depth": {"en": "Explain the why and the trade-offs behind your decisions.",
              "hy": "Բացատրի՛ր որոշումներիդ պատճառներն ու փոխզիջումները։",
              "ru": "Объясните «почему» и компромиссы за вашими решениями."},
    "relevance": {"en": "Tie the answer directly to the question's topic.",
                  "hy": "Կապի՛ր պատասխանը ուղղակիորեն հարցի թեմայի հետ։",
                  "ru": "Свяжите ответ напрямую с темой вопроса."},
    "clarity": {"en": "Keep it structured — avoid one long, dense block.",
                "hy": "Պահի՛ր կառուցվածքը — խուսափի՛ր մեկ երկար, խիտ պարբերությունից։",
                "ru": "Сохраняйте структуру — избегайте одного длинного плотного блока."},
    "practical_example": {"en": "Add a concrete example with the outcome.",
                          "hy": "Ավելացրո՛ւ կոնկրետ օրինակ՝ արդյունքով։",
                          "ru": "Добавьте конкретный пример с результатом."},
    "communication": {"en": "Use STAR: Situation, Task, Action, Result.",
                      "hy": "Օգտագործի՛ր STAR՝ Իրավիճակ, Խնդիր, Գործողություն, Արդյունք։",
                      "ru": "Используйте STAR: Ситуация, Задача, Действие, Результат."},
}
_FLAG_MSG = {
    "vague": {"en": "The answer is vague — add specifics.",
              "hy": "Պատասխանը անորոշ է — ավելացրո՛ւ մանրամասներ։",
              "ru": "Ответ расплывчатый — добавьте конкретику."},
    "generic_memorized": {"en": "It sounds generic/memorized — make it personal and specific.",
                          "hy": "Հնչում է ընդհանրական/անգիր — դարձրո՛ւ անձնական և կոնկրետ։",
                          "ru": "Звучит шаблонно/заученно — сделайте личным и конкретным."},
    "irrelevant": {"en": "The answer drifts off topic.",
                   "hy": "Պատասխանը շեղվում է թեմայից։",
                   "ru": "Ответ уходит от темы."},
    "does_not_address": {"en": "It does not clearly address what was asked.",
                         "hy": "Այն հստակ չի պատասխանում հարցին։",
                         "ru": "Он не отвечает чётко на заданный вопрос."},
    "no_practical_example": {"en": "No practical example was given.",
                             "hy": "Գործնական օրինակ չի բերվել։",
                             "ru": "Не приведён практический пример."},
    "no_measurable_detail": {"en": "No measurable detail (numbers, %, impact).",
                             "hy": "Չափելի մանրամասն չկա (թվեր, %, ազդեցություն)։",
                             "ru": "Нет измеримых деталей (цифры, %, влияние)."},
    "missing_key_concept": {"en": "A key concept for this question is missing.",
                            "hy": "Այս հարցի համար կարևոր հասկացություն բացակայում է։",
                            "ru": "Отсутствует ключевое понятие для этого вопроса."},
    "too_short_shallow": {"en": "The answer is too short to assess well.",
                          "hy": "Պատասխանը չափազանց կարճ է լավ գնահատելու համար։",
                          "ru": "Ответ слишком короткий для надёжной оценки."},
    "overconfident_unsupported": {"en": "Confident but unsupported — add evidence.",
                                  "hy": "Վստահ, բայց չհիմնավորված — ավելացրո՛ւ ապացույց։",
                                  "ru": "Уверенно, но без подтверждения — добавьте доказательства."},
}
_GUIDANCE = {
    "strong": {"en": "Keep this level of concrete detail across your other answers.",
               "hy": "Պահպանի՛ր այս կոնկրետության մակարդակը մյուս պատասխաններում։",
               "ru": "Сохраняйте этот уровень конкретики и в других ответах."},
    "adequate": {"en": "Add one concrete example with a measurable outcome to make it convincing.",
                 "hy": "Ավելացրո՛ւ մեկ կոնկրետ օրինակ՝ չափելի արդյունքով, որպեսզի համոզիչ լինի։",
                 "ru": "Добавьте один конкретный пример с измеримым результатом, чтобы было убедительно."},
    "weak": {"en": "Re-answer using a real example: situation, what you did, and the result.",
             "hy": "Վերապատասխանի՛ր իրական օրինակով՝ իրավիճակ, ինչ արեցիր, և արդյունք։",
             "ru": "Ответьте заново на реальном примере: ситуация, что вы сделали и результат."},
}
_LEARNING = {"en": "Practice articulating concrete {skill} examples with measurable results.",
             "hy": "Մարզվի՛ր ներկայացնելու կոնկրետ {skill} օրինակներ՝ չափելի արդյունքներով։",
             "ru": "Тренируйтесь излагать конкретные примеры {skill} с измеримыми результатами."}
_LEARNING_GENERIC = {"en": "the role's core skills", "hy": "դերի հիմնական հմտությունները",
                     "ru": "ключевые навыки роли"}
_FOLLOWUP = {
    "practical_example": {"en": "Can you give one concrete example with numbers and the outcome?",
                          "hy": "Կարո՞ղ ես մեկ կոնկրետ օրինակ բերել՝ թվերով և արդյունքով։",
                          "ru": "Можете привести один конкретный пример с цифрами и результатом?"},
    "relevance": {"en": "How does that connect directly to the question?",
                  "hy": "Ինչպե՞ս է դա ուղղակիորեն կապված հարցի հետ։",
                  "ru": "Как это напрямую связано с вопросом?"},
    "depth": {"en": "Why did you take that approach, and what were the trade-offs?",
              "hy": "Ինչո՞ւ ընտրեցիր այդ մոտեցումը, և որո՞նք էին փոխզիջումները։",
              "ru": "Почему вы выбрали такой подход и какие были компромиссы?"},
    "technical_correctness": {"en": "Which specific tools or techniques did you use?",
                              "hy": "Կոնկրետ ո՞ր գործիքները կամ մեթոդներն օգտագործեցիր։",
                              "ru": "Какие именно инструменты или методы вы использовали?"},
}


# ---------------------------------------------------------------------------
# Candidate feedback (localized)
# ---------------------------------------------------------------------------

def candidate_rubric_feedback(rubric: RubricResult, question: Any, lang: Optional[str]) -> Dict[str, Any]:
    lang = lang if lang in _LANGS else _DEFAULT_LANG
    target = str(getattr(question, "target", "") or "")
    dims = rubric.dimensions

    strengths = [_pick(_DIM_STRENGTH[d], lang) for d in _DIM_STRENGTH
                 if dims.get(d, 0.0) >= 0.6][:3]
    improvements: List[str] = [_pick(_DIM_IMPROVE[d], lang) for d in _DIM_IMPROVE
                               if dims.get(d, 0.0) < 0.5][:3]
    for flag in rubric.flags:
        if flag in _FLAG_MSG and _pick(_FLAG_MSG[flag], lang) not in improvements:
            improvements.append(_pick(_FLAG_MSG[flag], lang))
    improvements = improvements[:5]

    # Weakest positive dimension drives the follow-up + learning focus.
    weakest = min(_FOLLOWUP, key=lambda d: dims.get(d, 1.0))
    skill = target or _pick(_LEARNING_GENERIC, lang)

    return {
        "band": _pick(_BAND[rubric.band], lang),
        "score": round(rubric.overall * 100),
        "dimensions": dims,
        "strengths": strengths,
        "improvements": improvements,
        "better_answer": _pick(_GUIDANCE[rubric.band], lang),
        "learning_focus": _pick(_LEARNING, lang).format(skill=skill),
        "follow_up": _pick(_FOLLOWUP[weakest], lang),
        "confidence_band": _pick(_CONF[rubric.confidence_band], lang),
    }


# ---------------------------------------------------------------------------
# Recruiter evidence-confidence summary (read-only over recruiter_view)
# ---------------------------------------------------------------------------

_RISK_VERIFY = {"en": "Verify {skill} with a concrete, first-hand example.",
                "hy": "Ստուգի՛ր {skill}-ը կոնկրետ, անձնական օրինակով։",
                "ru": "Проверьте {skill} на конкретном личном примере."}
_VALIDATE = {
    "en": ["Ask for a specific project and the candidate's exact role.",
           "Probe for measurable outcomes (numbers, impact).",
           "Confidence is directional — confirm depth in the live interview."],
    "hy": ["Հարցրո՛ւ կոնկրետ նախագիծ և թեկնածուի ճշգրիտ դերը։",
           "Ստուգի՛ր չափելի արդյունքները (թվեր, ազդեցություն)։",
           "Վստահությունն ուղղորդիչ է — հաստատի՛ր խորությունը կենդանի հարցազրույցում։"],
    "ru": ["Спросите конкретный проект и точную роль кандидата.",
           "Уточните измеримые результаты (цифры, влияние).",
           "Уверенность ориентировочная — подтвердите глубину на живом собеседовании."],
}
_DIST = {
    "cv_quality": {"en": "CV quality — how well the CV is structured and complete.",
                   "hy": "CV-ի որակ — որքանով է CV-ն կառուցված և ամբողջական։",
                   "ru": "Качество резюме — насколько резюме структурировано и полно."},
    "jd_match": {"en": "JD match — overlap of CV evidence with the job's requirements.",
                 "hy": "JD համապատասխանություն — CV-ի ապացույցների համընկնումը պահանջների հետ։",
                 "ru": "Соответствие вакансии — совпадение данных резюме с требованиями."},
    "skill_depth": {"en": "Skill-depth confidence — directional, heuristic (not a verdict).",
                    "hy": "Հմտության խորության վստահություն — ուղղորդիչ, էվրիստիկ (ոչ վճիռ)։",
                    "ru": "Уверенность по глубине навыков — ориентировочная, эвристическая (не вердикт)."},
    "interview_perf": {"en": "Interview performance — assessed only in the live interview.",
                       "hy": "Հարցազրույցի կատարում — գնահատվում է միայն կենդանի հարցազրույցում։",
                       "ru": "Результаты собеседования — оцениваются только на живом собеседовании."},
}


def recruiter_confidence_summary(recruiter_view: Dict[str, Any], lang: Optional[str]) -> Dict[str, Any]:
    """
    A read-only, anti-overclaim summary from recruiter-facing data: an evidence
    confidence band, gap/risk signals, what to validate, and the four signals
    kept explicitly separate. Does not change scoring or access control.
    """
    lang = lang if lang in _LANGS else _DEFAULT_LANG
    skills = recruiter_view.get("skills_ontology")
    coverage = float(getattr(skills, "coverage_ratio", 0.0) or 0.0) if skills else 0.0
    missing = []
    if skills is not None:
        for e in getattr(skills, "missing_critical", []) or []:
            name = getattr(e, "canonical_name", None) or getattr(e, "skill_name", None)
            if name:
                missing.append(name)
    completeness = float(recruiter_view.get("analysis_completeness_score", 1.0) or 1.0)

    if missing or coverage < 0.4 or completeness < 0.6:
        conf = "low"
    elif coverage >= 0.7 and completeness >= 0.9 and not missing:
        conf = "high"
    else:
        conf = "medium"

    risk_signals = [_pick(_RISK_VERIFY, lang).format(skill=s) for s in missing[:5]]
    return {
        "confidence_band": _pick(_CONF[conf], lang),
        "risk_signals": risk_signals,
        "validate": list(_VALIDATE.get(lang, _VALIDATE["en"])),
        "distinction": {k: _pick(v, lang) for k, v in _DIST.items()},
    }
