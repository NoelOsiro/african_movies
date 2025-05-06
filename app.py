from fastapi import FastAPI
from bot import tweet_movie

app = FastAPI()

@app.get("/")
def root():
    tweet_movie()
    return {"status": "Tweet sent"}
