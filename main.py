from datetime import datetime, timedelta
from flask import Flask, send_file, abort, request, Response
import logging
import os
import sqlite3

app = Flask(__name__)

if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

base_url = os.environ.get('INDEXER_BASE_URL')
nzbs_root_dir = os.environ.get('NZBS_DIR')
config_dir = "/config"
db_name = "nzbs.db"
table_name = "nzbs"
db_path = os.path.join(config_dir, db_name)

MTYPE_MOVIE = "movie"
MTYPE_SHOW = "show"

class NZB:
    """Represents an NZB file with its metadata."""

    def __init__(self, filename: str, raw_size: int, mtype: str, imdb_id: str = None, season: int = None, episode: str = None, tmdb_name: str = None):
        self.filename = filename
        self.raw_size = raw_size
        self.mtype = mtype
        self.imdb_id = imdb_id
        self.season = season
        self.episode = episode
        self.tmdb_name = tmdb_name

if __name__ != '__main__':
    gunicorn_logger = logging.getLogger('gunicorn.error')
    app.logger.handlers = gunicorn_logger.handlers
    app.logger.setLevel(gunicorn_logger.level)

@app.route('/download/<filename>')
def download_nzb(filename):
    """
    Downloads an NZB file.

    :param filename: The name of the NZB file to download.
    :return: The NZB file if found, otherwise a 404 error.
    """
    app.logger.info('New download request for %s', filename)
    try:
        # Check if file exists on disk
        for root, _, files in os.walk(nzbs_root_dir):
            if filename in files:
                full_path = os.path.join(root, filename)
                app.logger.debug("Found %s at path %s", filename, full_path)
                return send_file(full_path, as_attachment=True)
        abort(404)
    except Exception as e:
        app.logger.exception(f"Error downloading or parsing NZB file {filename}: {e}")
        abort(500)

@app.route("/search/shows/<imdbid>/<seasonnum>")
def search_shows_with_imdb(imdbid, seasonnum):
    """
    Searches for shows with the given IMDb ID and season number.

    :param imdbid: The IMDb ID of the show.
    :param seasonnum: The season number of the show.
    :return: A dictionary containing the search results.
    """
    app.logger.info('New show search request for %s, Season %s', imdbid, seasonnum)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # Use parameterized query to prevent SQL injection
        query = f"SELECT * FROM {table_name} WHERE mtype=? AND imdb_id=? AND season=?"
        app.logger.debug("Executing query %s", query)
        cursor.execute(query, (MTYPE_SHOW, imdbid, seasonnum))
        rows = cursor.fetchall()
        return {"results": rows_to_dicts(cursor, rows)}

@app.route("/search/movies/<imdbid>")
def search_movies_with_imdb(imdbid):
    """
    Searches for movies with the given IMDb ID.

    :param imdbid: The IMDb ID of the movie.
    :return: A dictionary containing the search results.
    """
    app.logger.info('New movie search request for %s', imdbid)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # Use parameterized query to prevent SQL injection
        query = f"SELECT * FROM {table_name} WHERE mtype=? AND imdb_id=?"
        app.logger.debug("Executing query %s", query)
        cursor.execute(query, (MTYPE_MOVIE, imdbid))
        rows = cursor.fetchall()
        return {"results": rows_to_dicts(cursor, rows)}

# This is needed to make prowlarr tests happy
@app.route("/search/shows/title/")
def search_shows_with_title_test():
    """
    Searches for a random show.

    :return: A dictionary containing a random show.
    """
    app.logger.info('New show search request for testing')
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        query = f"SELECT * FROM {table_name} WHERE mtype='{MTYPE_SHOW}' ORDER BY RANDOM() LIMIT 1;"
        app.logger.debug("Executing query %s", query)
        cursor.execute(query)
        rows = cursor.fetchall()
        return {"results": rows_to_dicts(cursor, rows)}

# This is needed to make prowlarr tests happy
@app.route("/search/movies/title/")
def search_movies_with_title_test():
    """
    Searches for a random movie.

    :return: A dictionary containing a random movie.
    """
    app.logger.info('New movie search request for testing')
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        query = f"SELECT * FROM {table_name} WHERE mtype='{MTYPE_MOVIE}' ORDER BY RANDOM() LIMIT 1;"
        app.logger.debug("Executing query %s", query)
        cursor.execute(query)
        rows = cursor.fetchall()
        return {"results": rows_to_dicts(cursor, rows)}

@app.route("/search/shows/title/<title>")
def search_shows_with_title(title):
    """
    Searches for shows with the given title.

    :param title: The title of the show.
    :return: A dictionary containing the search results.
    """
    app.logger.info('New show search request for %s', title)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # Use parameterized query to prevent SQL injection
        query = f"SELECT * FROM {table_name} WHERE mtype=? AND lower(tmdb_name)=lower(?)"
        app.logger.debug("Executing query %s", query)
        cursor.execute(query, (MTYPE_SHOW, title))
        rows = cursor.fetchall()
        return {"results": rows_to_dicts(cursor, rows)}

