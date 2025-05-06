from fastapi import FastAPI
from main import tweet_movie

app = FastAPI()

@app.get("/")
def root():
    tweet_movie()
    return {"status": "Tweet sent"}
