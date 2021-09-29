import logging
import json
import os
import html
import boto3

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


def process_results(event):
    # step 1: download the JSON file that contains our annotation data
    url = event["payload"]["s3Uri"]
    bucket_name, file_name = get_bucket_and_key(url)
    data = get_json_from_s3(bucket_name, file_name)
    return_data = []

    # step 2: parse the JSON sent back from the UI for each image
    for item in data:
        # get the name of the image that was processed
        # and download it from S3 to local storage as /tmp/temp.jpg
        image_file_name = item['dataObject']['s3Uri']
        download_image(bucket_name, os.path.basename(image_file_name))

        # get the bounding boxes
        all_annotations = item['annotations']
        for annotation in all_annotations:
            all_data = json.loads(annotation['annotationData']['content'])
            print(f'Got the following data from annotations: {json.dumps(all_data, indent=2)}')
            # each annotation is a bounding box
            bounding_boxes = all_data['myTexts']['boundingBoxes']
            for bbox in bounding_boxes:
                top = bbox['top']
                left = bbox['left']
                width = bbox['width']
                height = bbox['height']
                label = bbox['label']   # 'Empty' or 'Full'

                # get the portion of the image defined by the bounding box
                # save it to S3, along with all of its variations

        # and add this information to our return data for each image
        annotation_info = {
            "datasetObjectId": item['datasetObjectId'],
            "consolidatedAnnotation": {
                "content": {
                    "source-ref": item['dataObject']['s3Uri'],
                    event["labelAttributeName"]: {}
                }
            }
        }
        return_data.append(annotation_info)
    return return_data


def lambda_handler(event, context):
    logger.info(f'In lambda post_step2 for event {json.dumps(event, indent=2)}')
    logger.info(f'Region is {REGION}')
    return process_results(event)
