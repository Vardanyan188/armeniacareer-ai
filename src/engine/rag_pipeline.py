# src/engine/rag_pipeline.py
#
# HybridRAGPipeline — two-retriever ensemble with optional cross-encoder reranking.
#
# Architecture:
#
#   Query
#     │
#     ├── BM25Retriever (sparse, keyword-exact)     ─┐
#     │                                              ├─► EnsembleRetriever (RRF fusion)
#     └── ChromaDB dense retriever (semantic)       ─┘
#                                                        │
#                                                        ▼
#                                              CrossEncoder reranker
#                                              (ms-marco-MiniLM-L-6-v2)
#                                                        │
#                                                        ▼
#                                                top-k Documents
#
# Collection design rationale:
#
#   interview_guides   — Behavioral/STAR frameworks. Dense-heavy (0.70/0.30):
#                        semantic proximity dominates in coaching context matching.
#
#   cv_rubrics         — ATS formatting rules, Armenian market norms. Hybrid (0.60/0.40):
#                        both conceptual match and keyword exact-match matter.
#
#   labor_code_am      — RA Labor Code excerpts. BM25-heavy (0.20/0.80):
#                        legal terminology requires exact keyword matching.
#
#   skill_taxonomy_cis — Skill hierarchy JSON. Equal weight (0.50/0.50):
#                        canonical names benefit from both retrieval modes.
#
# Cross-encoder reranking pass:
#   Implemented using `cross-encoder/ms-marco-MiniLM-L-6-v2`.
#   Activates only when `enable_reranker=True` (default) AND the model
#   is loadable from sentence_transformers. Fails gracefully — if the
#   package is absent or the model download fails, retrieval continues
#   without reranking and a WARNING is logged.
#
# Singleton usage:
#   Instantiate once per Streamlit process lifecycle via a module-level
#   singleton or Streamlit `@st.cache_resource`. Repeated `__init__` calls
#   re-open ChromaDB connections; avoid this in high-traffic deployments.

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from langchain.schema import Document

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Collection Configuration
# ---------------------------------------------------------------------------

COLLECTION_CONFIGS: Dict[str, Dict[str, Any]] = {
    "interview_guides": {
        "description":   "STAR method, behavioral frameworks, question taxonomies",
        "dense_weight":  0.70,
        "bm25_weight":   0.30,
        "k":             5,
        "chunk_size":    900,
        "chunk_overlap": 120,
    },
    "cv_rubrics": {
        "description":   "ATS optimization, CV formatting guides, Armenian market norms",
        "dense_weight":  0.60,
        "bm25_weight":   0.40,
        "k":             4,
        "chunk_size":    700,
        "chunk_overlap": 100,
    },
    "labor_code_am": {
        "description":   "RA Labor Code excerpts for responsible hiring governance",
        "dense_weight":  0.20,
        "bm25_weight":   0.80,  # Legal text: exact term matching must dominate
        "k":             3,
        "chunk_size":    600,
        "chunk_overlap": 80,
    },
    "skill_taxonomy_cis": {
        "description":   "Armenian and CIS tech market skill hierarchy and canonical names",
        "dense_weight":  0.50,
        "bm25_weight":   0.50,
        "k":             6,
        "chunk_size":    500,
        "chunk_overlap": 60,
    },
}

KNOWN_COLLECTIONS = frozenset(COLLECTION_CONFIGS.keys())

DEFAULT_RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
RERANKER_BATCH_SIZE    = 32   # Documents per cross-encoder inference call
MAX_CONTEXT_CHUNKS     = 6    # Hard cap on injected RAG chunks (context budget)


# ===========================================================================
# HybridRAGPipeline
# ===========================================================================

