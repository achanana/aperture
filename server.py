# Author: Aditya Chanana

import cv2
import cv2.xfeatures2d
import gabriel_server
import gabriel_server.cognitive_engine
import logging
import sys
# import gabriel_server.gabriel_pb2

import table

def main():
    image_db = table.ImageDataTable()
    logging.basicConfig(format="%(levelname)s: %(message)s", level=logging.INFO)
    server = ApertureServer(image_db)


class ApertureServer(gabriel_server.cognitive_engine.Engine):
    def __init__(self, image_db):
        surf = cv2.xfeatures2d.SURF_create()
        self.table = image_db
    def handle(self, input_frame):
        pass

if __name__ == '__main__':
    sys.exit(main())
