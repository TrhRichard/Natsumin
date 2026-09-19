from api.routers import badges, users
from fastapi import FastAPI


def create_app() -> FastAPI:
	app = FastAPI(title="Natsumin API", description="")
	app.include_router(badges.router, prefix="/badges", tags=["badges"])
	app.include_router(users.router, prefix="/users", tags=["users"])

	return app
