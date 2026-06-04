# src/preprocessing/cv_preprocessor.py
#
# Multilingual CV text preprocessing pipeline.
#
# Operational logic overview:
#   Pass 1 — Encoding normalization (Unicode NFC, Armenian charset repair)
#   Pass 2 — Structural noise removal (headers/footers, page numbers, watermarks)
#   Pass 3 — Line reconstruction (broken PDF extraction artifacts)
#   Pass 4 — Section segmentation (multi-language header detection)
#   Pass 5 — Token budget allocation (proportional to section info density)
#   Pass 6 — Anomaly flagging (populates CVFormatQualitySignals)
#
# The "geometric" property of the pipeline: each pass operates on the OUTPUT
# of the previous pass, forming a composition chain. The token budget allocation
# in Pass 5 uses an entropy-weighted proportional distribution — sections with
# higher information entropy receive a proportionally larger share of the total
# context budget. This prevents high-verbosity but low-signal sections (e.g.,
# a verbose "Objective" paragraph) from consuming context at the expense of
# dense work history entries.
#
# All methods are synchronous. The async wrapper `preprocess_async` is a thin
# executor bridge for use inside asyncio.gather() in the orchestrator.

from __future__ import annotations

import asyncio
import logging
import math
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Maximum token budget for the entire preprocessed CV text passed to the LLM.
# GPT-4.1-mini context: 128k tokens. CV budget: conservative 4,000 tokens
# (leaves headroom for system prompt, JD text, few-shot examples, output).
CV_MAX_TOKENS: int = 4_000

# Approximate chars-per-token ratio for multilingual (Armenian/Russian/English) text.
# Armenian Hayots Gir characters are multi-byte in UTF-8 but count as 1–2 tokens each.
# Conservative estimate: 2.8 chars/token for mixed Armenian/Latin, 2.5 for Cyrillic.
CHARS_PER_TOKEN_ARMENIAN: float = 2.8
CHARS_PER_TOKEN_CYRILLIC: float = 2.5
CHARS_PER_TOKEN_LATIN: float = 4.0

# Minimum chars to retain from any section, even if budget is exhausted.
MIN_SECTION_CHARS: int = 200

# Noise patterns — strings that appear in PDF exports but carry zero semantic value.
_NOISE_LINE_PATTERNS = [
    re.compile(r"^\s*\d+\s*$"),                           # Lone page numbers
    re.compile(r"^\s*Page\s+\d+(\s+of\s+\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*Էջ\s+\d+\s*$"),                      # Armenian page label
    re.compile(r"^\s*Страница\s+\d+\s*$", re.IGNORECASE), # Russian page label
    re.compile(r"^[-=_\s]{4,}$"),                          # Divider lines
    re.compile(r"^\s*Curriculum Vitae\s*$", re.IGNORECASE),
    re.compile(r"^\s*RESUME\s*$", re.IGNORECASE),
    re.compile(r"^\s*CV\s*$"),
    re.compile(r"^\s*Ինքնակենսագրական\s*$"),              # Armenian "CV" label
    re.compile(r"^\s*Резюме\s*$", re.IGNORECASE),         # Russian "resume"
]

# Armenian character Unicode range (Hayots Gir block).
_ARMENIAN_RANGE_START = 0x0531
_ARMENIAN_RANGE_END   = 0x058F

# Cyrillic character range.
_CYRILLIC_RANGE_START = 0x0400
_CYRILLIC_RANGE_END   = 0x04FF

