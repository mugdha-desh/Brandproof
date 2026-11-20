from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import asyncio

from . import config, db, limits, schedule, seed
from .routers import assets, auth, governance, redteam, stale as stale_router, system, verify


@asynccontextmanager
async def lifespan(app: FastAPI):
    limits.check_secrets()
    db.init_engine()
    if config.seed_enabled():
        seed.seed_if_empty()
    seed.ensure_core_rules()
    try:  # facts may have expired since the last start
        from . import stale
        s = db.session()
        try:
            stale.scan(s, "system", "startup (date check)")
        finally:
            s.close()
    except Exception:
        import logging; logging.getLogger("brandproof").exception("startup stale scan skipped")
    task = asyncio.create_task(schedule.loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(title="BrandProof API", version="2.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.cors_origins(), allow_methods=["*"], allow_headers=["*"],
                   allow_credentials=False)
limits.install(app)
for r in (auth.router, assets.router, governance.router, redteam.router, system.router, verify.router, stale_router.router):
    app.include_router(r)
