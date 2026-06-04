# src/ui/locales/hy.py
# Armenian translations (professional, hand-authored — not machine-translated).

STRINGS = {
    # Brand
    "app.name": "ArmeniaCareer AI",
    "app.tagline": "Կարիերային ինտելեկտ",

    # Sidebar
    "sidebar.workspace": "Աշխատանքային տիրույթ",
    "sidebar.how_it_works": "Ինչպես է աշխատում",
    "sidebar.language": "Լեզու",
    "sidebar.status": "Կարգավիճակ",
    "sidebar.disclaimer": (
        "Միայն որոշումների աջակցություն։ Աշխատանքի ընդունման ցանկացած որոշումից "
        "առաջ պարտադիր է մարդկային վերանայումը։ Ֆայլերը մշակվում են տեղում և չեն պահվում։"
    ),

    # Modes
    "mode.candidate": "Թեկնածու",
    "mode.recruiter": "Հավաքագրող / HR",
    "mode.admin": "Ադմին · Դեմո",
    "mode.candidate.intro": "Վերլուծի՛ր և բարելավի՛ր քո ինքնակենսագրականը (CV)։",
    "mode.recruiter.intro": "Գնահատի՛ր թեկնածուներին ըստ թափուր աշխատատեղի։",
    "mode.admin.intro": "Ներքին դեմո՝ տեղական նմուշային տվյալներով։",
    "mode.admin.badge": "Ներքին դեմո ռեժիմ",

    # Heroes
    "hero.candidate.title": "Բարելավի՛ր քո CV-ն և պատրաստվի՛ր հարցազրույցին",
    "hero.candidate.subtitle": (
        "Վերբեռնի՛ր քո CV-ն մասնավոր, տեղական վերլուծության համար՝ "
        "որակ, հմտություններ, բացեր և պրակտիկա։"
    ),
    "hero.recruiter.title": "Դասակարգի՛ր թեկնածուներին և ստուգի՛ր ապացույցները",
    "hero.recruiter.subtitle": (
        "Տրամադրի՛ր աշխատանքի նկարագրությունը, վերբեռնի՛ր թեկնածուների CV-ները և "
        "դիտի՛ր հավաքագրողի համար անվտանգ դասակարգումը։"
    ),
    "hero.admin.title": "Ներքին դեմո և կառավարման գործիքներ",
    "hero.admin.subtitle": (
        "Գործարկի՛ր դետերմինիստական հոսքը տեղական նմուշային տվյալների վրա և "
        "ստուգի՛ր բոլոր շերտերը։"
    ),

    # Steppers
    "steps.candidate": ["CV", "Համեմատել", "Արդյունքներ", "Պրակտիկա", "Թեստ"],
    "steps.recruiter": ["JD", "CV-ներ", "Դասակարգում", "Վերանայում", "Ստուգում"],
    "steps.admin": ["Ընտրել տվյալներ", "Վերլուծել", "Ստուգել", "Կառավարում"],

    # Trust chips
    "trust.offline_ready": "Աշխատում է առանց ինտերնետի",
    "trust.deterministic_fallback": "Դետերմինիստական պահեստային տարբերակ",
    "trust.private_excluded": "Մասնավոր տվյալները բացառված են",
    "trust.decision_support": "Միայն որոշումների աջակցություն",
    "trust.no_auto_hiring": "Առանց ավտոմատ ընդունման",

    # Utility bar
    "util.reset": "Վերակայել",
    "util.focus_mode": "Կենտրոնացման ռեժիմ",
    "util.presentation_ready": "Պատրաստ ներկայացման",
    "util.print_hint": "Տպել՝ Ctrl/Cmd + P",
    "util.workspace_prefix": "Տիրույթ",

    # Status chips
    "status.local_only": "Միայն տեղական · չի պահվում",
    "status.local_data_safe": "Տեղական տվյալները պաշտպանված են",
    "status.pool_protected": "Թեկնածուների շտեմարանը պաշտպանված է",
    "status.ingest_enabled": "Ներմուծում՝ միացված",
    "status.ingest_disabled": "Ներմուծում՝ անջատված",
    "status.fallback_ready": "Պահեստային՝ պատրաստ · API-ն ընտրովի",
    "status.decision_support": "Միայն որոշումների աջակցություն",
    "status.mode_prefix": "Ռեժիմ",

    # Candidate mode
    "candidate.cv_step": "Քո CV-ն",
    "candidate.upload_cv": "Վերբեռնի՛ր քո CV-ն",
    "candidate.format_caption": (
        "Ընդունվում է՝ PDF, DOCX, TXT, MD։ Տեքստային PDF-ները լավագույնն են. "
        "սկանավորված/պատկերային PDF-ները կարող են նշվել որպես ցածր որակ "
        "(OCR-ը դեռ իրականացված չէ)։"
    ),
    "candidate.no_cv_title": "Դեռ CV վերբեռնված չէ",
    "candidate.no_cv_hint": "Վերբեռնի՛ր CV՝ քո CV-ի վերլուծությունը տեսնելու համար։",
    "candidate.compare_step": "Համեմատի՛ր կոնկրետ աշխատանքի հետ (ընտրովի)",
    "candidate.results": "Արդյունքներ",
    "candidate.compare_button": "Համեմատել այս աշխատանքի հետ",

    # Recruiter mode
    "recruiter.no_cv_title": "Դեռ թեկնածուի CV չկա",
    "recruiter.no_cv_hint": "Շարունակելու համար վերբեռնի՛ր առնվազն մեկ թեկնածուի CV։",

    # Admin mode
    "admin.internal_notice": (
        "Ներքին դեմո ռեժիմ — օգտագործում է data/raw-ի տեղական նմուշները։ "
        "Ոչ իրական թեկնածուների համար։ Բոլոր չորս ներդիրները ցուցադրվում են փորձարկման համար։"
    ),
    "admin.disabled_notice": "Ադմին / Դեմո գործիքներն այս միջավայրում անջատված են։",

    # CV intelligence report (Candidate Mode)
    "cv.report.title": "CV-ի վերլուծության հաշվետվություն",
    "cv.report.scanned_warning": (
        "Ցածր արդյունահանման որակ — սա հավանաբար սկանավորված/պատկերային PDF է՝ առանց "
        "տեքստային շերտի։ Ճշգրիտ վերլուծության համար վերբեռնի՛ր տեքստային PDF կամ DOCX։"
    ),
    "cv.report.low_warning": (
        "Ցածր արդյունահանման որակ — գտնվել է շատ քիչ ընթեռնելի տեքստ։ "
        "Արդյունքները կարող են անվստահելի լինել։"
    ),
    "cv.report.partial_warning": (
        "Մասնակի արդյունահանում — որոշ բաժիններ կարող են չհայտնաբերվել։"
    ),
    "cv.report.quality_score": "CV-ի որակի գնահատական",
    "cv.report.skills_detected": "Հայտնաբերված հմտություններ",
    "cv.report.word_count": "Բառերի քանակ",
    "cv.report.sections": "Բաժիններ",
    "cv.report.contact_info": "Կոնտակտային տվյալներ",
    "cv.report.work_experience": "Աշխատանքային փորձ",
    "cv.report.education": "Կրթություն",
    "cv.report.skills": "Հմտություններ",
    "cv.report.summary": "Ամփոփագիր",
    "cv.report.present": "Այո",
    "cv.report.missing": "Բացակայում է",
    "cv.report.detected_skills": "Հայտնաբերված հմտություններ",
    "cv.report.no_skills": (
        "Տեխնիկական հմտություններ չեն հայտնաբերվել։ Ավելացրո՛ւ հստակ Հմտություններ բաժին։"
    ),
    "cv.report.languages": "Լեզուներ",
    "cv.report.role_directions": "Հնարավոր մասնագիտական ուղղություններ",
    "cv.report.improvement": "Բարելավման առաջարկներ",
    "cv.report.no_issues": (
        "Կառուցվածքային էական խնդիրներ չեն հայտնաբերվել։ Ամուր CV-ի հիմք։"
    ),

    # Interview (candidate practice + recruiter verification)
    "interview.practice_title": "Հարցազրույցի պրակտիկա",
    "interview.practice_notice": (
        "Պրակտիկայի ռեժիմ — մասնավոր, աջակցող մարզում։ Քո պատասխանները չեն պահվում և չեն կիսվում։"
    ),
    "interview.question": "Հարց",
    "interview.answered": "Պատասխանված",
    "interview.avg_score": "Միջին գնահատական",
    "interview.target": "Թիրախ",
    "interview.session_progress": "Սեսիայի առաջընթաց",
    "interview.on_track": "Լավ ընթացքի մեջ ես — միջինը համապատասխանում է թիրախին։",
    "interview.keep_going": "Շարունակի՛ր — ձգտի՛ր բարձրացնել միջինը դեպի թիրախը։",
    "interview.current_question": "Ընթացիկ հարց",
    "interview.your_answer": "Քո պատասխանը",
    "interview.your_answer_prefix": "Քո պատասխանը",
    "interview.submit": "Ուղարկել պատասխանը",
    "interview.skip": "Բաց թողնել հարցը",
    "interview.end": "Ավարտել սեսիան",
    "interview.write_answer": "Նախքան ուղարկելը գրի՛ր պատասխան։",
    "interview.complete": "Պրակտիկայի սեսիան ավարտված է։ Վերանայի՛ր վերևի արձագանքը։",
    "interview.avg_answer_score": "Պատասխանի միջին գնահատական",
    "interview.restart": "Վերսկսել պրակտիկան",
    "interview.followup": "Հետևողական հարց",
    "interview.verify_title": "Ստուգման հարցազրույց",
    "interview.verify_notice": (
        "Կառուցվածքային, ապացույցների վրա հիմնված ստուգման ուղեցույց՝ ձեռքով գնահատման համար։ "
        "Միայն որոշումների աջակցություն — պատասխանները գնահատում է հավաքագրողը։"
    ),
    "interview.no_questions": "Այս վերլուծության համար ստուգման հարցեր չեն ստեղծվել։",
    "interview.strong_header": "Ուժեղ պատասխանը պետք է պարունակի",
    "interview.weak_header": "Թույլ / անհասկանալի պատասխանները կարող են վկայել",
    "interview.followups_header": "Առաջարկվող հետևողական հարցեր",
    "interview.must_ask": "Պարտադիր հարցնել",
    "interview.recommended": "Խորհուրդ է տրվում",
    "interview.optional": "Ընտրովի",
}
