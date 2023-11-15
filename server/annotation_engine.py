# Author: Aditya Chanana

import argparse
from base64 import b64encode, b64decode
import cv2
import cv2.xfeatures2d
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

import config
import match
import table
import zhuocv as zc
from generated_proto import client_extras_pb2

DEFAULT_SOURCE_NAME = 'roundtrip'
DEFAULT_SERVER_HOST = 'localhost'
ZMQ_PORT = 5555

def parse_source_name_server_host():
    parser = argparse.ArgumentParser()
    parser.add_argument('source_name', nargs='?', default=DEFAULT_SOURCE_NAME)
    parser.add_argument('server_host', nargs='?', default=DEFAULT_SERVER_HOST)
    return parser.parse_args()

def engine_factory(image_db):
    return lambda: ApertureServer(image_db)

def main():
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
        self.surf = cv2.xfeatures2d.SURF_create()
        self.table = image_db
        self.matcher = match.ImageMatcher(self.table)

        # initialize database (if any)
        self.db_path = os.path.abspath('db/')
        if not os.path.exists(self.db_path):
            os.makedirs(self.db_path)

        self.add_images_to_table()

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
        image_filter = lambda f : f.lower().endswith("jpeg")
        db_filelist = \
            [os.path.join(self.db_path, f) for f in os.listdir(self.db_path) if
                 image_filter(f)]

        for filename in db_filelist:
            img = cv2.imread(filename, 0)
            img = cv2.resize(img, (config.IM_WIDTH, config.IM_HEIGHT))
            annotation_img = cv2.imread(filename.replace('jpeg', 'png'), -1)
            annotation_img = cv2.resize(annotation_img,
                                        (config.IM_WIDTH, config.IM_HEIGHT))
            annotation_text_filename = filename.replace('jpeg', 'txt')
            annotation_text = self.get_file_content(annotation_text_filename)

            hist = get_image_histogram(img)
            kp, des = self.surf.detectAndCompute(img, None)

            # Store the keypoints, descriptors, hist, image name, and cv image
            # in the database
            self.table.add_annotation(filename, kp, des, hist, img,
                                      annotation_text, annotation_img)

    def add_new_annotation(self, annotation_data):
        '''
        Add a new annotation to the database if the client specifies one.
        '''

        # The frame that the annotation corresponds to.
        annotation_image_bytes = annotation_data.frame_data
        annotation_image_array = \
            np.frombuffer(annotation_image_bytes, dtype=np.uint8)
        annotation_image = \
            cv2.imdecode(annotation_image_array, cv2.IMREAD_GRAYSCALE)
        annotation_image = \
            cv2.resize(annotation_image, (config.IM_WIDTH, config.IM_HEIGHT))

        kp, des = self.surf.detectAndCompute(annotation_image, None)
        hist = self.get_image_histogram(annotation_image)

        # Compute filename to store annotation in.
        annotation_index = self.get_next_annotation_file_index()
        annotation_filename = 'annotation' + str(annotation_index)

        # Add annotation to the database.
        self.table.add_annotation(
            annotation_filename, kp, des, hist, annotation_image,
            annotation_data.annotation_text)

    def handle(self, input_frame):
        # Receive data from control VM
        logging.info("received new image")
        result = {}

        status = gabriel_pb2.ResultWrapper.Status.SUCCESS

        # If the client specifies the extras field then an annotation should
        # be added to the database.
        if input_frame.HasField('extras'):
            print(input_frame.extras.type_url)
            annotation_data = client_extras_pb2.AnnotationData()
            input_frame.extras.Unpack(annotation_data)
            self.add_new_annotation(annotation_data)

        frame_bytes = input_frame.payloads[0]
        frame = np.frombuffer(input_frame.payloads[0], dtype=np.uint8)

        # Preprocessing of input image
        img = cv2.imdecode(frame, cv2.IMREAD_GRAYSCALE)

        # Get image match
        match = self.matcher.match(img)

        # Send annotation data to mobile client
        annotation = {}
        if match['key'] is not None:
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
