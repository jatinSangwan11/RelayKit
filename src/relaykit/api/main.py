from fastapi import FastAPI

from relaykit.api.routes.endpoints import router as endpoints_router
from relaykit.api.routes.subscriptions import router as subscriptions_router

app = FastAPI(title="RelayKit")
app.include_router(endpoints_router)
app.include_router(subscriptions_router)