@app.route("/search/movies/title/<title>")
def search_movies_with_title(title):
    """
    Searches for movies with the given title.

    :param title: The title of the movie.
    :return: A dictionary containing the search results.
    """
    app.logger.info('New movie search request for %s', title)
    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()
        # Use parameterized query to prevent SQL injection
        query = f"SELECT * FROM {table_name} WHERE mtype=? AND lower(tmdb_name)=lower(?)"
        app.logger.debug("Executing query %s", query)
        cursor.execute(query, (MTYPE_MOVIE, title))
        rows = cursor.fetchall()
        return {"results": rows_to_dicts(cursor, rows)}

@app.route("/api")
def newznab_api():
    """
    Handles Newznab API requests.

    :return: An XML response containing the requested data.
    """
    function = request.args.get('t')
    if function == "caps":
        return Response("""<caps>
        <server appversion="1.0.0" version="0.1" title="UDIndexer" strapline="" />
        <limits max="100" default="100"/>
        <registration available="no" open="no"/>
        <searching>
            <search available="yes" supportedParams="q"/>
            <tv-search available="yes" supportedParams="q,imdbid,season,ep"/>
            <movie-search available="yes" supportedParams="q,imdbid"/>
        </searching>
        <categories>
            <category id="2000" name="Movies"></category>
            <category id="5000" name="TV"></category>
        </categories>
        <genres>
            <genre id="2" categoryid="2000" name="All"/>
            <genre id="5" categoryid="5000" name="All"/>
        </genres>
        </caps>""", mimetype='application/xml')

    if function == "tvsearch":
        imdb_id = request.args.get('imdbid')
        if not imdb_id.startswith("tt"):
            imdb_id = "tt" + imdb_id
        season = request.args.get('season')
        results = search_shows_with_imdb(imdb_id, season)
        return Response(construct_xml(results['results'], 5000), mimetype='application/xml')

    if function == "movie":
        imdb_id = request.args.get('imdbid')
        if not imdb_id.startswith("tt"):
            imdb_id = "tt" + imdb_id
        results = search_movies_with_imdb(imdb_id)
        return Response(construct_xml(results['results'], 2000), mimetype='application/xml')

    if function == "search":
        q = request.args.get('q')
        cats = request.args.get('cat')
        if cats and '2000' in cats:
            if q:
                results = search_movies_with_title(q)
                return Response(construct_xml(results['results'], 2000), mimetype='application/xml')
            return Response(construct_xml(search_movies_with_title_test()['results'], 2000), mimetype='application/xml')
        if cats and '5000' in cats:
            if q:
                results = search_shows_with_title(q)
                return Response(construct_xml(results['results'], 5000), mimetype='application/xml')
            return Response(construct_xml(search_shows_with_title_test()['results'], 5000), mimetype='application/xml')

def rows_to_dicts(cursor, rows):
    """
    Converts database rows to a list of dictionaries.

    :param cursor: The database cursor.
    :param rows: The database rows.
    :return: A list of dictionaries.
    """
    column_names = [desc[0] for desc in cursor.description]
    data = []
    for row in rows:
        # Zip column names and row values to create a dictionary
        data.append(dict(zip(column_names, row)))
    return data

def fake_dt():
    """
    Generates a fake datetime string.

    :return: A fake datetime string.
    """
    now = datetime.now()
    one_hour_ago = now - timedelta(hours=1)
    return one_hour_ago.strftime('%a, %d %b %Y %H:%M:%S %z')

def construct_xml(rows_dicts, cat):
    """
    Constructs an XML string from the given data.

    :param rows_dicts: A list of dictionaries containing the data.
    :param cat: The category ID.
    :return: An XML string.
    """
    pre = """<?xml version="1.0" encoding="UTF-8"?>
    <rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom" xmlns:newznab="http://www.newznab.com/DTD/2010/feeds/attributes/" encoding="utf-8">
    <channel><newznab:response offset="0" total="100"/><newznab:apilimits apiCurrent="0" grabCurrent="0"/>"""
    post = """</channel></rss>"""
    items = ""
    for row in rows_dicts:
        item_xml = "<item>"
        item_xml += f"<title>{row['name']}</title>"
        item_xml += f"<link>{base_url}/download/{row['filename']}</link>"
        item_xml += f'<enclosure url=\"{base_url}/download/{row["filename"]}\" length=\"{row["raw_size"]}\" type=\"application/x-nzb\"/>'
        item_xml += f"<pubDate>{fake_dt()}</pubDate>"
        item_xml += f'<newznab:attr name=\"category\" value=\"{cat}\"/>'
        item_xml += f'<newznab:attr name=\"size\" value=\"{row["raw_size"]}\"/>'
        item_xml += f'<newznab:attr name=\"files\" value=\"1\"/>'
        item_xml += f'<newznab:attr name=\"title\" value=\"\"/>'
        if cat == 5000:
            item_xml += f'<newznab:attr name=\"season\" value=\"{row["season"]}\"/>'
            item_xml += f'<newznab:attr name=\"episode\" value=\"{row["episode"]}\"/>'
        item_xml += "</item>"
        items += item_xml
    return f"{pre}{items}{post}"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=7990)