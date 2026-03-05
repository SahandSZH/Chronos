from fastapi import APIRouter

from app.api.endpoints import auth, calendar, google, tasks

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(tasks.router)
api_router.include_router(calendar.router)
api_router.include_router(google.router)

