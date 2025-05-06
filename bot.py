import requests
import tweepy
import random
import schedule
import time
import os
import json
import google.generativeai as genai
from urllib.request import urlretrieve

# TMDb API configuration
TMDB_API_URL = "https://api.themoviedb.org/3/discover/movie"
TMDB_CREDITS_URL = "https://api.themoviedb.org/3/movie/{id}/credits"
TMDB_BEARER_TOKEN = os.getenv("TMDB_BEARER_TOKEN")
TMDB_HEADERS = {
    "accept": "application/json",
    "Authorization": f"Bearer {TMDB_BEARER_TOKEN}"
}

# Gemini API configuration
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel("gemini-1.5-flash")

# X API credentials
X_CONSUMER_KEY = os.getenv("X_CONSUMER_KEY")
X_CONSUMER_SECRET = os.getenv("X_CONSUMER_SECRET")
X_ACCESS_TOKEN = os.getenv("X_ACCESS_TOKEN")
X_ACCESS_TOKEN_SECRET = os.getenv("X_ACCESS_TOKEN_SECRET")

# Authenticate with X API for v2 (tweeting) and v1.1 (media upload)
client = tweepy.Client(
    consumer_key=X_CONSUMER_KEY,
    consumer_secret=X_CONSUMER_SECRET,
    access_token=X_ACCESS_TOKEN,
    access_token_secret=X_ACCESS_TOKEN_SECRET
)
# v1.1 API for media upload
auth = tweepy.OAuthHandler(X_CONSUMER_KEY, X_CONSUMER_SECRET)
auth.set_access_token(X_ACCESS_TOKEN, X_ACCESS_TOKEN_SECRET)
v1_api = tweepy.API(auth, wait_on_rate_limit=True)

# List of African countries
AFRICAN_COUNTRIES = [
    {"code": "NG", "name": "Nigeria"},
    {"code": "ZA", "name": "South Africa"},
    {"code": "KE", "name": "Kenya"},
    {"code": "GH", "name": "Ghana"},
    {"code": "ET", "name": "Ethiopia"},
    {"code": "EG", "name": "Egypt"},
    {"code": "MA", "name": "Morocco"},
    {"code": "DZ", "name": "Algeria"},
    {"code": "UG", "name": "Uganda"},
    {"code": "TN", "name": "Tunisia"},
]

def load_tweeted_ids():
    try:
        with open("tweeted_ids.json", "r") as f:
            return set(json.load(f))
    except:
        return set()

def save_tweeted_id(movie_id):
    tweeted_ids = load_tweeted_ids()
    tweeted_ids.add(str(movie_id))
    with open("tweeted_ids.json", "w") as f:
        json.dump(list(tweeted_ids), f)

def split_tweet_text(text, max_length=280):
    if len(text) <= max_length:
        return [(text, 1, 1)]
    chunks = []
    current = ""
    sentences = text.split(". ")
    for i, sentence in enumerate(sentences):
        sentence = sentence + (". " if i < len(sentences) - 1 else "")
        if len(current) + len(sentence) <= max_length:
            current += sentence
        else:
            if current:
                chunks.append(current.strip())
            current = sentence
    if current:
        chunks.append(current.strip())
    return [(chunk, i + 1, len(chunks)) for i, chunk in enumerate(chunks)]

def fetch_african_movie():
    tweeted_ids = load_tweeted_ids()
    for attempt in range(3):
        selected_country = random.choice(AFRICAN_COUNTRIES)
        country_code = selected_country["code"]
        country_name = selected_country["name"]
        print(f"Attempt {attempt + 1}/3 - Selected country: {country_name} ({country_code})")

        params = {
            "include_adult": "false",
            "include_video": "false",
            "language": "en-US",
            "page": random.randint(1, 5),
            "sort_by": "popularity.desc",
            "with_origin_country": country_code
        }
        response = requests.get(TMDB_API_URL, headers=TMDB_HEADERS, params=params)

        if response.status_code != 200:
            print(f"TMDb API error: {response.status_code} - {response.text}")
            continue

        data = response.json()
        movies = data.get("results", [])
        if not movies:
            print(f"No movies found for {country_name}")
            continue

        valid_movies = [
            movie
            for movie in movies
            if movie.get("poster_path")
            and movie.get("overview")
            and str(movie["id"]) not in tweeted_ids
        ]

        if not valid_movies:
            print(f"No valid movies with poster and overview for {country_name}")
            continue

        movie = random.choice(valid_movies)
        movie_id = movie["id"]

        credits_response = requests.get(
            TMDB_CREDITS_URL.format(id=movie_id), headers=TMDB_HEADERS
        )
        actors = []
        if credits_response.status_code == 200:
            credits_data = credits_response.json()
            actors = [
                f"{actor['name']} as {actor['character']}"
                for actor in credits_data.get("cast", [])[:3]
                if actor.get("character")
            ]

        save_tweeted_id(movie_id)
        return {
            "title": movie.get("title", "Unknown Title"),
            "plot": movie.get("overview", "No plot available."),
            "poster_url": f"https://image.tmdb.org/t/p/w500{movie.get('poster_path')}",
            "country": country_name,
            "actors": actors,
            "release_year": movie.get("release_date", "")[:4],
            "rating": movie.get("vote_average", 0)
        }
    print("Failed to find a valid movie after 3 attempts.")
    return None

