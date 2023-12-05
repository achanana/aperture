# Author: Aditya Chanana

import argparse
from base64 import b64encode, b64decode
import cv2
# import cv2.xfeatures2d
import gabriel_server
from gabriel_server import cognitive_engine as gb_cognitive_engine
from gabriel_server import local_engine as gb_local_engine
from gabriel_protocol import gabriel_pb2
import logging
import os
import sys
import numpy as np
import pyttsx3
import json
import time
from pynput import keyboard
from threading import Lock

import config
import match
import table
import zhuocv as zc
from generated_proto import client_extras_pb2

DEFAULT_SOURCE_NAME = 'roundtrip'
DEFAULT_SERVER_HOST = 'localhost'
ZMQ_PORT = 5555
VLOG1 = 15
VLOG2 = 14
VLOG3 = 13

def parse_source_name_server_host():
    parser = argparse.ArgumentParser()
    parser.add_argument('source_name', nargs='?', default=DEFAULT_SOURCE_NAME)
    parser.add_argument('server_host', nargs='?', default=DEFAULT_SERVER_HOST)
    return parser.parse_args()

def engine_factory(image_db):
    return lambda: ApertureServer(image_db)

def main():
    # logging.basicConfig(level=VLOG1)
    image_db = table.ImageDataTable()
    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    SERVER_ADDRESS_FORMAT = 'tcp://{}:{}'
    args = parse_source_name_server_host()
    server_address = \
        SERVER_ADDRESS_FORMAT.format(args.server_host, ZMQ_PORT)
    gb_local_engine.run(engine_factory(image_db), args.source_name,
                        input_queue_maxsize=60, port=8099, num_tokens=2)

config.setup(is_streaming = True)
display_list = config.DISPLAY_LIST

