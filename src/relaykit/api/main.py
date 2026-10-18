from fastapi import FastAPI

from relaykit.api.routes.endpoints import router as endpoints_router

app = FastAPI(title="RelayKit")
app.include_router(endpoints_router)
