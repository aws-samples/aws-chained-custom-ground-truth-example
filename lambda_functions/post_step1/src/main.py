# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.

# Permission is hereby granted, free of charge, to any person obtaining a copy of
# this software and associated documentation files (the "Software"), to deal in
# the Software without restriction, including without limitation the rights to
# use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
# the Software, and to permit persons to whom the Software is furnished to do so.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
# FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
# COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
# IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
# CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

import logging
import html
import json
import os
import boto3
import cv2
import numpy as np

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
REGION = os.getenv('REGION', 'us-east-1')
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)
s3 = boto3.resource('s3', region_name=REGION)
TEMP_IMAGE_NAME = '/tmp/temp.jpg'


def get_bucket_and_key(url):
    url = html.unescape(url)
    if url.startswith("s3://"):
        url = url[5:]   # strip off
    first_slash = url.find("/")
    bucket_name = url[0:first_slash]
    file_name = url[first_slash + 1:]
    return bucket_name, file_name


def download_file(local_path, bucket_name, key):
    print(f'downloading from {bucket_name} / {key} to {local_path}')
    bucket = s3.Bucket(bucket_name)
    object = bucket.Object(key)
    object.download_file(local_path)


def upload_from_local_file(bucket_name, key, local_filename):
    # upload from memory to S3
    print(f'Uploading from local {local_filename} to {key} in {bucket_name}')
    s3.Object(bucket_name, key).upload_file(local_filename)


def get_json_from_s3(bucket_name, key):
    local_path = "/tmp/temp.json"
    download_file(local_path, bucket_name, key)
    with open(local_path, "r") as rf:
        decoded_data = json.load(rf)
    os.remove(local_path)
    return decoded_data


def download_image(bucket_name, key):
    local_path = TEMP_IMAGE_NAME
    download_file(local_path, bucket_name, key)


def get_name_for_deskewed(image_file_name):
    # note that this also strips off any path
    name, ext = os.path.splitext(os.path.basename(image_file_name))
    new_name = name + '-deskewed' + ext
    print(f'get_name_for_deskewed({image_file_name}) = {new_name}')
    return new_name


def create_deskewed_image(image, corners):
    # break these into individual coordinates to help readability
    upperleft = corners[0]
    upperright = corners[1]
    lowerleft = corners[2]
    lowerright = corners[3]

    # get max width and height via Pythagorean distance formula.
    # note that element[0] is the X coordinate, element[1] is the Y
    upper_width = np.sqrt((upperleft[0] - upperright[0]) ** 2 + (upperleft[1] - upperright[1]) ** 2)
    lower_width = np.sqrt((lowerleft[0] - lowerright[0]) ** 2 + (lowerleft[1] - lowerright[1]) ** 2)
    width = max(int(upper_width), int(lower_width))
    left_height = np.sqrt((upperleft[0] - lowerleft[0]) ** 2 + (upperleft[1] - lowerleft[1]) ** 2)
    right_height = np.sqrt((upperright[0] - lowerright[0]) ** 2 + (upperright[1] - lowerright[1]) ** 2)
    height = max(int(left_height), int(right_height))

    new_corners = np.float32([(0, 0), (width - 1, 0), (0, height - 1), (width - 1, height - 1)])
    old_corners = np.float32(corners)

    # get the mapping matrix between the old image and the new one
    matrix, _ = cv2.findHomography(old_corners, new_corners, method=cv2.RANSAC, ransacReprojThreshold=3.0)

    # and then do the mapping
    source_height, source_width = image.shape[:2]
    un_warped = cv2.warpPerspective(image, matrix, (source_width, source_height), flags=cv2.INTER_LINEAR)
    return un_warped


def deskew_image(vertices):
    # convert vertices from a list of dicts to a list of tuples
    vert_tuples = [(d['x'], d['y']) for d in vertices]

    # need to make sure points are ordered UL, UR, LL, LR (upper/lower left/right)
    leftmost = set(sorted(vert_tuples, key=lambda el: el[0])[:2])
    topmost = set(sorted(vert_tuples, key=lambda el: el[1])[:2])
    rightmost = set(sorted(vert_tuples, reverse=True, key=lambda el: el[0])[:2])
    bottommost = set(sorted(vert_tuples, reverse=True, key=lambda el: el[1])[:2])

    upperleft = leftmost & topmost
    upperright = rightmost & topmost
    lowerleft = leftmost & bottommost
    lowerright = rightmost & bottommost

    corners = [upperleft.pop(), upperright.pop(), lowerleft.pop(), lowerright.pop()]

    # load the image so we can deskew it
    image = cv2.imread(TEMP_IMAGE_NAME)

    # now deskew
    return create_deskewed_image(image, corners)


def process_results(event):
    # step 1: download the JSON file that contains our annotation data
    url = event["payload"]["s3Uri"]
    bucket_name, file_name = get_bucket_and_key(url)
    data = get_json_from_s3(bucket_name, file_name)
    print(f'Got annotations: {json.dumps(data, indent=2)}')
    return_data = []

    # step 2: parse the JSON sent back from the UI for each image
    for item in data:
        # get the corners
        all_annotations = item['annotations']
        print(f'For item, got annotations: {json.dumps(all_annotations, indent=2)}')
        for annotation in all_annotations:
            all_data = json.loads(annotation['annotationData']['content'])
            print(f'Got the following data from annotations: {json.dumps(all_data, indent=2)}')
            # each annotation has a list of vertices
            vertices = all_data['annotatedResult']['polygons'][0]['vertices']
            print(f'Got vertices: {json.dumps(vertices, indent=2)}')

        # get the name of the image that was processed
        # and download it from S3 to local storage as /tmp/temp.jpg
        image_file_name = item['dataObject']['s3Uri']
        download_image(bucket_name, os.path.basename(image_file_name))

        # de-skew it
        deskewed_image = deskew_image(vertices)

        # and save it to a new local file name (based on the original)
        new_image_name = get_name_for_deskewed(image_file_name)
        local_new_image_name = f'/tmp/{new_image_name}'
        print(f'Deskewed image will be saved as {local_new_image_name}')
        cv2.imwrite(local_new_image_name, deskewed_image)

        # and then copy from local /tmp back to S3, so the next job can get it
        upload_from_local_file(bucket_name, new_image_name, local_new_image_name)

        # and add this information to our return data for each image
        annotation_info = {
            "datasetObjectId": item['datasetObjectId'],
            "consolidatedAnnotation": {
                "content": {
                    "source-ref": f"s3://{bucket_name}/{new_image_name}",
                    event["labelAttributeName"]: {}
                }
            }
        }
        return_data.append(annotation_info)
    return return_data


def lambda_handler(event, context):
    logger.info(f'In lambda post_step1 for event {json.dumps(event, indent=2)}')
    logger.info(f'Region is {REGION}')
    return process_results(event)