class ApertureServer(gb_cognitive_engine.Engine):
    def __init__(self, image_db):
        self.feature_extraction_algo = cv2.KAZE_create()
        self.table = image_db
        self.matcher = match.ImageMatcher(self.table)

        # initialize database (if any)
        self.db_path = os.path.abspath('db/')
        if not os.path.exists(self.db_path):
            os.makedirs(self.db_path)

        self.add_images_to_table()

        self.gpsFilterLock = Lock()
        self.gpsFilterEnabled = True

        listener = keyboard.Listener(on_press=self.on_press)
        listener.start()

    def on_press(self, key):
        try:
            if (key.char == 'g'):
                enabled = False
                with self.gpsFilterLock:
                    self.gpsFilterEnabled = not self.gpsFilterEnabled
                    enabled = self.gpsFilterEnabled
                if enabled:
                    logStr = """***************************************************\nEnabled GPS matching filter\n***************************************************"""
                    logging.info(logStr)
                else:
                    logStr = """***************************************************\nDisabled GPS matching filter\n***************************************************"""
                    logging.info(logStr)

        except AttributeError:
            pass

    @staticmethod
    def get_next_annotation_file_index():
        '''
        Returns the next file index to use when constructing the filename if
        saving the annotations to the db directory.
        '''
        server_data_filename = 'server_data/server_data.json'
        if os.path.exists(server_data_filename):
            with open(server_data_filename, 'r+') as f:
                ret = json.load(f)
                next_file_index = ret + 1
                f.truncate(0)
                f.seek(0)
                json.dump(next_file_index, f)
        else:
            with open(server_data_filename, 'w') as f:
                ret = 1
                next_file_index = ret + 1
                json.dump(next_file_index, f)
        next_file_index = ret
        print(f'{next_file_index=}')
        return next_file_index

    @staticmethod
    def get_image_histogram(img):
        return cv2.calcHist([img], [0], None, [256], [0, 256])  # Grayscale

    @staticmethod
    def get_file_content(filename):
        with open(filename, 'r') as file:
            content = file.read()
            return content

    def add_images_to_table(self):
        logging.info("Adding images to table")
        image_filter = lambda f : f.lower().endswith("jpg")
        db_filelist = \
            [os.path.join(self.db_path, f) for f in os.listdir(self.db_path) if
                 image_filter(f)]

        for filename in db_filelist:
            img = cv2.imread(filename, 0)
            img = cv2.resize(img, (config.IM_WIDTH, config.IM_HEIGHT))
            annotation_text_filename = filename.replace('jpg', 'txt')
            annotation_data = self.get_file_content(annotation_text_filename)

            annotation_data_lines = annotation_data.splitlines()
            if len(annotation_data_lines) != 3:
                logging.fatal("expected 3 lines in the annotation data file")
            annotation_text = annotation_data_lines[0]
            latitude = float(annotation_data_lines[1])
            longitude = float(annotation_data_lines[2])

            hist = self.get_image_histogram(img)
            kp, des = self.feature_extraction_algo.detectAndCompute(img, None)

            # Store the keypoints, descriptors, hist, image name, and cv image
            # in the database
            key = os.path.splitext(os.path.basename(filename))[0]
            self.table.add_annotation(key, kp, des, hist, img,
                                      annotation_text, latitude, longitude,
                                      persist_to_disk=False)

    def add_new_annotation(self, extras, frame):
        '''
        Add a new annotation to the database if the client specifies one.
        '''

        # The frame that the annotation corresponds to.
        annotation_image = \
            cv2.imdecode(frame, cv2.IMREAD_GRAYSCALE)
        annotation_image = \
            cv2.resize(annotation_image, (config.IM_WIDTH, config.IM_HEIGHT))

        kp, des = self.feature_extraction_algo.detectAndCompute(annotation_image, None)
        hist = self.get_image_histogram(annotation_image)

        # Compute filename to store annotation in.
        annotation_index = self.get_next_annotation_file_index()
        annotation_filename = 'annotation' + str(annotation_index)

        latitude = extras.current_location.latitude
        longitude = extras.current_location.longitude

        # Add annotation to the database.
        self.table.add_annotation(
            annotation_filename, kp, des, hist, annotation_image,
            extras.annotation_text, latitude, longitude)

    def handle(self, input_frame):
        # Receive data from control VM
        logging.log(VLOG1, "received new image")
        result = {}

        status = gabriel_pb2.ResultWrapper.Status.SUCCESS

        frame_bytes = input_frame.payloads[0]
        frame = np.frombuffer(input_frame.payloads[0], dtype=np.uint8)

        latitude = 0
        longitude = 0
        if input_frame.HasField('extras'):
            extras = client_extras_pb2.Extras()
            input_frame.extras.Unpack(extras)
            if not extras.HasField('current_location'):
                logging.error("No current_location field")
            latitude = extras.current_location.latitude
            longitude = extras.current_location.longitude
            if extras.HasField('annotation_text'):
                self.add_new_annotation(extras, frame)
        else:
            logging.error("Did not receive extras field")

        # Preprocessing of input image
        img = cv2.imdecode(frame, cv2.IMREAD_GRAYSCALE)

        # Get image match
        query_coords = (latitude, longitude)
        match_start_time = time.time()
        useGpsFilter = False
        with self.gpsFilterLock:
            useGpsFilter = self.gpsFilterEnabled
        logging.log(VLOG1, f"{useGpsFilter=}")

        match = self.matcher.match(img, query_coords, gps_filtering=useGpsFilter)
        match_end_time = time.time()

        # Send annotation data to mobile client
        annotation = {}
        if match['key'] is not None:
            num_matches_considered = match['num_matches_considered']
            logging.info(f"Match found: {match['key']}. "
                         f"It took {match_end_time - match_start_time} seconds"
                          " to performing image matching against "
                         f"{num_matches_considered} stored annotations")
            annotated_text = match['annotated_text']
        else:
            annotated_text = None

        result_wrapper = gb_cognitive_engine.create_result_wrapper(status)

        if annotated_text is not None:
            result = gabriel_pb2.ResultWrapper.Result()
            result.payload_type = gabriel_pb2.PayloadType.TEXT
            result.payload = bytes(annotated_text, 'utf-8')
            result_wrapper.results.append(result)

        return result_wrapper

if __name__ == '__main__':
    sys.exit(main())
