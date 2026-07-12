from mangum import Mangum

from common.http.fastApiFactory import createFastApiApp
from modules.callbackRouter.routes import router

app = createFastApiApp("sahai-production-callback-router", lambda fastApiApp: fastApiApp.include_router(router))

handler = Mangum(app)
