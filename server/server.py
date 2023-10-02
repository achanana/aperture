# Author: Aditya Chanana

import argparse
import cv2
import cv2.xfeatures2d
import gabriel_server
import gabriel_server.cognitive_engine
from gabriel_server import local_engine as gb_local_engine
from gabriel_protocol import gabriel_pb2
import logging
import os
import sys
import zhuocv as zc

import table

DEFAULT_SOURCE_NAME = '0'
DEFAULT_SERVER_HOST = 'localhost'
ZMQ_PORT = 5555

def parse_source_name_server_host():
    parser = argparse.ArgumentParser()
    parser.add_argument('source_name', nargs='?', default=DEFAULT_SOURCE_NAME)
    parser.add_argument('server_host', nargs='?', default=DEFAULT_SERVER_HOST)
    return parser.parse_args()

def main():
    image_db = table.ImageDataTable()
    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    SERVER_ADDRESS_FORMAT = 'tcp://{}:{}'
    args = parse_source_name_server_host()
    server_address = \
        SERVER_ADDRESS_FORMAT.format(args.server_host, ZMQ_PORT)
    engine_factory = lambda: ApertureServer(image_db)
    gb_local_engine.run(engine_factory, args.source_name,
                        input_queue_maxsize=60, port=8099, num_tokens=2)

class ApertureServer(gabriel_server.cognitive_engine.Engine):
    def __init__(self, image_db):
        surf = cv2.xfeatures2d.SURF_create()
        self.table = image_db

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
            img = cv2.resize(cv2.imread(filename, 0),
                             (config.IM_HEIGHT, config.IM_WIDTH))
            annotation_img = \
                cv2.resize(cv2.imread(filename.replace('jpeg', 'png'), -1),
                           (config.IM_HEIGHT, config.IM_WIDTH))

            # Choose betwen color hist and grayscale hist
            hist = cv2.calcHist([img], [0], None, [256], [0, 256])  # Grayscale

            kp, des = surf.detectAndCompute(img, None)

            # Store the keypoints, descriptors, hist, image name, and cv image
            # in the database
            self.table.add_annotation(filename, kp, des, hist, img,
                                      annotation_img = annotation_img)

    def handle(self, input_frame):
        # Receive data from control VM
        logging.info("received new image")
        header['status'] = "nothing"
        result = {}

        # Preprocessing of input image
        img = zc.raw2cv_image(data, gray_scale = True)
        img_with_color = zc.raw2cv_image(data)
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
        header['status'] = 'success'
        img_RGBA = cv2.resize(img_RGBA, (320, 240))
        result['annotated_img'] = b64encode(zc.cv_image2raw(img_RGBA))
        if match['key'] is not None:
            if match.get('annotated_text', None) is not None:
                result['annotated_text'] = match['annotated_text']
            if match.get('annotation_img', None) is not None:
                annotation_img = match['annotation_img']
                annotation_img = cv2.resize(annotation_img, (320, 240))
                annotated_img = \
                    cv2.addWeighted(img_RGBA, 1, annotation_img, 1, 0)
                result['annotated_img'] = \
                    b64encode(zc.cv_image2raw(annotated_img))
        else:
            result['annotated_text'] = "No match found"

        header[gabriel.Protocol_measurement.JSON_KEY_APP_SYMBOLIC_TIME] = \
            time.time()
        return json.dumps(result)

if __name__ == '__main__':
    sys.exit(main())
