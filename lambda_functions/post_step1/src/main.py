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

"""
Portions of this code were adapted from
https://github.com/ashuta03/automatic_skew_correction_using_corner_detectors_and_homography
which accompanies the following blog post:
https://blog.ekbana.com/skew-correction-using-corner-detectors-and-homography-fda345e42e65
"""


def get_bucket_and_key(url):
    url = html.unescape(url)
    if url.startswith("s3://"):
        url = url[5:]   # strip off
    first_slash = url.find("/")
    bucket_name = url[0:first_slash]
    file_name = url[first_slash + 1:]
    return bucket_name, file_name


def download_file(local_path, bucket_name, key):
    print(f'downloading {key} to {local_path}')
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
    local_path = "/tmp/temp.jpg"
    download_file(local_path, bucket_name, key)


def get_name_for_deskewed(image_file_name):
    # note that this also strips off any path
    name, ext = os.path.splitext(os.path.basename(image_file_name))
    return name + '-deskewed.' + ext


def get_destination_points(corners):
    """
    -Get destination points from corners of warped images
    -Approximating height and width of the rectangle: we take maximum of the 2 widths and 2 heights

    Args:
        corners: list

    Returns:
        destination_corners: list
        height: int
        width: int
    """

    w1 = np.sqrt((corners[0][0] - corners[1][0]) ** 2 + (corners[0][1] - corners[1][1]) ** 2)
    w2 = np.sqrt((corners[2][0] - corners[3][0]) ** 2 + (corners[2][1] - corners[3][1]) ** 2)
    w = max(int(w1), int(w2))

    h1 = np.sqrt((corners[0][0] - corners[2][0]) ** 2 + (corners[0][1] - corners[2][1]) ** 2)
    h2 = np.sqrt((corners[1][0] - corners[3][0]) ** 2 + (corners[1][1] - corners[3][1]) ** 2)
    h = max(int(h1), int(h2))

    destination_corners = np.float32([(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)])

    print('\nThe destination points are: \n')
    for index, c in enumerate(destination_corners):
        character = chr(65 + index) + "'"
        print(character, ':', c)

    print('\nThe approximated height and width of the original image is: \n', (h, w))
    return destination_corners, h, w


def unwarp(img, src, dst):
    """
    Args:
        img: np.array
        src: list
        dst: list

    Returns:
        un_warped: np.array
    """
    h, w = img.shape[:2]
    H, _ = cv2.findHomography(src, dst, method=cv2.RANSAC, ransacReprojThreshold=3.0)
    print('\nThe homography matrix is: \n', H)
    un_warped = cv2.warpPerspective(img, H, (w, h), flags=cv2.INTER_LINEAR)
    return un_warped


def deskew_image(vertices):
    # need to make sure points are ordered UL, UR, LL, LR (upper/lower left/right)
    leftmost = set(sorted(vertices, key=lambda el: el['x'])[:2])
    topmost = set(sorted(vertices, key=lambda el: el['y'])[:2])
    rightmost = set(sorted(vertices, reverse=True, key=lambda el: el['x'])[:2])
    bottommost = set(sorted(vertices, reverse=True, key=lambda el: el['y'])[:2])

    upperleft = leftmost & topmost
    upperright = rightmost & topmost
    bottomleft = leftmost & bottommost
    bottomright = rightmost & bottommost

    corners = [upperleft.pop(), upperright.pop(), bottomleft.pop(), bottomright.pop()]

    # load the image so we can deskew it
    image = cv2.imread('/tmp/temp.jpg')
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)

    # now deskew
    destination_points, h, w = get_destination_points(corners)
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    un_warped = unwarp(image, np.float32(corners), destination_points)
    cropped = un_warped[0:h, 0:w]

    return cropped


def process_results(event):
    # step 1: download the JSON file that contains our annotation data
    url = event["payload"]["s3Uri"]
    bucket_name, file_name = get_bucket_and_key(url)
    data = get_json_from_s3(bucket_name, file_name)

    # step 2: parse the JSON sent back from the UI
    for item in data:
        # get the corners
        all_annotations = item['annotations']
        for annotation in all_annotations:
            all_data = json.loads(annotation['annotationData']['content'])
            print(f'Got the following data from annotations: {json.dumps(all_data, indent=2)}')
            # each annotation has a list of vertices
            vertices = all_data['annotatedResult']['polygons']['vertices']

        print(f'Got vertices: {json.dumps(vertices, indent=2)}')

        # get the name of the image that was processed
        # and download it from S3 to local storage as /tmp/temp.jpg
        image_file_name = item['dataObject']['s3Uri']
        download_image(bucket_name, image_file_name)

        # de-skew it
        deskewed_image = deskew_image(vertices)

        # and save it to a new file name (based on the original)
        new_image_name = get_name_for_deskewed(image_file_name)
        print(f'Deskewed image will be saved as {new_image_name}')
        cv2.imwrite(new_image_name, deskewed_image)

        # and then copy from local /tmp back to S3, so the next job can get it
        upload_from_local_file(bucket_name, new_image_name, f'/tmp/{new_image_name}')


def lambda_handler(event, context):
    logger.info(f'In lambda post_step1 for event {json.dumps(event, indent=2)}')
    return process_results(event)
