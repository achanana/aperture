#!/usr/bin/env python
import cv2
import logging
import numpy as np
import os
from scipy import stats
import sys
import time
from threading import Thread, Lock
from geopy import distance

import config
import table

sys.path.insert(0, "..")
import zhuocv as zc

VLOG1 = 15
VLOG2 = 14
VLOG3 = 13

class ImageMatcher:
    def __init__(self, table):
        # Initialize SURF feature detector, FLANN matcher, and image database
        self.surf = cv2.KAZE_create()
        self.flann = cv2.FlannBasedMatcher(config.INDEX_PARAMS, config.SEARCH_PARAMS)
        self.table = table
        self.current_frame = np.zeros((100,100,1))
        self.current_frame_lock = Lock()

        Thread(target=self.display_match_loop, args=()).start()

    def display_match_loop(self):
        while True:
            match = None
            with self.current_frame_lock:
                match = self.current_frame
            cv2.imshow("Match", match)
            k = cv2.waitKey(1) & 0xFF
            if k == ord('q'):
                return

    # Finds the median bin of a histogram
    def hist_median(self, hist):
        total_samples = hist.sum()
        half_samples = total_samples / 2
        s = 0
        for i in range(len(hist)):
            s += hist[i]
            if s > half_samples:
                return i

    # Filters out poor quality matches using the ratio test
    def extract_good_matches(self, matches):
        good = []
        for i, (m, n) in enumerate(matches):
            if m.distance < (config.DISTANCE_THRESH * n.distance):
                good.append(m)
        return good

    # Returns a match score between two images
    def compute_match_score(self, query_data, train_data):
        query_kp, query_des, query_hist, query_img = query_data
        train_kp, train_des, train_hist, train_img = train_data

        score = 0

        matches = self.extract_good_matches(self.flann.knnMatch(query_des, train_des, k = 2))

        # Filter out high intensity pixel values
        train_hist[245:] = train_hist[244]
        query_hist[245:] = query_hist[244]

        # Filter out low intensity pixel values
        train_hist[:10] = train_hist[10]
        query_hist[:10] = query_hist[10]

        # Shift histograms based on median bin to match score
        train_hist_median = self.hist_median(train_hist)
        if train_hist_median is None:
            train_hist_median = 128
        query_hist_median = self.hist_median(query_hist)
        if query_hist_median is None:
            query_hist_median = 128
        if query_hist_median > train_hist_median:
            n_shift = query_hist_median - train_hist_median
            hist_new = train_hist.copy()
            hist_new[:] = 0
            hist_new[n_shift:255] = train_hist[:255 - n_shift]
            train_hist = hist_new
        else:
            n_shift = train_hist_median - query_hist_median
            hist_new = query_hist.copy()
            hist_new[:] = 0
            hist_new[n_shift:255] = query_hist[:255 - n_shift]
            query_hist = hist_new

        # Find histogram correlation
        hist_correlation = cv2.compareHist(train_hist, query_hist, cv2.HISTCMP_CORREL) * 100

        # Find Mann-Whitney U Test score
        hist_mwn = stats.mannwhitneyu(query_hist.flatten(), train_hist.flatten(), use_continuity = True, alternative = "two-sided").pvalue * 100

        # Find DCT correlation
        imf = np.float32(query_img) / 255.0  # Float conversion/scale
        dst = cv2.dct(imf)           # Calculate the dct
        img1 = dst

        imf = np.float32(train_img) / 255.0  # Float conversion/scale
        dst = cv2.dct(imf)           # Calculate the dct
        img2 = dst

        dct_diff = img1 - img2
        dct_correl = cv2.compareHist(img1.flatten(), img2.flatten(), cv2.HISTCMP_CORREL) * 100

        logging.debug("NUMBER OF GOOD MATCHES: {0}".format(len(matches)))
        logging.debug("HISTORGRAM CORRELATION: {0}".format(hist_correlation))
        logging.debug("MWN CORRELATION: {0}".format(hist_mwn))
        logging.debug("DCT CORRELATION: {0}".format(dct_correl))

        # Calculate match threshold based on the number of keypoints detected in the database image and the query image
        train_threshold = 0.07 * len(train_kp)
        query_threshold = 0.07 * len(query_kp)
        threshold = max(train_threshold, query_threshold)

        logging.debug("THRESHOLD: {0}".format(threshold))

        # Reject match if number of detected matches is less than the threshold
        if len(matches) < threshold:
            logging.log(VLOG1, f"{len(matches)=} is less than {threshold=}, did not match")
            return None, None, None
        else:
            score += len(matches)

        # calculate the relative displacement between two group of key points
        # shift_xs = []
        # shift_ys = []
        # for m in matches:
        #     k_q = query_kp[m.queryIdx]
        #     k_t = train_kp[m.trainIdx]
        #     shift_xs.append(k_q.pt[0] - k_t.pt[0])
        #     shift_ys.append(k_q.pt[1] - k_t.pt[1])

        # shift_x1 = sum(shift_xs) / len(shift_xs)
        # shift_y1 = sum(shift_ys) / len(shift_ys)
        # shift_x2 = np.median(np.array(shift_xs))
        # shift_y2 = np.median(np.array(shift_ys))
        # shift_x = (shift_x1 + shift_x2) / 2
        # shift_y = (shift_y1 + shift_y2) / 2

        hist_test_passes = 0
        if hist_correlation > config.CORREL_TH:
            hist_test_passes += 1
        else:
            logging.log(VLOG1, f"{hist_correlation=} < {config.CORREL_TH=}")

        if dct_correl > config.DCT_TH:
            hist_test_passes += 1
        else:
            logging.log(VLOG1, f"{dct_correl=} < {config.DCT_TH=}")

        if hist_mwn > config.MWN_TH:
            hist_test_passes += 1
        else:
            logging.log(VLOG1, f"{hist_mwn=} < {config.MWN_TH=}")

        # Reject match if less than 2 hist tests pass
        if hist_test_passes >= 1:
            score += hist_correlation + dct_correl + hist_mwn
        else:
            logging.log(VLOG1, f"{hist_test_passes=} tests passed, did not match")
            return None, None, None

        logging.debug("SCORE IS {0}".format(score))
        return score, None, matches

    def display_match(self, query_img, query_kp, train_img, train_kp, best_matches):
        match_img = \
            cv2.drawMatches(
                query_img, query_kp, train_img, train_kp, best_matches, None,
                flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
        with self.current_frame_lock:
            self.current_frame = match_img

    @staticmethod
    def coordinates_in_proximity(coord1, coord2, thresh_meters):
        d = distance.distance(coord1, coord2).meters
        return d < thresh_meters

    def match(self, query_img, query_coords, gps_filtering = True,
              display_match = True):
        response = {}

        query_img = cv2.resize(query_img, (config.IM_WIDTH, config.IM_HEIGHT))

        # Calculate color hist
        query_hist = cv2.calcHist([query_img], [0], None, [256], [0, 256])

        # Extract image features
        match_start_time = time.time()
        query_kp, query_des = self.surf.detectAndCompute(query_img, None)
        match_end_time = time.time()
        logging.log(VLOG1, f"It took {match_end_time - match_start_time} seconds"
                            " to extract features for the incoming frame")

        if len(query_kp) is None:
            response['key'] = None
            return response

        # Find the best match in the database
        best_fit = None
        best_score = 0
        best_shift = None
        best_matches = None

        num_matches_considered = 0

        logging.log(
            VLOG1,
            f"Finding best match for location {query_coords=} "
            f"from {len(self.table.get_keys())} files")
        for key in self.table.get_keys():
            logging.debug("NOW COMPARING WITH: %s" % key)

            train_data = self.table.get_all_data(key)
            train_coords = (train_data.latitude, train_data.longitude)

            if gps_filtering and \
                not self.coordinates_in_proximity(train_coords, query_coords, 50):
                logging.log(
                    VLOG2,
                    f"Skip matching against {key=} because its "
                    f"location {train_coords=} is not "
                    f"in proximity of current coords {query_coords=}: ")
                continue

            num_matches_considered += 1

            score, shift, matches = \
                self.compute_match_score(
                    (query_kp, query_des, query_hist, query_img),
                    (train_data.kp, train_data.des, train_data.hist, train_data.img))
            if score is not None and score > best_score:
                best_score = score
                best_shift = shift
                best_fit = key
                best_matches = matches

        response = {'status' : 'success'}
        response['num_matches_considered'] = num_matches_considered

        # Send response to server
        if best_fit == None:
            logging.debug("BEST FIT IS: {0}".format(best_fit))
            response['key'] = None
        else:
            if display_match:
                train_data = self.table.get_all_data(best_fit)
                self.display_match(query_img, query_kp, train_data.img, train_data.kp, best_matches)

            logging.log(VLOG1, "BEST FIT IS: {0}".format(best_fit))
            response['key'] = best_fit
            annotated_text = self.table.get_annotation_text(best_fit)
            if annotated_text is not None:
                response['annotated_text'] = annotated_text
        return response