class HybridRAGPipeline:
    """
    Manages ChromaDB collections with per-collection BM25 + dense ensemble
    retrieval, fused via Reciprocal Rank Fusion (RRF), and optionally
    reranked by a cross-encoder pass.

    Parameters
    ----------
    persist_directory : str
        Path to the ChromaDB persistence directory. Created if absent.
    enable_reranker : bool
        Whether to load and apply the cross-encoder reranker.
        Defaults to True but degrades gracefully if sentence_transformers
        is unavailable.
    reranker_model_name : str
        HuggingFace model ID for the cross-encoder reranker.
    embedding_model : str
        OpenAI embedding model for dense retrieval.
    """

    def __init__(
        self,
        persist_directory:   str  = "./data/chroma_db",
        enable_reranker:     bool = True,
        reranker_model_name: str  = DEFAULT_RERANKER_MODEL,
        embedding_model:     str  = "text-embedding-3-small",
    ) -> None:
        self.persist_directory = persist_directory
        self._reranker_model_name = reranker_model_name
        self._embedding_model     = embedding_model

        # Lazy-initialized per collection
        self._vectorstores:       Dict[str, Any] = {}
        self._bm25_document_sets: Dict[str, List[Document]] = {}

        # Embeddings shared across all collections
        self._embeddings = self._init_embeddings(embedding_model)

        # Cross-encoder reranker (optional)
        self._reranker: Optional[Any] = None
        if enable_reranker:
            self._reranker = self._load_reranker(reranker_model_name)

        # Ensure persist directory exists
        Path(persist_directory).mkdir(parents=True, exist_ok=True)

    # ── Initialization Helpers ─────────────────────────────────────────────

    @staticmethod
    def _init_embeddings(model: str) -> Any:
        """Initializes OpenAI embeddings. Raises on missing OPENAI_API_KEY."""
        from langchain_openai import OpenAIEmbeddings
        return OpenAIEmbeddings(model=model)

    @staticmethod
    def _load_reranker(model_name: str) -> Optional[Any]:
        """
        Loads a sentence-transformers CrossEncoder for reranking.
        Returns None and logs a WARNING if sentence_transformers is
        unavailable or the model download fails.
        """
        try:
            from sentence_transformers import CrossEncoder  # type: ignore
            reranker = CrossEncoder(model_name)
            logger.info("Cross-encoder reranker loaded: %s", model_name)
            return reranker
        except ImportError:
            logger.warning(
                "sentence_transformers not installed. "
                "RAG pipeline will operate without cross-encoder reranking. "
                "Install with: pip install sentence-transformers"
            )
        except Exception as exc:
            logger.warning(
                "Failed to load cross-encoder reranker '%s': %s. "
                "Operating without reranking.",
                model_name, exc,
            )
        return None

    # ── Collection Management ──────────────────────────────────────────────

    def load_collection(self, collection_name: str) -> None:
        """
        Loads or opens a ChromaDB collection and builds the in-memory BM25
        document set for the ensemble retriever.

        Safe to call multiple times — skips if already loaded.
        """
        if collection_name in self._vectorstores:
            return

        if collection_name not in KNOWN_COLLECTIONS:
            raise ValueError(
                f"Unknown collection: '{collection_name}'. "
                f"Valid collections: {sorted(KNOWN_COLLECTIONS)}"
            )

        from langchain_chroma import Chroma

        vectorstore = Chroma(
            collection_name=collection_name,
            persist_directory=self.persist_directory,
            embedding_function=self._embeddings,
        )
        self._vectorstores[collection_name] = vectorstore

        # Load all documents from ChromaDB for BM25 index construction
        raw = vectorstore.get(include=["documents", "metadatas"])
        docs: List[Document] = []
        for content, meta in zip(raw.get("documents", []), raw.get("metadatas", [])):
            if content:   # Skip empty documents
                docs.append(Document(page_content=content, metadata=meta or {}))

        self._bm25_document_sets[collection_name] = docs

        doc_count = len(docs)
        logger.info(
            "Collection '%s' loaded: %d document chunks available for retrieval.",
            collection_name, doc_count,
        )

        if doc_count == 0:
            logger.warning(
                "Collection '%s' is empty. Run `make setup` or `corpus_loader.py` "
                "to populate the knowledge base before querying.",
                collection_name,
            )

    def _ensure_loaded(self, collection_name: str) -> None:
        """Load a collection if not already in memory."""
        if collection_name not in self._vectorstores:
            self.load_collection(collection_name)

    # ── Retriever Construction ─────────────────────────────────────────────

    def get_ensemble_retriever(self, collection_name: str) -> Any:
        """
        Constructs an EnsembleRetriever combining:
          - BM25Retriever (sparse, TF-IDF-based)
          - ChromaDB as_retriever (dense, embedding-based)

        Fusion is performed by EnsembleRetriever using Reciprocal Rank Fusion.
        Weights are collection-specific (see COLLECTION_CONFIGS).

        Returns a LangChain EnsembleRetriever ready for `.invoke()` calls.
        """
        self._ensure_loaded(collection_name)
        config = COLLECTION_CONFIGS[collection_name]
        k = config["k"]

        docs = self._bm25_document_sets[collection_name]

        if not docs:
            logger.warning(
                "Collection '%s' has no documents. "
                "Returning dense-only retriever as fallback.",
                collection_name,
            )
            return self._vectorstores[collection_name].as_retriever(
                search_kwargs={"k": k}
            )

        from langchain_community.retrievers import BM25Retriever
        from langchain.retrievers import EnsembleRetriever

        bm25_retriever = BM25Retriever.from_documents(docs, k=k)
        bm25_retriever.k = k

        dense_retriever = self._vectorstores[collection_name].as_retriever(
            search_type   = "similarity",
            search_kwargs = {"k": k},
        )

        ensemble = EnsembleRetriever(
            retrievers = [bm25_retriever, dense_retriever],
            weights    = [config["bm25_weight"], config["dense_weight"]],
        )
        return ensemble

    # ── Cross-Encoder Reranking ────────────────────────────────────────────

    def rerank_documents(
        self,
        query:     str,
        documents: List[Document],
        top_k:     int = 5,
    ) -> List[Document]:
        """
        Reranks `documents` against `query` using the cross-encoder model.
        Returns the top-k documents sorted by cross-encoder relevance score.

        If the reranker is unavailable, returns the first `top_k` documents
        (preserving the RRF ordering from EnsembleRetriever).
        """
        if not documents:
            return []

        if self._reranker is None or len(documents) <= 1:
            return documents[:top_k]

        pairs  = [(query, doc.page_content) for doc in documents]
        scores = self._reranker.predict(
            pairs,
            batch_size = min(RERANKER_BATCH_SIZE, len(pairs)),
            show_progress_bar = False,
        )

        ranked = sorted(
            zip(scores, documents),
            key    = lambda x: x[0],
            reverse = True,
        )

        reranked = [doc for _, doc in ranked[:top_k]]
        logger.debug(
            "Reranked %d → %d documents for query: '%s...'",
            len(documents), len(reranked), query[:60],
        )
        return reranked

    # ── Full Retrieval Pipeline ────────────────────────────────────────────

    def retrieve_and_rerank(
        self,
        collection_name: str,
        query:           str,
        top_k:           int = 5,
    ) -> List[Document]:
        """
        Single-collection retrieval with optional cross-encoder reranking.
        Step 1: EnsembleRetriever (BM25 + dense via RRF)
        Step 2: CrossEncoder reranking pass (if available)
        """
        retriever = self.get_ensemble_retriever(collection_name)
        docs      = retriever.invoke(query)
        return self.rerank_documents(query, docs, top_k)

    def retrieve_multi_collection(
        self,
        collection_queries: List[Tuple[str, str]],
        top_k_per_collection: int = 3,
        global_top_k:         int = MAX_CONTEXT_CHUNKS,
        rerank_globally:      bool = True,
    ) -> List[Document]:
        """
        Retrieves from multiple collections in a single call, deduplicates
        by content hash, optionally reranks the merged result globally.

        Parameters
        ----------
        collection_queries : list of (collection_name, query) tuples.
        top_k_per_collection : documents to retrieve per collection before merge.
        global_top_k : hard cap on final returned document count.
        rerank_globally : whether to apply a final cross-encoder pass over
                          the merged set using the first query as the probe.
        """
        seen_hashes: set  = set()
        merged:      List[Document] = []

        for collection_name, query in collection_queries:
            try:
                retriever  = self.get_ensemble_retriever(collection_name)
                candidates = retriever.invoke(query)
                for doc in candidates[:top_k_per_collection]:
                    content_hash = hash(doc.page_content[:250])
                    if content_hash not in seen_hashes:
                        seen_hashes.add(content_hash)
                        merged.append(doc)
            except Exception as exc:
                logger.warning(
                    "retrieve_multi_collection: collection '%s' failed: %s",
                    collection_name, exc,
                )

        if not merged:
            return []

        if rerank_globally and self._reranker and collection_queries:
            primary_query = collection_queries[0][1]
            merged        = self.rerank_documents(primary_query, merged, global_top_k)
        else:
            merged = merged[:global_top_k]

        return merged

    # ── Semantic Context Methods (Agent-Specific) ──────────────────────────

    def retrieve_coaching_context(
        self,
        skill_gaps:  List[str],
        role_title:  str,
        language:    str = "en",
        top_k:       int = MAX_CONTEXT_CHUNKS,
    ) -> str:
        """
        Retrieves and formats relevant coaching material for the CandidateCoach
        agent prompt. Queries `interview_guides` and `cv_rubrics` collections.

        Returns a formatted string for direct injection into the Gemini prompt.
        Returns an empty string if both collections are empty.
        """
        gap_summary = ", ".join(skill_gaps[:5]) if skill_gaps else "general competency gaps"
        query = (
            f"career coaching and interview preparation for {role_title}. "
            f"How to address skill gaps in: {gap_summary}."
        )

        docs = self.retrieve_multi_collection(
            collection_queries    = [
                ("interview_guides", query),
                ("cv_rubrics",       f"CV improvement and ATS optimization for {role_title}"),
            ],
            top_k_per_collection  = 3,
            global_top_k          = top_k,
            rerank_globally       = True,
        )

        if not docs:
            return ""

        sections = []
        for i, doc in enumerate(docs, start=1):
            source = doc.metadata.get("source", "knowledge base")
            source_short = Path(source).stem if source != "knowledge base" else source
            sections.append(
                f"[Context {i} — {source_short}]\n{doc.page_content.strip()}"
            )

        return "\n\n".join(sections)

    def retrieve_governance_context(
        self,
        jd_text: str,
        top_k:   int = 3,
    ) -> List[Document]:
        """
        Retrieves relevant RA Labor Code excerpts for the Bias & Safety Agent.
        Used to contextualize responsible hiring recommendations — NOT legal advice.
        The query is fixed and does not include JD content to avoid
        contaminating the governance retrieval with role-specific language.
        """
        query = (
            "prohibited discrimination criteria employment law hiring procedures "
            "equal opportunity employer Armenia labor code"
        )
        return self.retrieve_and_rerank("labor_code_am", query, top_k=top_k)

    def retrieve_skill_taxonomy_context(
        self,
        skill_names: List[str],
        top_k:       int = 6,
    ) -> List[Document]:
        """
        Retrieves skill taxonomy entries for canonical name normalization.
        Used by SkillsOntologyAgent to resolve non-standard skill references
        against the CIS tech market taxonomy.
        """
        if not skill_names:
            return []

        query = (
            f"skill taxonomy canonical names: {', '.join(skill_names[:8])}. "
            "CIS Armenian technology market skill hierarchy."
        )
        return self.retrieve_and_rerank("skill_taxonomy_cis", query, top_k=top_k)

    def format_documents_as_context(
        self,
        documents: List[Document],
        max_chars_per_doc: int = 600,
    ) -> str:
        """
        Formats a list of Documents into a clean context block string
        suitable for injection into an LLM prompt.
        """
        if not documents:
            return ""

        parts = []
        for i, doc in enumerate(documents, start=1):
            content = doc.page_content.strip()
            if len(content) > max_chars_per_doc:
                content = content[:max_chars_per_doc] + "…"
            source = doc.metadata.get("source", "")
            label  = Path(source).stem if source else f"context_{i}"
            parts.append(f"[{label}]\n{content}")

        return "\n\n".join(parts)

    # ── Diagnostics ────────────────────────────────────────────────────────

    def get_collection_stats(self) -> Dict[str, Dict[str, Any]]:
        """
        Returns document counts and loaded status for all known collections.
        Used by the Home Tab's system status panel.
        """
        stats: Dict[str, Dict[str, Any]] = {}
        for name in KNOWN_COLLECTIONS:
            if name in self._vectorstores:
                doc_count = len(self._bm25_document_sets.get(name, []))
                stats[name] = {
                    "loaded":      True,
                    "doc_chunks":  doc_count,
                    "description": COLLECTION_CONFIGS[name]["description"],
                }
            else:
                stats[name] = {
                    "loaded":      False,
                    "doc_chunks":  None,
                    "description": COLLECTION_CONFIGS[name]["description"],
                }
        return stats

    def health_check(self) -> Dict[str, Any]:
        """
        Verifies ChromaDB connectivity and embedding model availability.
        Returns a structured health report dict. Does NOT perform retrieval.
        Used by `make eval` and the Evaluation Tab's system status widget.
        """
        status: Dict[str, Any] = {
            "chromadb_path":        self.persist_directory,
            "chromadb_accessible":  False,
            "embeddings_available": False,
            "reranker_available":   self._reranker is not None,
            "reranker_model":       self._reranker_model_name,
            "collections_loaded":   list(self._vectorstores.keys()),
            "errors":               [],
        }

        # Check persist directory
        persist_path = Path(self.persist_directory)
        if not persist_path.exists():
            status["errors"].append(
                f"ChromaDB persist directory not found: {self.persist_directory}. "
                "Run `make setup` to initialize the knowledge base."
            )
        else:
            status["chromadb_accessible"] = True

        # Check embeddings with a no-op call
        try:
            _ = self._embeddings.embed_query("test")
            status["embeddings_available"] = True
        except Exception as exc:
            status["errors"].append(f"OpenAI embeddings unavailable: {exc}")

        return status

    # ── Corpus Ingestion Helper ────────────────────────────────────────────

    def ingest_documents(
        self,
        collection_name: str,
        documents:       List[Document],
        batch_size:      int = 100,
    ) -> int:
        """
        Ingests pre-chunked Documents into a ChromaDB collection in batches.
        Returns the count of documents successfully ingested.

        Typically called by `corpus_loader.py` during `make setup`.
        Safe to call incrementally — ChromaDB will assign UUIDs automatically.
        """
        if collection_name not in KNOWN_COLLECTIONS:
            raise ValueError(f"Unknown collection: '{collection_name}'")

        from langchain_chroma import Chroma

        vectorstore = self._vectorstores.get(collection_name)
        if vectorstore is None:
            vectorstore = Chroma(
                collection_name   = collection_name,
                persist_directory = self.persist_directory,
                embedding_function = self._embeddings,
            )
            self._vectorstores[collection_name] = vectorstore

        ingested = 0
        for i in range(0, len(documents), batch_size):
            batch = documents[i: i + batch_size]
            try:
                vectorstore.add_documents(batch)
                ingested += len(batch)
                logger.debug(
                    "Ingested batch %d–%d into '%s'.",
                    i, i + len(batch) - 1, collection_name,
                )
            except Exception as exc:
                logger.error(
                    "Ingestion failed at batch %d for collection '%s': %s",
                    i, collection_name, exc,
                )
                raise

        # Rebuild BM25 index to include newly ingested documents
        raw  = vectorstore.get(include=["documents", "metadatas"])
        docs = [
            Document(page_content=c, metadata=m or {})
            for c, m in zip(raw.get("documents", []), raw.get("metadatas", []))
            if c
        ]
        self._bm25_document_sets[collection_name] = docs

        logger.info(
            "Ingested %d documents into '%s'. Total corpus size: %d chunks.",
            ingested, collection_name, len(docs),
        )
        return ingested


# ---------------------------------------------------------------------------
# Module-Level Singleton
# ---------------------------------------------------------------------------

_pipeline_singleton: Optional[HybridRAGPipeline] = None


def get_pipeline(
    persist_directory: str = "./data/chroma_db",
    enable_reranker:   bool = True,
) -> HybridRAGPipeline:
    """
    Returns the module-level HybridRAGPipeline singleton.
    Creates it on first call; subsequent calls return the cached instance.

    In a Streamlit application, wrap this with `@st.cache_resource` to
    bind the singleton to the Streamlit session lifecycle:

        @st.cache_resource
        def get_rag_pipeline():
            return get_pipeline()
    """
    global _pipeline_singleton
    if _pipeline_singleton is None:
        _pipeline_singleton = HybridRAGPipeline(
            persist_directory = persist_directory,
            enable_reranker   = enable_reranker,
        )
        logger.info("HybridRAGPipeline singleton initialized.")
    return _pipeline_singleton