def generate_gemini_tweets(movie):
    prompt = f"""
    Generate exactly 3 engaging tweets (each ≤280 characters) for a movie thread about '{movie['title']}' ({movie['release_year']}) from {movie['country']}. Use this plot: '{movie['plot']}'. Follow this structure:
    - Tweet 1: A concise, vibrant plot teaser capturing the movie's essence in an exciting tone.
    - Tweet 2: Highlight key performers, community figures, or crew (e.g., director, musicians). Use provided actors: {', '.join(movie['actors']) if movie['actors'] else 'community figures or crew'}. Avoid saying 'no actor info available.'
    - Tweet 3: A fun fact about the movie’s cultural significance, filming locations, awards, or impact (include rating: {movie['rating']}/10 if relevant), in an informative tone.
    Each tweet must include the #AfricanCinema hashtag and be standalone, with no markdown, labels (e.g., 'Tweet 1'), asterisks, or extra formatting. Separate each tweet with a newline. Ensure Tweet 1 is exciting and Tweet 3 is informative.
    """
    try:
        response = gemini_model.generate_content(prompt)
        tweets = response.text.strip().split("\n")
        return [tweet.strip() for tweet in tweets if tweet.strip() and len(tweet.strip()) <= 280]
    except Exception as e:
        print(f"Gemini API error: {e}")
        return [
            f"📖 '{movie['title']}': {movie['plot'][:200]}... #AfricanCinema",
            f"🌟 Featuring {', '.join(movie['actors']) if movie['actors'] else 'authentic voices from ' + movie['country']}. #AfricanCinema",
            f"⭐ Rated {movie['rating']}/10. A vibrant gem from {movie['country']}! #AfricanCinema"
        ]

def download_poster(poster_url, filename="poster.jpg"):
    if poster_url:
        try:
            urlretrieve(poster_url, filename)
            return filename
        except Exception as e:
            print(f"Error downloading poster: {e}")
    return None

def tweet_movie():
    movie = fetch_african_movie()
    if not movie:
        print("No African movie to tweet.")
        return

    title = movie["title"]
    country = movie["country"]
    poster_url = movie["poster_url"]

    # First tweet
    first_tweet = f"🎬 African Movie of the Day: {title}\n🌍 From: {country}\n#AfricanCinema"
    first_tweet_chunks = split_tweet_text(first_tweet, max_length=280)

    # Generate additional tweets with Gemini
    gemini_tweets = generate_gemini_tweets(movie)
    gemini_tweet_chunks = []
    for tweet in gemini_tweets:
        gemini_tweet_chunks.extend(split_tweet_text(tweet, max_length=280))

    # Download poster
    poster_path = download_poster(poster_url)

    try:
        previous_tweet_id = None
        # Post first tweet
        chunk, _, _ = first_tweet_chunks[0]
        tweet_text = chunk  # No numbering
        if poster_path:
            media = v1_api.media_upload(poster_path)
            tweet = client.create_tweet(
                text=tweet_text,
                media_ids=[media.media_id],
                in_reply_to_tweet_id=previous_tweet_id
            )
        else:
            tweet = client.create_tweet(
                text=tweet_text,
                in_reply_to_tweet_id=previous_tweet_id
            )
        previous_tweet_id = tweet.data["id"]
        print(f"Tweeted part 1: {tweet_text}")

        # Post Gemini-generated tweets
        for i, (chunk, _, _) in enumerate(gemini_tweet_chunks, start=2):
            tweet_text = chunk  # No numbering
            tweet = client.create_tweet(
                text=tweet_text,
                in_reply_to_tweet_id=previous_tweet_id
            )
            previous_tweet_id = tweet.data["id"]
            print(f"Tweeted part {i}: {tweet_text}")

        # Clean up
        if poster_path and os.path.exists(poster_path):
            os.remove(poster_path)
    except tweepy.errors.Forbidden as e:
        print(f"X API Forbidden error: {e}")
        if "453" in str(e):
            print("Your API access level does not permit posting tweets. Check Project/App settings in X Developer Portal or upgrade to Basic tier: https://developer.x.com/en/portal/products")
    except tweepy.errors.TooManyRequests as e:
        print(f"Rate limit exceeded: {e}")
    except Exception as e:
        print(f"Error tweeting: {e}")

# # Schedule to run daily
# schedule.every().day.at("09:00").do(tweet_movie)

# # Run the scheduler
# while True:
#     schedule.run_pending()
#     time.sleep(60)

# Schedule to run daily
# schedule.every().day.at("09:00").do(tweet_movie)

# Run the scheduler
while True:
    tweet_movie()
    time.sleep(60)