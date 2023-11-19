#!/usr/bin/env python
import cv2
import logging
import numpy as np
import os
from scipy import stats
import sys
import time
from threading import Thread, Lock

import config
import table

sys.path.insert(0, "..")
import zhuocv as zc


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
        train_threshold = 0.1 * len(train_kp)
        query_threshold = 0.1 * len(query_kp)
        threshold = max(train_threshold, query_threshold)

        logging.debug("THRESHOLD: {0}".format(threshold))

        # Reject match if number of detected matches is less than the threshold
        if len(matches) < threshold:
            return None, None, None
        else:
            score += len(matches)

        # calculate the relative displacement between two group of key points
        shift_xs = []
        shift_ys = []
        for m in matches:
            k_q = query_kp[m.queryIdx]
            k_t = train_kp[m.trainIdx]
            shift_xs.append(k_q.pt[0] - k_t.pt[0])
            shift_ys.append(k_q.pt[1] - k_t.pt[1])

        shift_x1 = sum(shift_xs) / len(shift_xs)
        shift_y1 = sum(shift_ys) / len(shift_ys)
        shift_x2 = np.median(np.array(shift_xs))
        shift_y2 = np.median(np.array(shift_ys))
        shift_x = (shift_x1 + shift_x2) / 2
        shift_y = (shift_y1 + shift_y2) / 2

        hist_test_passes = 0
        if hist_correlation > config.CORREL_TH:
            hist_test_passes += 1
        if dct_correl > config.DCT_TH:
            hist_test_passes += 1
        if hist_mwn > config.MWN_TH:
            hist_test_passes += 1

        # Reject match if less than 2 hist tests pass
        if hist_test_passes >= 2:
            score += hist_correlation + dct_correl + hist_mwn
        else:
            return None, None, None

        logging.debug("SCORE IS {0}".format(score))
        return score, (shift_x, shift_y), matches

    def display_match(self, query_img, query_kp, train_img, train_kp, best_matches):
        match_img = \
            cv2.drawMatches(
                query_img, query_kp, train_img, train_kp, best_matches, None,
                flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS)
        with self.current_frame_lock:
            self.current_frame = match_img

    def match(self, query_img, display_match = True):
        response = {}

        query_img = cv2.resize(query_img, (config.IM_WIDTH, config.IM_HEIGHT))

        # Calculate color hist
        query_hist = cv2.calcHist([query_img], [0], None, [256], [0, 256])

        # Extract image features with SIFT
        query_kp, query_des = self.surf.detectAndCompute(query_img, None)

        if len(query_kp) is None:
            response['status'] = 'success'
            response['image'] = None
            return response

        # Find the best match in the database
        best_fit = None
        best_score = 0
        best_shift = None
        best_matches = None
        for key in self.table.get_keys():
            logging.debug("NOW COMPARING WITH: %s" % key)
            train_data = self.table.get_all_data(key)
            train_kp, train_des, train_hist, train_img, annotation_text, annotation_img = train_data
            score, shift, matches = \
                self.compute_match_score(
                    (query_kp, query_des, query_hist, query_img),
                    (train_kp, train_des, train_hist, train_img))
            if score is not None and score > best_score:
                best_score = score
                best_shift = shift
                best_fit = key
                best_matches = matches

        response = {'status' : 'success'}


        # Send response to server
        if best_fit == None:
            logging.debug("BEST FIT IS: {0}".format(best_fit))
            response['key'] = None
        else:
            if display_match:
                train_data = self.table.get_all_data(best_fit)
                train_kp, _, _, train_img, _, _ = train_data
                self.display_match(query_img, query_kp, train_img, train_kp, best_matches)

            logging.info("BEST FIT IS: {0}".format(best_fit))
            response['key'] = best_fit
            annotated_text = self.table.get_annotation_text(best_fit)
            annotation_img = self.table.get_annotation_img(best_fit)
            if annotation_img is not None:
                rows,cols = annotation_img.shape[:2]
                M = np.float32([[1,0,best_shift[0]],[0,1,best_shift[1]]])
                annotation_img = cv2.warpAffine(annotation_img, M, (cols, rows))
                response['annotation_img'] = annotation_img
            if annotated_text is not None:
                response['annotated_text'] = annotated_text
        return response

