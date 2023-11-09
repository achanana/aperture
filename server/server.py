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

import config
import match
import table
import zhuocv as zc

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

    def add_images_to_table(self):
        logging.info("Adding images to table")
        image_filter = lambda f : f.lower().endswith("jpeg")
        db_filelist = \
            [os.path.join(self.db_path, f) for f in os.listdir(self.db_path) if
                 image_filter(f)]

        for filename in db_filelist:
            img = cv2.imread(filename, 0)
            img = cv2.resize(img, (config.IM_HEIGHT, config.IM_WIDTH))
            annotation_img = cv2.imread(filename.replace('jpeg', 'png'), -1)
            annotation_img = cv2.resize(annotation_img,
                                        (config.IM_HEIGHT, config.IM_WIDTH))

            # Choose betwen color hist and grayscale hist
            hist = cv2.calcHist([img], [0], None, [256], [0, 256])  # Grayscale

            kp, des = self.surf.detectAndCompute(img, None)

            # Store the keypoints, descriptors, hist, image name, and cv image
            # in the database
            self.table.add_annotation(filename, kp, des, hist, img,
                                      annotation_img = annotation_img)

    def handle(self, input_frame):
        # Receive data from control VM
        logging.info("received new image")
        result = {}

        status = gabriel_pb2.ResultWrapper.Status.SUCCESS

        data = np.frombuffer(input_frame.payloads[0], dtype='uint8')

        # Preprocessing of input image
        # deserialized_bytes = np.frombuffer(input_frame.payloads, dtype=np.int8)
        img = cv2.imdecode(data, 0)
        img_with_color = cv2.imdecode(data, -1)
        img_with_color = \
            cv2.resize(img_with_color, (config.IM_HEIGHT, config.IM_WIDTH))
        b_channel, g_channel, r_channel = cv2.split(img_with_color)
        alpha_channel = np.ones(b_channel.shape, dtype = b_channel.dtype) * 50
        img_RGBA = cv2.merge((b_channel, g_channel, r_channel, alpha_channel))
        zc.check_and_display(
            'input', img, display_list, resize_max = config.DISPLAY_MAX_PIXEL,
            wait_time = config.DISPLAY_WAIT_TIME)

        # Get image match
        match = self.matcher.match(img)

        # Send annotation data to mobile client
        if match['status'] != 'success':
            return json.dumps(result)
        img_RGBA = cv2.resize(img_RGBA, (config.IM_HEIGHT, config.IM_WIDTH))
        annotation = {}
        annotation['annotated_img'] = zc.cv_image2raw(img_RGBA)
        if match['key'] is not None:
            if match.get('annotated_text', None) is not None:
                annotation['annotated_text'] = match['annotated_text']
            if match.get('annotation_img', None) is not None:
                annotation_img = match['annotation_img']
                annotation_img = cv2.resize(annotation_img,
                                            (config.IM_HEIGHT, config.IM_WIDTH))
                annotated_img = \
                    cv2.addWeighted(img_RGBA, 1, annotation_img, 1, 0)
                annotation['annotated_img'] = \
                    zc.cv_image2raw(annotated_img)
        else:
            annotation['annotated_text'] = "No match found"

        result_wrapper = gb_cognitive_engine.create_result_wrapper(status)

        result = gabriel_pb2.ResultWrapper.Result()
        result.payload_type = gabriel_pb2.PayloadType.IMAGE
        result.payload = annotation['annotated_img']
        result_wrapper.results.append(result)

        return result_wrapper

if __name__ == '__main__':
    sys.exit(main())
