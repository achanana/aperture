#!/usr/bin/env python

from collections import namedtuple
import cv2

ImageData = namedtuple('ImageData', 'kp des hist img annotation_text latitude longitude')

# TODO: Add in exception handling!
class ImageDataTable:
    def __init__(self, starting_data={}):
        self.table = starting_data

    def get_keys(self):
        return self.table.keys()

    ## Get operations
    def get_annotation_text(self, image):
        response = self.table[image].annotation_text
        return response

    def get_keypoints(self, image):
        response = self.table[image].kp
        return response

    def get_descriptors(self, image):
        response = self.table[image].des
        return response

    def get_histogram(self, image):
        response = self.table[image].hist
        return response

    def get_image(self, image):
        return self.table[image].img

    def get_all_data(self, image):
        return self.table[image]

    ## Add operations
    def add_annotation(self, key, kp, des, hist, img,
                       annotation_text,
                       latitude = 0,
                       longitude = 0,
                       persist_to_disk = True):
        data = ImageData(kp = kp, des = des, hist = hist, img = img,
                         annotation_text = annotation_text,
                         latitude = latitude, longitude = longitude)
        print(f"Adding {key=} to the database, "
              f"{annotation_text=} {latitude=} {longitude=}")
        self.table[key] = data

        if (persist_to_disk):
            cv2.imwrite('db/' + key + '.jpg', img)
            with open('db/' + key + '.txt', 'w') as f:
                f.write(annotation_text)
                f.write('\n')
                f.write(str(latitude))
                f.write('\n')
                f.write(str(longitude))

    # TODO: Add remove annotation

