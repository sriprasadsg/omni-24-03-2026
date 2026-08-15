from fastapi import FastAPI
from app.api.v1.router import api_router
from app.models.itam import Base
from app.database import engine

app = FastAPI()

app.include_router(api_router, prefix="/api")

@app.on_event("startup")
async def startup_event():
    Base.metadata.create_all(bind=engine)

@app.get("/")
async def root():
    return {"message": "Welcome to the ITAM API"}
