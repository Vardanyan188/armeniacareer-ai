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
}