# Section header vocabularies across all three languages.
# Keys are normalized section labels used downstream.
_SECTION_HEADERS: Dict[str, List[re.Pattern]] = {
    "work_experience": [
        re.compile(r"^(work\s+experience|experience|professional\s+experience|employment|employment\s+history)\s*:?\s*$", re.IGNORECASE),
        re.compile(r"^(աշխատանքային\s+փորձ|փորձ|մասնագիտական\s+փորձ)\s*:?\s*$"),
        re.compile(r"^(опыт\s+работы|опыт|профессиональный\s+опыт|трудовая\s+деятельность)\s*:?\s*$", re.IGNORECASE),
    ],
    "education": [
        re.compile(r"^(education|academic\s+background|qualifications)\s*:?\s*$", re.IGNORECASE),
        re.compile(r"^(կրթություն|ակադեմիական\s+կրթություն)\s*:?\s*$"),
        re.compile(r"^(образование|учёба|академическое\s+образование)\s*:?\s*$", re.IGNORECASE),
    ],
    "skills": [
        re.compile(r"^(skills|technical\s+skills|core\s+competencies|expertise)\s*:?\s*$", re.IGNORECASE),
        re.compile(r"^(հմտություններ|տեխնիկական\s+հմտություններ|կարողություններ)\s*:?\s*$"),
        re.compile(r"^(навыки|технические\s+навыки|компетенции|умения)\s*:?\s*$", re.IGNORECASE),
    ],
    "languages": [
        re.compile(r"^(languages|language\s+skills|language\s+proficiency)\s*:?\s*$", re.IGNORECASE),
        re.compile(r"^(լեզուներ|լեզվի\s+իմացություն)\s*:?\s*$"),
        re.compile(r"^(языки|знание\s+языков|иностранные\s+языки)\s*:?\s*$", re.IGNORECASE),
    ],
    "certifications": [
        re.compile(r"^(certifications?|certificates?|licenses?|credentials?)\s*:?\s*$", re.IGNORECASE),
        re.compile(r"^(հավաստագրեր|վկայականներ)\s*:?\s*$"),
        re.compile(r"^(сертификаты?|удостоверения?|лицензии)\s*:?\s*$", re.IGNORECASE),
    ],
    "projects": [
        re.compile(r"^(projects?|personal\s+projects?|side\s+projects?|portfolio)\s*:?\s*$", re.IGNORECASE),
        re.compile(r"^(նախագծեր|անձնական\s+նախագծեր)\s*:?\s*$"),
        re.compile(r"^(проекты|личные\s+проекты|портфолио)\s*:?\s*$", re.IGNORECASE),
    ],
    "summary": [
        re.compile(r"^(summary|profile|objective|about\s+me|professional\s+summary)\s*:?\s*$", re.IGNORECASE),
        re.compile(r"^(ամփոփում|ինձ\s+մասին|նպատակ)\s*:?\s*$"),
        re.compile(r"^(краткое\s+резюме|о\s+себе|цель|профиль)\s*:?\s*$", re.IGNORECASE),
    ],
    "contact": [
        re.compile(r"^(contact|contact\s+information|personal\s+information)\s*:?\s*$", re.IGNORECASE),
        re.compile(r"^(կոնտակտ|կոնտակտային\s+տվյալներ)\s*:?\s*$"),
        re.compile(r"^(контакты|контактная\s+информация)\s*:?\s*$", re.IGNORECASE),
    ],
}

# Section priority weights for token budget allocation.
# Higher weight → larger share of the total CV_MAX_TOKENS budget.
_SECTION_BUDGET_WEIGHTS: Dict[str, float] = {
    "work_experience":  0.38,
    "skills":           0.22,
    "education":        0.18,
    "certifications":   0.08,
    "projects":         0.07,
    "languages":        0.04,
    "summary":          0.02,
    "contact":          0.01,
}


# ---------------------------------------------------------------------------
# Data Structures
# ---------------------------------------------------------------------------

@dataclass
class CVSection:
    """A segmented section of a CV with its normalized label and content."""
    label: str           # Key from _SECTION_HEADERS, or "unknown"
    raw_header: str      # The detected header line as found in text
    content: str         # Section body text (header stripped)
    char_count: int      = 0
    entropy: float       = 0.0      # Character-level Shannon entropy
    token_budget: int    = 0        # Allocated token budget (chars)
    is_truncated: bool   = False    # True if content was cut to fit budget


