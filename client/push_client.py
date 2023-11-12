import common
import cv2
import multiprocessing
import time
import logging
from gabriel_client.websocket_client import WebsocketClient
from gabriel_client.websocket_client import ProducerWrapper
from gabriel_client import push_source
from gabriel_client.opencv_adapter import OpencvAdapter
from gabriel_protocol import gabriel_pb2
import numpy as np
import google.protobuf.any_pb2
from aperture.generated_proto import client_extras_pb2
import pyttsx3
from gtts import gTTS
import os
import sys

capture = cv2.VideoCapture(0)

def get_producer_wrappers():
    async def producer():
        _, frame = capture.read()
        if frame is None:
            return None

        # frame = self._preprocess(frame)
        _, jpeg_frame = cv2.imencode('.jpg', frame)
        print(jpeg_frame.dtype)

        input_frame = gabriel_pb2.InputFrame()
        input_frame.payload_type = gabriel_pb2.PayloadType.IMAGE
        input_frame.payloads.append(jpeg_frame.tobytes())

        annotation_data = client_extras_pb2.AnnotationData()
        annotation_data.annotation_text = "Hello world!!"

        annotation_img = cv2.imread('IMG_0716.JPG', 0)
        _, annotation_img_jpeg = cv2.imencode('.jpg', annotation_img)

        annotation_data.frame_data = annotation_img_jpeg.tobytes()
        input_frame.extras.Pack(annotation_data)

        return input_frame

    return [
        ProducerWrapper(producer=producer, source_name="roundtrip")
    ]

def consumer(result_wrapper):
    if not result_wrapper.results:
        return

    print(result_wrapper.results[0].payload.decode('utf-8'))

def main():
    common.configure_logging()
    args = common.parse_source_name_server_host()

    client = WebsocketClient(args.server_host, common.WEBSOCKET_PORT,
                             get_producer_wrappers(),
                             consumer)
    client.launch()


if __name__ == '__main__':
    main()
