import asyncio
import aiohttp
import logging
import os
import re
from typing import Dict
import sqlite3
import LordNzb
import PTN

DATABASE = "nzbs.db"
conn = sqlite3.connect(DATABASE)
cursor = conn.cursor()

# Configure logging
logging.basicConfig(filename='producer.log',
                    level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

MTYPE_SHOW = "show"
MTYPE_MOVIE = "movie"

class NZB:
    """Represents an NZB file with its metadata."""

    def __init__(self,
                 filename: str,
                 raw_size: int,
                 mtype: str,
                 imdb_id: str = None,
                 season: int = None,
                 episode: int = None,
                 tmdb_name: str = None):
        self.filename = filename
        self.raw_size = raw_size
        self.mtype = mtype
        self.imdb_id = imdb_id
        self.season = season
        self.episode = episode
        self.tmdb_name = tmdb_name

async def fetch_tmdb_data(nzbo, parsed_info):
    """Fetches data from TMDB API asynchronously."""
    try:
        async with aiohttp.ClientSession() as session:
            if nzbo.mtype == MTYPE_SHOW:
                # It's a TV show
                async with session.get(
                        f"https://api.themoviedb.org/3/search/tv?api_key={os.environ.get('TMDB_KEY')}&query={parsed_info['title']}"
                ) as response:
                    response.raise_for_status()
                    matching_shows = await response.json()
                    if len(matching_shows['results']) > 0:
                        show_id = matching_shows['results'][0]['id']
                        async with session.get(
                                f"https://api.themoviedb.org/3/tv/{show_id}?api_key={os.environ.get('TMDB_KEY')}&append_to_response=external_ids"
                        ) as response:
                            response.raise_for_status()
                            show = await response.json()
                            nzbo.tmdb_id = show['id']
                            nzbo.tmdb_original_name = show['original_name']
                            nzbo.tmdb_name = show['name']
                            nzbo.tmdb_release_date = show['first_air_date']
                            nzbo.tmdb_year = int(
                                show['first_air_date'].split('-')[0])
                            nzbo.imdb_id = show['external_ids']['imdb_id']
            else:
                # It's a movie
                async with session.get(
                        f"https://api.themoviedb.org/3/search/movie?api_key={os.environ.get('TMDB_KEY')}&query={parsed_info['title']}"
                ) as response:
                    response.raise_for_status()
                    matching_movies = await response.json()
                    if len(matching_movies['results']) > 0:
                        movie_id = matching_movies['results'][0]['id']
                        async with session.get(
                                f"https://api.themoviedb.org/3/movie/{movie_id}?api_key={os.environ.get('TMDB_KEY')}&append_to_response=external_ids"
                        ) as response:
                            response.raise_for_status()
                            movie = await response.json()
                            nzbo.tmdb_id = movie['id']
                            nzbo.tmdb_original_name = movie[
                                'original_title']
                            nzbo.tmdb_name = movie['title']
                            nzbo.tmdb_release_date = movie['release_date']
                            nzbo.tmdb_year = int(
                                movie['release_date'].split('-')[0])
                            nzbo.imdb_id = movie['external_ids']['imdb_id']
    except aiohttp.ClientError as e:
        logging.error(f"Error fetching TMDB data: {e}")
    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")

async def process_single_nzb(file_path: str):
    """Processes a single NZB file asynchronously."""
    try:
        with open(file_path, 'rb') as f:
            nzbo = NZB()

            nzb_metadata = parse_nzb_metadata(file_path)
            parsed_info = PTN.parse(nzb_metadata['name'])

            # Set basic metadata
            nzbo.filename = nzb_metadata['filename']
            nzbo.name = nzb_metadata['name']
            nzbo.raw_size = nzb_metadata['raw_size']
            nzbo.title = parsed_info['title']

            if nzb_exists(nzbo.filename, nzbo.raw_size):
                logging.debug(
                    "Already exists in the table.. Skipping")
                return

            nzbo.mtype = MTYPE_MOVIE
            is_tv = False
            if 'season' in parsed_info or 'month' in parsed_info or 'episode' in parsed_info:
                is_tv = True
                nzbo.mtype = MTYPE_SHOW

            # Set the year based on the file name
            nzbo.year = parsed_info.get('year', None)

            # Set season
            nzbo.season = parsed_info.get('season', None)
            if is_tv and not parsed_info.get('season', None):
                nzbo.season = 1

            # Set episode number
            if isinstance(parsed_info.get('episode', None), list):
                nzbo.episode = "".join(
                    ["E{:02d}".format(e) for e in parsed_info['episode']])
            else:
                nzbo.episode = parsed_info.get('episode', None)

            # Set TMDB values by calling the API
            nzbo.tmdb_id = None
            nzbo.tmdb_original_name = None
            nzbo.tmdb_name = None
            nzbo.tmdb_release_date = None
            nzbo.tmdb_year = None
            nzbo.imdb_id = None

            await fetch_tmdb_data(nzbo, parsed_info)

            # Use parameterized query to prevent SQL injection
            cursor.execute(
                "INSERT INTO releases (filename, raw_size, mtype, imdb_id, season, tmdb_name) VALUES (?, ?, ?, ?, ?, ?)",
                (nzbo.filename, nzbo.raw_size, nzbo.mtype, nzbo.imdb_id,
                 nzbo.season, nzbo.tmdb_name))
            conn.commit()

    except sqlite3.Error as e:
        logging.error(f"Error processing NZB file {file_path}: {e}")
        conn.rollback()
    except Exception as e:
        logging.exception(
            f"An unexpected error occurred while processing {file_path}: {e}")

def create_db_and_table():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS releases (
        filename TEXT PRIMARY KEY,
        raw_size INTEGER,
        mtype TEXT,
        imdb_id TEXT,
        season INTEGER,
        tmdb_name TEXT
    )
    """)
    conn.commit()

def load_nzb_data():
    for filename in os.listdir("."):
        if filename.endswith(".nzb"):
            process_single_nzb(filename)

# Function to parse metadata from nzb
def parse_nzb_metadata(filepath):
    m = LordNzb.parser(filepath)
    return {
    'filename': m.filename,
    'name': m.name,
    'raw_size': m.raw_size
    }

# Function to check if an NZB already exists
def nzb_exists(filename, raw_size):
    cursor.execute(
        "SELECT COUNT(*) FROM releases WHERE filename = ? AND raw_size = ?",
        (filename, raw_size))
    count = cursor.fetchone()[0]
    return count > 0

async def main():
    """Main function to process NZB files."""
    try:
        create_db_and_table()
        load_nzb_data()

        # ... (Get the list of files and process each one)
        files = [f for f in os.listdir(".") if f.endswith(".nzb")]
        tasks = [process_single_nzb(file) for file in files]
        await asyncio.gather(*tasks)

    except Exception as e:
        logging.exception(f"An unexpected error occurred: {e}")

if __name__ == '__main__':
    asyncio.run(main())