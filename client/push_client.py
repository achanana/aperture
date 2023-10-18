import common
import cv2
import multiprocessing
import time
import logging
from gabriel_client.websocket_client import WebsocketClient
from gabriel_client import push_source
from gabriel_client.opencv_adapter import OpencvAdapter
from gabriel_protocol import gabriel_pb2

def consume_frame(frame, extras):
    cv2.imshow('Image from server', frame)
    print(type(extras))
    print(type(frame))
    cv2.waitKey(1)

# def send_frames(source):
#     capture = cv2.VideoCapture(0)
#
#     assert(capture.isOpened())
#     logging.info("Video capture is opened")
#
#     while True:
#         _, frame = capture.read()
#         _, jpeg_frame=cv2.imencode('.jpg', frame)
#         input_frame = gabriel_pb2.InputFrame()
#         input_frame.payload_type = gabriel_pb2.PayloadType.IMAGE
#         input_frame.payloads.append(jpeg_frame.tobytes())
#
#         source.send(input_frame)
#         time.sleep(0.1)

def preprocess(frame):
    return frame

def produce_extras():
    return None

def main():
    common.configure_logging()
    args = common.parse_source_name_server_host()
    source = push_source.Source(args.source_name)
    multiprocessing.set_start_method('fork')
    # p = multiprocessing.Process(target=send_frames, args=(source,))
    # p.start()
    producer_wrappers = [source.get_producer_wrapper()]
    capture = cv2.VideoCapture(0)
    opencv_adapter = OpencvAdapter(preprocess, produce_extras, consume_frame,
                                   capture, args.source_name)

    client = WebsocketClient(args.server_host, common.WEBSOCKET_PORT,
                             opencv_adapter.get_producer_wrappers(),
                             opencv_adapter.consumer)
    client.launch()
    # p.terminate()


if __name__ == '__main__':
    main()
