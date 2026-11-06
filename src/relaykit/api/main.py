from fastapi import FastAPI

from relaykit.api.middleware.request_logging import request_logging_middleware
from relaykit.api.routes.endpoints import router as endpoints_router
from relaykit.api.routes.events import router as events_router
from relaykit.api.routes.subscriptions import router as subscriptions_router
from relaykit.observability.logging import configure_logging

configure_logging()
app = FastAPI(title="RelayKit")
app.middleware("http")(request_logging_middleware)
app.include_router(endpoints_router)
app.include_router(subscriptions_router)
app.include_router(events_router)
