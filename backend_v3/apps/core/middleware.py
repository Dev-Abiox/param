"""
Request middleware: correlation IDs and structlog context binding.

Each inbound request receives a unique X-Request-ID header (generated if
not already present).  The ID is bound into the structlog context so that
every log line emitted during that request carries the same request_id,
making cross-service log correlation trivial.
"""

import uuid

import structlog


class CorrelationIdMiddleware:
    """
    Injects a per-request correlation ID and binds it to structlog.

    The ID is taken from the incoming X-Request-ID header if present,
    otherwise a new UUID4 is generated.  The same value is echoed back
    in the response header so clients (and Nginx logs) can correlate.
    """

    HEADER_NAME = "HTTP_X_REQUEST_ID"
    RESPONSE_HEADER = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request_id = request.META.get(self.HEADER_NAME) or str(uuid.uuid4())
        request.request_id = request_id

        # Bind to structlog context for the lifetime of this thread/task
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = self.get_response(request)
        response[self.RESPONSE_HEADER] = request_id
        return response
