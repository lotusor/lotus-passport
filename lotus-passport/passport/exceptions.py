"""Centralized DRF exception handler — uniform JSON error shape."""
from rest_framework.views import exception_handler as drf_handler


def custom_exception_handler(exc, context):
    response = drf_handler(exc, context)
    if response is None:
        # Unhandled (e.g. 500) — let Django render it; we keep it minimal.
        return None
    detail = response.data
    if isinstance(detail, dict) and "detail" not in detail:
        # Flatten field errors into a single message for clients.
        messages = []
        for field, errs in detail.items():
            if isinstance(errs, (list, tuple)):
                messages.append(f"{field}: {errs[0]}")
            else:
                messages.append(f"{field}: {errs}")
        response.data = {"error": {"code": response.status_code, "message": "; ".join(messages)}}
    elif isinstance(detail, dict) and "detail" in detail:
        response.data = {
            "error": {"code": response.status_code, "message": str(detail["detail"])}
        }
    return response
