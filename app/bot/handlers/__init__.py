from aiogram import Router

from app.bot.handlers.main import router as main_router
from app.bot.handlers.material import router as material_router
from app.bot.handlers.progress import router as progress_router
from app.bot.handlers.quiz import router as quiz_router


def build_router() -> Router:
    router = Router()
    router.include_router(main_router)
    router.include_router(material_router)
    router.include_router(progress_router)
    router.include_router(quiz_router)
    return router
