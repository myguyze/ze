from ze_api.api.schemas import ErrorDetail

OPENAPI_TAGS = [
    {
        "name": "capabilities",
        "description": "Read and update per-agent capability modes (`capabilities.yaml`).",
    },
    {
        "name": "memory",
        "description": "User facts, review workflow, and memory digest.",
    },
    {
        "name": "routing",
        "description": "Embedding-based routing audit log.",
    },
]

OPENAPI_RESPONSES_422: dict = {
    422: {
        "model": ErrorDetail,
        "description": "Validation error (unknown agent/intent or invalid request body)",
    },
}
