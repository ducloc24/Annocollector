from fastapi import APIRouter

from app.api.v1.endpoints import (
    audit,
    auth,
    catalog,
    data,
    health,
    me,
    projects,
    teams,
    users,
    work,
)

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(me.router)
api_router.include_router(users.router)
api_router.include_router(catalog.router)
api_router.include_router(audit.router)
api_router.include_router(teams.router)
api_router.include_router(projects.router)
api_router.include_router(data.router)
api_router.include_router(work.router)
