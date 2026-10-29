"""路由汇总。"""
from fastapi import APIRouter

from app.api import auth, hosts, tasks, inspections, plans, credentials

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(hosts.router)
api_router.include_router(tasks.router)
api_router.include_router(inspections.router)
api_router.include_router(plans.router)
api_router.include_router(credentials.router)
