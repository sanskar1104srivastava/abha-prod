from mangum import Mangum

from common.http.fastApiFactory import createFastApiApp
from modules.abha.routes import router as abhaRouter
from modules.admin.routes import router as adminRouter
from modules.auth.routes import router as authRouter
from modules.externalApi.routes import router as externalApiRouter
from modules.hip.routes import router as hipRouter
from modules.share.routes import router as shareRouter
from modules.userLinking.routes import router as userLinkingRouter


def registerRoutes(app):
    app.include_router(authRouter)
    app.include_router(adminRouter)
    app.include_router(externalApiRouter)
    app.include_router(abhaRouter)
    app.include_router(hipRouter)
    app.include_router(userLinkingRouter)
    app.include_router(shareRouter)

    # /v1/health mirrors the root /health so it works through API Gateway's /v1/* prefix
    @app.get("/v1/health", include_in_schema=False)
    async def v1Health():
        return {"status": "ok", "service": "sahai-production-external-api"}


app = createFastApiApp("sahai-production-external-api", registerRoutes)

handler = Mangum(app)
