# blackhole.py

import logging
import os
import time
import xml.etree.ElementTree as ET

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from producer import process_single_nzb

# Define logger
logger = logging.getLogger('producer')
logger.setLevel(logging.DEBUG)
logFormatter = logging.Formatter(
    "%(name)-12s %(asctime)s %(levelname)-8s %(filename)s:%(funcName)s %(message)s"
)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
logger.addHandler(consoleHandler)

base_watch_path = os.environ.get("BLACKHOLE_BASE_WATCH_PATH")
radarr_path = os.environ.get("BLACKHOLE_RADARR_PATH")
sonarr_path = os.environ.get("BLACKHOLE_SONARR_PATH")
ud_mount_path = os.environ.get("BLACKHOLE_UD_MOUNT_PATH")


def getPath(isRadarr, create=False):
    absoluteBaseWatchPath = base_watch_path if os.path.isabs(
        base_watch_path) else os.path.abspath(base_watch_path)
    finalPath = os.path.join(
        absoluteBaseWatchPath, radarr_path if isRadarr else sonarr_path)

    if create:
        for sub_path in ['', 'processing', 'completed']:
            path_to_check = os.path.join(finalPath, sub_path)
            if not os.path.exists(path_to_check):
                os.makedirs(path_to_check)

    return finalPath


class ArrEventHandler(FileSystemEventHandler):
    """
    Handles file system events for new NZB files downloaded by Radarr/Sonarr.
    """

    def __init__(self, is_radarr):
        super().__init__()
        self.is_radarr = is_radarr
        self.path_name = getPath(is_radarr, create=True)

    def on_created(self, event):
        if not event.is_directory and not event.src_path.endswith('.nzb'):
            return
        logger.info(f"File '{event.src_path}' created, processing...!")
        process_single_nzb(event.src_path, self.is_radarr)


def process_single_nzb(filepath, is_radarr):
    # filepath is an absolute path
    arr_path = getPath(is_radarr)
    processing_path = os.path.join(arr_path, 'processing')
    completed_path = os.path.join(arr_path, 'completed')

    nzb_metadata = parse_nzb_metadata(filepath)
    if nzb_metadata is None:
        logger.error(f"Failed to parse NZB metadata for {filepath}")
        return

    file_to_search = nzb_metadata['name']
    file_raw_size = nzb_metadata['raw_size']

    # Move file to processing directory
    processing_file = os.path.join(processing_path,
                                   os.path.basename(filepath))
    try:
        os.rename(filepath, processing_file)
        logger.debug(f"NZB moved to processing: {processing_file}")
    except OSError as e:
        logger.error(f"Error moving NZB: {e}")
        return

    # Search for matching file in ud_mount_path
    found_file = None
    for root, _, files in os.walk(ud_mount_path):
        for file in files:
            if file == file_to_search:
                full_path = os.path.join(root, file)
                logger.debug("Checking file for size %s", full_path)
                # Check file size for up to 3% tolerance
                file_size = os.path.getsize(full_path)
                tolerance = file_raw_size * 0.03
                if abs(file_size - file_raw_size) <= tolerance:
                    logger.debug("Matching file found %s", full_path)
                    found_file = full_path
                    break
                else:
                    logger.debug("File size mismatch %s", full_path)
        if found_file:
            break

    if found_file:
        # Create symlink from `completed` to found file
        # Delete nzb from processing
        symlink_path = os.path.join(completed_path, file_to_search)
        # Delete existing symlink if it exists
        if os.path.exists(symlink_path):
            os.remove(symlink_path)
        logger.debug("Creating symlink [%s] -> [%s]", symlink_path, found_file)
        os.symlink(found_file, symlink_path)
        logger.info(f"Symlink created: {symlink_path}")
    else:
        logger.info(f"File not found: {file_to_search}")

    # Delete file from processing (assuming processing is done)
    try:
        os.remove(processing_file)
        logger.debug(f"NZB deleted from processing: {processing_file}")
    except OSError as e:
        logger.debug(f"Error deleting NZB from processing: {e}")


def parse_nzb_metadata(filepath):
    """Parses NZB metadata to extract relevant information."""
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()
        # Assuming the NZB XML has a structure like this:
        # <nzb>
        #   <file subject="...">
        #     <segments>
        #       <segment bytes="..." number="..."/>
        #       ...
        #     </segments>
        #   </file>
        #   ...
        # </nzb>

        total_bytes = 0
        for file_element in root.findall('file'):
            for segment_element in file_element.find('segments').findall(
                    'segment'):
                total_bytes += int(segment_element.get('bytes'))

        return {
            'filename': os.path.basename(filepath),
            'name': root.find('file').get('subject'),  # Extract subject as name
            'raw_size': total_bytes
        }
    except ET.ParseError:
        logger.exception(f"Error parsing NZB file: {filepath}")
        return None


if __name__ == '__main__':
    radarr_handler = ArrEventHandler(is_radarr=True)
    sonarr_handler = ArrEventHandler(is_radarr=False)

    radarr_observer = Observer()
    sonarr_observer = Observer()

    radarr_observer.schedule(radarr_handler, radarr_handler.path_name)
    sonarr_observer.schedule(sonarr_handler, sonarr_handler.path_name)

    radarr_observer.start()
    sonarr_observer.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        radarr_observer.stop()
        sonarr_observer.stop()

    radarr_observer.join()
    sonarr_observer.join()