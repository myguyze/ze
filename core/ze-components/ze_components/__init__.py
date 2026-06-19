# ── Atoms ─────────────────────────────────────────────────────────────────────
from ze_components.atoms import (
    Badge, Button, Divider, ProgressBar, Spacer, Text,
    badge, button, caption, code, danger, divider, error,
    heading, info, label, muted, primary, progress,
    secondary, spacer, subheading, success, text, warning,
)

# ── Molecules ──────────────────────────────────────────────────────────────────
from ze_components.molecules import (
    Col, Row,
    between, card, center, col, row, section,
)

# ── Organisms ─────────────────────────────────────────────────────────────────
from ze_components.organisms import (
    ConnectionEvidence, ConnectionItem, Connections, Form, FormField, Table,
    connections, form, form_field, table,
)

# ── Patterns ──────────────────────────────────────────────────────────────────
from ze_components.patterns import (
    card_notice, choice_group, confirm_prompt, connect_account,
    connections_list, consent, list_items, metric,
    progress_steps, review, timeline,
)

# ── Registry (for codegen and schema generation) ──────────────────────────────
PRIMITIVE_SUB_TYPES: list[type] = [FormField, ConnectionEvidence, ConnectionItem]

PRIMITIVE_TYPES: list[type] = [
    Col, Row, Text, Badge, Divider, Spacer, Button, ProgressBar,
    Table, Form, Connections,
]
