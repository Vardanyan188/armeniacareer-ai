# src/ui/components/data_ingest_panel.py
#
# Admin-only PRIVATE data ingest panel (Phase 17.3).
#
# Renders ONLY when ACAI_ENABLE_INGEST is enabled. Saves a single uploaded
# CV/JD into the local PRIVATE dataset (git-ignored) via src.engine.data_ingest.
# It never writes to data/raw, never to the Candidate Pool, and is never shown
# in Candidate/Recruiter modes. No PII or raw CV text is displayed.

from __future__ import annotations

from typing import Any

import streamlit as st

from src.engine.data_ingest import (
    DATA_TYPE_JD,
    DATA_TYPE_RESUME,
    AuthorizationRequiredError,
    DuplicateIngestError,
    UnsupportedDestinationError,
    destination_dir,
    ingest_enabled,
    save_private_file,
)
from src.ui.components.ui_kit import notice, section_header

# Human labels ↔ engine data types.
_TYPE_LABELS = {
    "Resume (CV)": DATA_TYPE_RESUME,
    "Job description (JD)": DATA_TYPE_JD,
}
_UPLOAD_TYPES = {
    DATA_TYPE_RESUME: ["pdf", "docx", "txt", "md"],
    DATA_TYPE_JD: ["json", "txt", "md"],
}


def _as_bytes(value: Any) -> bytes:
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return value.encode("utf-8")
    return bytes(value)


def render_data_ingest_panel() -> None:
    """Admin-only private ingest UI. No-op unless ACAI_ENABLE_INGEST is set."""
    if not ingest_enabled():
        # Hidden completely when the env gate is off (no persistence surface).
        return

    with st.expander("Data Ingest (internal · private dataset)", expanded=False):
        notice(
            "Internal data ingest. Saves to your PRIVATE local dataset only "
            "(data/private/, git-ignored). These files are never shown in the "
            "Admin/Demo selectors and are never committed. Ingest only data you "
            "are authorized to store. raw/demo import is deferred to a later phase.",
            "warn",
        )

        section_header(
            "Save a file to the private dataset",
            "Formats — CV: PDF, DOCX, TXT, MD · JD: JSON, TXT, MD. Text-based "
            "files work best; scanned/image files are not OCR'd (OCR not implemented).",
        )

        type_label = st.radio(
            "Data type", list(_TYPE_LABELS.keys()),
            horizontal=True, key="ingest_data_type",
        )
        data_type = _TYPE_LABELS[type_label]

        uploaded = st.file_uploader(
            "Upload a single file",
            type=_UPLOAD_TYPES[data_type],
            accept_multiple_files=False,
            key=f"ingest_uploader_{data_type}",
        )

        dest = destination_dir(data_type).as_posix()
        st.caption(f"Destination (private only): `{dest}/`")

        notes = st.text_input("Notes (optional)", key="ingest_notes")
        authorized = st.checkbox(
            "I am authorized to store this file locally for internal testing.",
            key="ingest_authorized",
        )

        can_save = uploaded is not None and authorized
        if st.button("Save to private dataset", key="ingest_save", disabled=not can_save):
            try:
                record = save_private_file(
                    data=_as_bytes(uploaded.getvalue()),
                    original_filename=uploaded.name,
                    data_type=data_type,
                    authorized=authorized,
                    notes=notes,
                )
                st.success(
                    f"Saved to the private dataset · record {record.record_id[:8]}… → "
                    f"`{record.destination}/{record.stored_filename}`"
                )
            except DuplicateIngestError:
                st.info("Duplicate — an identical file is already ingested. Nothing written.")
            except AuthorizationRequiredError:
                st.warning("Authorization is required to store this file.")
            except UnsupportedDestinationError as exc:
                st.error(str(exc))
            except Exception as exc:  # pragma: no cover - defensive
                st.error(f"Could not save the file: {exc}")