@dataclass
class PreprocessingResult:
    """Output of the full preprocessing pipeline."""
    cleaned_text: str                           # Final text for LLM input
    sections: List[CVSection]                   # Segmented sections (ordered)
    primary_script: str                         # 'armenian' | 'cyrillic' | 'latin' | 'mixed'
    detected_languages: List[str]               # e.g. ['Armenian', 'Russian', 'English']
    section_headers_found: List[str]            # Raw header strings
    anomalies: List[str]                        # Anomaly labels
    total_input_chars: int                      # Before cleaning
    total_output_chars: int                     # After cleaning + truncation
    chars_per_token_estimate: float             # Used for budget calculation
    estimated_output_tokens: int                # Final token estimate
    preprocessing_confidence: float            # [0.0, 1.0]


# ---------------------------------------------------------------------------
# Core Preprocessor Class
# ---------------------------------------------------------------------------

class CVTextPreprocessor:
    """
    Multi-pass text preprocessing pipeline for CV inputs.

    Usage:
        preprocessor = CVTextPreprocessor()
        result = preprocessor.preprocess(raw_cv_text)
        # result.cleaned_text → pass to LLM
        # result.sections     → pass to format_quality model fields

    Async usage (within asyncio.gather):
        result = await preprocessor.preprocess_async(raw_cv_text)
    """

    def __init__(
        self,
        max_tokens: int = CV_MAX_TOKENS,
        strict_deduplication: bool = True,
    ):
        self.max_tokens = max_tokens
        self.strict_deduplication = strict_deduplication

    # -----------------------------------------------------------------------
    # Public Entry Points
    # -----------------------------------------------------------------------

    def preprocess(self, raw_text: str) -> PreprocessingResult:
        """Synchronous preprocessing pipeline. Returns a PreprocessingResult."""
        total_input_chars = len(raw_text)

        # Pass 1: Unicode normalization and encoding repair
        text = self._normalize_unicode(raw_text)

        # Pass 2: Structural noise removal
        text = self._remove_structural_noise(text)

        # Pass 3: Line reconstruction for PDF artifacts
        text, anomalies_line = self._reconstruct_broken_lines(text)

        # Pass 4: Section segmentation
        sections = self._segment_sections(text)

        # Pass 5: Script and language detection
        primary_script = self._detect_primary_script(text)
        detected_languages = self._detect_languages(text)
        chars_per_token = self._estimate_chars_per_token(primary_script)

        # Pass 6: Token budget allocation and truncation
        sections, budget_anomalies = self._allocate_token_budget(
            sections, chars_per_token
        )

        # Reconstruct final cleaned text from budgeted sections
        cleaned_text = self._reconstruct_from_sections(sections)

        # Pass 7: Anomaly aggregation
        anomalies = self._collect_anomalies(
            raw_text, text, sections, anomalies_line, budget_anomalies, primary_script
        )

        # Confidence calculation
        confidence = max(0.1, 1.0 - len(anomalies) * 0.08)

        return PreprocessingResult(
            cleaned_text=cleaned_text,
            sections=sections,
            primary_script=primary_script,
            detected_languages=detected_languages,
            section_headers_found=[s.raw_header for s in sections if s.raw_header],
            anomalies=anomalies,
            total_input_chars=total_input_chars,
            total_output_chars=len(cleaned_text),
            chars_per_token_estimate=chars_per_token,
            estimated_output_tokens=int(len(cleaned_text) / chars_per_token),
            preprocessing_confidence=confidence,
        )

    async def preprocess_async(self, raw_text: str) -> PreprocessingResult:
        """Async wrapper — runs synchronous preprocess in a thread executor."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self.preprocess, raw_text)

    # -----------------------------------------------------------------------
    # Pass 1: Unicode Normalization
    # -----------------------------------------------------------------------

    def _normalize_unicode(self, text: str) -> str:
        """
        Normalizes Unicode to NFC form, which is the canonical composed form.
        This resolves decomposed Armenian characters (common in legacy fonts like
        ArialAMU and ARMSCII conversions) where ե (U+0565) + ւ (U+057E) would
        appear as two code points instead of the composed form.

        Also repairs common Windows-1252 → UTF-8 misread artifacts:
        â€™ → ', â€œ → ", etc.
        """
        # NFC normalization (composing decomposed characters)
        text = unicodedata.normalize("NFC", text)

        # Repair Windows-1252 artifacts common in .docx → .txt conversions
        _WINDOWS_ARTIFACTS = {
            "\u00e2\u0080\u0099": "\u2019",  # â€™ → right single quote
            "\u00e2\u0080\u009c": "\u201c",  # â€œ → left double quote
            "\u00e2\u0080\u009d": "\u201d",  # â€  → right double quote
            "\u00e2\u0080\u00a6": "\u2026",  # â€¦ → ellipsis
            "\u00e2\u0080\u0093": "\u2013",  # â€" → en-dash
            "\u00e2\u0080\u0094": "\u2014",  # â€" → em-dash
            "\u00c3\u00a9": "\u00e9",        # Ã© → é
            "\u00c3\u00a0": "\u00e0",        # Ã  → à
            "\u00c3\u00bc": "\u00fc",        # Ã¼ → ü
            "\u00a0": " ",   # Non-breaking space → regular space
            "\u200b": "",    # Zero-width space → remove
            "\ufeff": "",    # BOM → remove
            "\u200c": "",    # Zero-width non-joiner → remove
        }
        for artifact, replacement in _WINDOWS_ARTIFACTS.items():
            text = text.replace(artifact, replacement)

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Normalize multiple consecutive blank lines to at most two
        text = re.sub(r"\n{3,}", "\n\n", text)

        return text

    # -----------------------------------------------------------------------
    # Pass 2: Structural Noise Removal
    # -----------------------------------------------------------------------

    def _remove_structural_noise(self, text: str) -> str:
        """
        Removes lines that match known noise patterns (page numbers, dividers,
        standalone CV/Resume labels). Preserves relative line structure.
        """
        lines = text.split("\n")
        cleaned_lines = []
        for line in lines:
            stripped = line.strip()
            is_noise = any(pattern.match(stripped) for pattern in _NOISE_LINE_PATTERNS)
            if not is_noise:
                cleaned_lines.append(line)
        return "\n".join(cleaned_lines)

    # -----------------------------------------------------------------------
    # Pass 3: Line Reconstruction
    # -----------------------------------------------------------------------

    def _reconstruct_broken_lines(self, text: str) -> Tuple[str, List[str]]:
        """
        Repairs broken lines introduced by PDF column extraction.

        PDF text extraction often produces:
            "Responsible for developing backend ser"
            "vices using FastAPI and PostgreSQL"

        Detection heuristic: a line ending with a lowercase letter or a
        letter followed by a comma/hyphen that is directly continued on the
        next non-empty line with a lowercase letter → merge.

        Edge case: Armenian text does not capitalize sentence starts consistently —
        use character context rather than capitalization signals.
        """
        anomalies = []
        lines = text.split("\n")
        merged_lines = []
        i = 0
        merge_count = 0

        while i < len(lines):
            current = lines[i]
            current_stripped = current.rstrip()

            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # Conditions for merging:
                # 1. Current line ends with a letter (not punctuation or digit)
                # 2. Current line is "short" — below the median line length threshold
                # 3. Next line starts with a lowercase letter OR Armenian continuation
                should_merge = (
                    len(current_stripped) > 5 and
                    len(current_stripped) < 60 and  # Typical broken line length
                    next_line and
                    current_stripped and
                    re.search(r"[a-zA-Z\u0561-\u0587\u0430-\u044F]$", current_stripped) and
                    re.match(r"^[a-z\u0561-\u0587\u0430-\u044F]", next_line)
                )
                if should_merge:
                    # Merge: join with space if the current line doesn't end with a hyphen
                    connector = "" if current_stripped.endswith("-") else " "
                    lines[i + 1] = current_stripped + connector + next_line
                    merge_count += 1
                    i += 1
                    continue

            merged_lines.append(lines[i])
            i += 1

        if merge_count > 5:
            anomalies.append("broken_lines")
            logger.debug("Reconstructed %d broken line pairs.", merge_count)

        return "\n".join(merged_lines), anomalies

    # -----------------------------------------------------------------------
    # Pass 4: Section Segmentation
    # -----------------------------------------------------------------------

    def _segment_sections(self, text: str) -> List[CVSection]:
        """
        Segments the CV text into labeled sections using multi-language header detection.

        Strategy:
        1. Scan each line against all header patterns in _SECTION_HEADERS.
        2. A line matches a header pattern if it is predominantly all-uppercase,
           or matches a compiled regex pattern, or is followed by a blank line
           and preceded by a blank line (structural isolation signal).
        3. Sections are emitted when a new header is detected.
        4. Text before the first recognized header is labeled "preamble"
           (contact info, name, summary candidate).
        """
        lines = text.split("\n")
        sections: List[CVSection] = []
        current_label = "preamble"
        current_header = ""
        current_lines: List[str] = []

        def emit_section():
            nonlocal current_label, current_header, current_lines
            content = "\n".join(current_lines).strip()
            if content:
                entropy = self._compute_text_entropy(content)
                sec = CVSection(
                    label=current_label,
                    raw_header=current_header,
                    content=content,
                    char_count=len(content),
                    entropy=entropy,
                )
                sections.append(sec)

        for line in lines:
            stripped = line.strip()
            detected_label = self._match_section_header(stripped)
            if detected_label:
                emit_section()
                current_label = detected_label
                current_header = stripped
                current_lines = []
            else:
                current_lines.append(line)

        emit_section()  # Emit last section

        if not sections:
            # No section structure detected — treat entire text as a single unknown section
            logger.warning("No section headers detected. CV may be unstructured or plain text.")
            entropy = self._compute_text_entropy(text)
            sections = [CVSection(
                label="unknown",
                raw_header="",
                content=text,
                char_count=len(text),
                entropy=entropy,
            )]

        return sections

    def _match_section_header(self, line: str) -> Optional[str]:
        """
        Tests a line against all section header patterns.
        Returns the section label if matched, None otherwise.

        Pre-processing applied before matching:
          - Strip leading Markdown heading characters (# / ## / ###)
          - Strip leading/trailing whitespace and trailing colon
          - Lowercase for pattern comparison (Armenian, Cyrillic, and Latin
            all support Unicode case folding via str.lower())

        Additional heuristic: a line that is fully uppercase, 3–40 chars,
        and contains no digits is likely a section header — labeled "unknown_header".
        """
        if not line:
            return None

        # Strip Markdown heading prefixes
        normalized = re.sub(r"^#{1,4}\s*", "", line).strip().rstrip(":").strip()

        if not normalized:
            return None

        # Lowercase version for pattern matching only
        normalized_lower = normalized.lower()

        for label, patterns in _SECTION_HEADERS.items():
            for pattern in patterns:
                if pattern.match(normalized_lower):
                    return label

        # Heuristic: all-uppercase short line with only letter characters
        non_space = normalized.replace(" ", "")
        if (
            3 <= len(non_space) <= 40 and
            non_space == non_space.upper() and
            not re.search(r"\d", non_space) and
            re.search(r"[A-ZԱ-Ֆ]", non_space)
        ):
            return "unknown_header"

        return None

    # -----------------------------------------------------------------------
    # Pass 5: Token Budget Allocation (Entropy-Weighted)
    # -----------------------------------------------------------------------

    def _allocate_token_budget(
        self,
        sections: List[CVSection],
        chars_per_token: float,
    ) -> Tuple[List[CVSection], List[str]]:
        """
        Allocates the total character budget across sections using an
        entropy-weighted proportional distribution.

        Mathematical formulation:
            For section i with base_weight w_i and entropy H_i:
                adjusted_weight_i = w_i * (1 + alpha * H_i)
            where alpha = 0.3 (entropy amplification factor — sections with higher
            information density receive a proportional bonus).

            Final allocation:
                budget_chars_i = (adjusted_weight_i / sum(adjusted_weights)) * total_char_budget

            total_char_budget = max_tokens * chars_per_token

        This ensures that a dense skills section (high entropy from diverse tool names)
        receives proportionally more budget than a verbose but low-entropy summary paragraph.

        Hard floor: every section receives at least MIN_SECTION_CHARS characters.
        """
        anomalies = []
        total_char_budget = int(self.max_tokens * chars_per_token)
        alpha = 0.3  # Entropy amplification factor

        # Map sections to base weights
        section_weights: List[float] = []
        for sec in sections:
            base_w = _SECTION_BUDGET_WEIGHTS.get(sec.label, 0.05)
            adjusted_w = base_w * (1.0 + alpha * min(sec.entropy, 4.0) / 4.0)
            section_weights.append(adjusted_w)

        total_weight = sum(section_weights)
        if total_weight == 0:
            section_weights = [1.0 / len(sections)] * len(sections)
            total_weight = 1.0

        # Proportional allocation with hard floor enforcement
        raw_allocations = [
            max(MIN_SECTION_CHARS, int((w / total_weight) * total_char_budget))
            for w in section_weights
        ]

        # Redistribute: if a section's content is shorter than its allocation,
        # return the surplus to the pool (allocated to work_experience first).
        surplus = 0
        for i, sec in enumerate(sections):
            if sec.char_count < raw_allocations[i]:
                surplus += raw_allocations[i] - sec.char_count
                raw_allocations[i] = sec.char_count

        # Assign surplus to work_experience (highest priority)
        for i, sec in enumerate(sections):
            if sec.label == "work_experience" and surplus > 0:
                raw_allocations[i] += surplus
                surplus = 0
                break

        # Apply allocations and truncate at sentence boundary
        for i, sec in enumerate(sections):
            sec.token_budget = raw_allocations[i]
            if sec.char_count > raw_allocations[i]:
                sec.content = self._truncate_at_boundary(sec.content, raw_allocations[i])
                sec.is_truncated = True
                anomalies.append(f"truncated:{sec.label}")
                logger.debug(
                    "Section '%s' truncated: %d → %d chars.",
                    sec.label, sec.char_count, raw_allocations[i],
                )

        return sections, anomalies

    def _truncate_at_boundary(self, text: str, max_chars: int) -> str:
        """
        Truncates text to max_chars at the nearest sentence boundary.
        Respects Armenian (։), Russian/English (. ! ?) sentence terminators.
        If no boundary is found within 20% of max_chars, truncates hard.
        """
        if len(text) <= max_chars:
            return text

        truncated = text[:max_chars]
        # Sentence boundary characters: full stop, exclamation, question, Armenian full stop
        boundary_pattern = re.compile(r"[.!?։]\s")
        search_from = int(max_chars * 0.80)
        boundaries = list(boundary_pattern.finditer(truncated[search_from:]))
        if boundaries:
            last_boundary = boundaries[-1]
            cut_pos = search_from + last_boundary.end()
            return truncated[:cut_pos].rstrip()

        # Hard truncate
        return truncated.rstrip()

    # -----------------------------------------------------------------------
    # Script and Language Detection
    # -----------------------------------------------------------------------

    def _detect_primary_script(self, text: str) -> str:
        """
        Classifies the dominant writing script using Unicode block membership.
        Counts non-whitespace, non-punctuation characters in each block.
        """
        armenian_count = 0
        cyrillic_count = 0
        latin_count = 0

        for char in text:
            cp = ord(char)
            if not char.isspace() and char.isalpha():
                if _ARMENIAN_RANGE_START <= cp <= _ARMENIAN_RANGE_END:
                    armenian_count += 1
                elif _CYRILLIC_RANGE_START <= cp <= _CYRILLIC_RANGE_END:
                    cyrillic_count += 1
                elif 0x0041 <= cp <= 0x007A or 0x00C0 <= cp <= 0x024F:
                    latin_count += 1

        total = max(armenian_count + cyrillic_count + latin_count, 1)
        arm_ratio = armenian_count / total
        cyr_ratio = cyrillic_count / total
        lat_ratio = latin_count / total

        if arm_ratio >= 0.40:
            return "armenian"
        elif cyr_ratio >= 0.40:
            return "cyrillic"
        elif lat_ratio >= 0.60:
            return "latin"
        else:
            return "mixed"

    def _detect_languages(self, text: str) -> List[str]:
        """
        Detects natural languages present in the text based on script analysis
        and lexical markers. Returns English names of detected languages.
        """
        languages = []
        lower_text = text.lower()

        # Armenian detection: script or Armenian-specific lexical markers
        armenian_count = sum(
            1 for c in text
            if _ARMENIAN_RANGE_START <= ord(c) <= _ARMENIAN_RANGE_END
        )
        if armenian_count > 20:
            languages.append("Armenian")

        # Russian detection: Cyrillic characters + Russian-specific stopwords
        cyrillic_count = sum(
            1 for c in text
            if _CYRILLIC_RANGE_START <= ord(c) <= _CYRILLIC_RANGE_END
        )
        russian_markers = ["опыт", "образование", "навыки", "работа", "по"]
        if cyrillic_count > 20 or any(m in lower_text for m in russian_markers):
            languages.append("Russian")

        # English detection: Latin script + common English function words
        english_markers = ["experience", "education", "skills", "and", "the", "for"]
        latin_count = sum(1 for c in text if 0x0041 <= ord(c) <= 0x007A)
        if latin_count > 50 or any(m in lower_text for m in english_markers):
            languages.append("English")

        return languages if languages else ["Unknown"]

    def _estimate_chars_per_token(self, primary_script: str) -> float:
        """Returns chars-per-token estimate based on dominant script."""
        return {
            "armenian": CHARS_PER_TOKEN_ARMENIAN,
            "cyrillic":  CHARS_PER_TOKEN_CYRILLIC,
            "latin":     CHARS_PER_TOKEN_LATIN,
            "mixed":     (CHARS_PER_TOKEN_ARMENIAN + CHARS_PER_TOKEN_LATIN) / 2,
        }.get(primary_script, CHARS_PER_TOKEN_LATIN)

    # -----------------------------------------------------------------------
    # Information Entropy Computation
    # -----------------------------------------------------------------------

    @staticmethod
    def _compute_text_entropy(text: str) -> float:
        """
        Computes Shannon entropy of the character distribution in a text block.
        Used as a proxy for information density:
          - High entropy (H > 3.5): diverse vocabulary, technical terms, varied skills
          - Low entropy (H < 2.5): repetitive or sparse text (e.g., headers, short summaries)

        H = -Σ p(c) * log2(p(c))  where c ranges over unique characters.
        """
        if not text:
            return 0.0
        counts = Counter(c for c in text if not c.isspace())
        total = sum(counts.values())
        if total == 0:
            return 0.0
        entropy = -sum(
            (count / total) * math.log2(count / total)
            for count in counts.values()
            if count > 0
        )
        return round(entropy, 4)

    # -----------------------------------------------------------------------
    # Reconstruction and Anomaly Collection
    # -----------------------------------------------------------------------

    def _reconstruct_from_sections(self, sections: List[CVSection]) -> str:
        """
        Reconstructs the final cleaned text from budgeted sections.
        Sections are ordered by their original sequence (maintained from segmentation).
        Each section is preceded by a normalized header for LLM section awareness.
        Strips any pre-existing Markdown prefixes from raw_header before re-adding
        the canonical '### ' prefix, preventing double-hash artifacts.
        """
        parts = []
        for sec in sections:
            if sec.raw_header:
                clean_header = re.sub(r"^#{1,4}\s*", "", sec.raw_header).strip()
                parts.append(f"### {clean_header}\n{sec.content}")
            else:
                parts.append(sec.content)
        return "\n\n".join(parts)

    def _collect_anomalies(
        self,
        raw_text: str,
        normalized_text: str,
        sections: List[CVSection],
        line_anomalies: List[str],
        budget_anomalies: List[str],
        primary_script: str,
    ) -> List[str]:
        """Aggregates all detected anomaly labels into a deduplicated list."""
        anomalies: List[str] = []

        # From line reconstruction
        anomalies.extend(line_anomalies)

        # Encoding artifacts: presence of replacement character (U+FFFD)
        if "\ufffd" in normalized_text:
            anomalies.append("encoding_artifacts")

        # Mixed RTL/LTR: Armenian or RTL markers with Arabic/Hebrew characters
        if re.search(r"[\u0600-\u06FF\u0590-\u05FF]", raw_text):
            anomalies.append("mixed_rtl_ltr")

        # Missing dates: work_experience section with no date patterns found
        for sec in sections:
            if sec.label == "work_experience":
                date_pattern = re.compile(
                    r"\b(19|20)\d{2}\b|present|current|հիմա|сейчас",
                    re.IGNORECASE
                )
                if not date_pattern.search(sec.content):
                    anomalies.append("missing_dates")
                break

        # Garbled Armenian: Armenian script but less than 20% vowel ratio
        # (Armenian has ~40% vowel frequency; lower suggests encoding corruption)
        if primary_script == "armenian":
            armenian_vowels = set("աեէըիovuuueueu") | set("աեէըիouёаеиоуыэюя")
            armenian_chars = [c for c in normalized_text if _ARMENIAN_RANGE_START <= ord(c) <= _ARMENIAN_RANGE_END]
            if armenian_chars:
                vowel_ratio = sum(1 for c in armenian_chars if c in "աեեւiuouiouioue") / len(armenian_chars)
                if vowel_ratio < 0.15:
                    anomalies.append("garbled_armenian")

        # Budget truncation anomalies
        truncated_sections = [
            a.replace("truncated:", "") for a in budget_anomalies
            if a.startswith("truncated:")
        ]
        if truncated_sections:
            anomalies.append(f"truncated_sections:{','.join(truncated_sections)}")

        # Duplicate entries: same company name appearing 3+ times
        company_pattern = re.compile(r"(?<=\n)([A-ZԱ-Ֆ][^\n]{2,40})(?=\n)")
        company_matches = company_pattern.findall(normalized_text)
        if company_matches:
            company_counts = Counter(company_matches)
            duplicates = [name for name, count in company_counts.items() if count >= 3]
            if duplicates:
                anomalies.append("duplicate_entries")

        return list(dict.fromkeys(anomalies))  # Deduplicate while preserving order


# ---------------------------------------------------------------------------
# Convenience: Token Budget Report (for logging / Evaluation Tab)
# ---------------------------------------------------------------------------

def format_budget_report(result: PreprocessingResult) -> str:
    """
    Returns a human-readable token budget allocation report.
    Used for display in the Evaluation Tab's pipeline trace.
    """
    lines = [
        f"CV Preprocessing Report",
        f"  Input chars   : {result.total_input_chars}",
        f"  Output chars  : {result.total_output_chars}",
        f"  Est. tokens   : {result.estimated_output_tokens}",
        f"  Primary script: {result.primary_script}",
        f"  Languages     : {', '.join(result.detected_languages)}",
        f"  Confidence    : {result.preprocessing_confidence:.2f}",
        f"  Anomalies     : {', '.join(result.anomalies) if result.anomalies else 'none'}",
        f"",
        f"Section Budget Allocation:",
    ]
    for sec in result.sections:
        truncation_flag = " [TRUNCATED]" if sec.is_truncated else ""
        lines.append(
            f"  [{sec.label:<18}] "
            f"chars={sec.char_count:>5} | "
            f"budget={sec.token_budget:>5} | "
            f"entropy={sec.entropy:.3f}{truncation_flag}"
        )
    return "\n".join(lines)
