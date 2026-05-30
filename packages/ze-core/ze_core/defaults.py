"""Ze Core framework defaults.

All framework-level constants live here. Modules import from this file so
every magic number has a name and a single point of change.

Override in code (subclass Container, pass RouterConfig, etc.) only when
you have a measured reason. You will rarely have one.
"""

# ── Routing ───────────────────────────────────────────────────────────────────

ROUTING_THRESHOLD: float = 0.55
"""Minimum cosine similarity for a confident single-agent match."""

ROUTING_GAP_THRESHOLD: float = 0.10
"""Minimum score gap between top-two agents before triggering LLM decomposition."""

# ── Models ────────────────────────────────────────────────────────────────────

MODEL_AGENT_DEFAULT: str = "anthropic/claude-sonnet-4-5"
"""Default model for agent execution when no override is declared."""

MODEL_AGENT_TIMEOUT: int = 30
"""Default per-agent execution timeout in seconds."""

MODEL_ROUTER_FALLBACK: str = "anthropic/claude-haiku-4-5"
"""Model used for LLM-based routing decomposition (haiku fallback)."""

MODEL_SYNTHESIS: str = "anthropic/claude-haiku-4-5"
"""Model used for memory synthesis, episode summarisation, and profile updates."""

MODEL_VISION_CAPTION: str = "google/gemini-flash-1.5"
"""Model used to caption images before embedding-based routing."""

MODEL_WHISPER: str = "openai/whisper-1"
"""Model used to transcribe audio before routing."""

# ── Memory — context retrieval ────────────────────────────────────────────────

MEMORY_FACTS_TOKEN_BUDGET: int = 200
"""Approximate token budget for facts injected into agent context."""

MEMORY_EPISODES_TOKEN_BUDGET: int = 500
"""Approximate token budget for episodes injected into agent context."""

MEMORY_EPISODES_FETCH_LIMIT: int = 20
"""Maximum number of candidate episodes fetched per semantic search."""

MEMORY_CONTRADICTION_THRESHOLD: float = 0.85
"""Cosine similarity above which a new fact is considered to contradict an existing one."""

# ── Memory — consolidation ────────────────────────────────────────────────────

MEMORY_MERGE_SILENT_THRESHOLD: float = 0.95
"""Cosine similarity above which two facts are silently merged (no LLM call)."""

MEMORY_MERGE_LLM_THRESHOLD: float = 0.85
"""Cosine similarity above which two facts are merged via an LLM call."""

MEMORY_UNREVIEWED_TTL_DAYS: int = 90
"""Days after which an unreviewed fact is soft-expired."""

MEMORY_CONTRADICTED_TTL_DAYS: int = 30
"""Days after which a contradicted fact is hard-deleted."""

MEMORY_EXPIRY_GRACE_DAYS: int = 7
"""Days between soft-expiry (expires_at set) and hard-deletion of unreviewed facts."""

MEMORY_EPISODE_RECENCY_DAYS: int = 14
"""Episodes older than this are eligible for archival."""

MEMORY_EPISODE_ARCHIVE_BATCH: int = 20
"""Maximum episodes to archive in a single consolidation run."""

MEMORY_EPISODE_MIN_ARCHIVE_BATCH: int = 10
"""Minimum batch size required to trigger archival (avoid summarising tiny sets)."""

# ── Workflow ──────────────────────────────────────────────────────────────────

MODEL_WORKFLOW_PLAN: str = "anthropic/claude-haiku-4-5-20251001"
"""Model used to decompose workflow descriptions into steps and extract schedules."""

# ── Goals ─────────────────────────────────────────────────────────────────────

MODEL_GOAL_PLAN: str = "anthropic/claude-haiku-4-5"
"""Model used to decompose goals into milestones and extract learnings."""

GOAL_ADVANCE_INTERVAL_SECONDS: int = 900
"""How often the goal advance sweep runs (15 minutes)."""

# ── Persona ───────────────────────────────────────────────────────────────────

PERSONA_DEFAULT_PROFILE: str = "default"
"""Name of the persona profile used when no override is active."""

PERSONA_KNOWN_DIALS: frozenset = frozenset({"humor", "directness", "formality", "depth"})
"""Dial names the framework recognises. Applications may extend by subclassing PersonaStore."""
