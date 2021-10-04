import logging
import json
import os
import html
import boto3
import io
from PIL import Image, ImageEnhance

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
REGION = os.getenv('REGION', 'us-east-1')
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)
s3 = boto3.resource('s3', region_name=REGION)
TEMP_IMAGE_NAME = '/tmp/temp.jpg'
# keep track of how many of each class we write out, to assist in naming them
counts = {'empty': 0, 'full': 0}


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


def save_image(class_name, image, bucket_name):
    print(f'Saving image to S3: {class_name}, {image}, {bucket_name}')
    # keep track of how many of this class we've created, to keep file names unique
    class_name = class_name.lower()
    image_number = counts[class_name]
    counts[class_name] += 1
    filename = f'training_data/{class_name}/{class_name}-{image_number:05}.jpg'
    # and then convert the image into a file object and send to S3
    fileobj = io.BytesIO()
    image.save(fileobj, "JPEG")
    fileobj.seek(0)
    s3.Object(bucket_name, filename).upload_fileobj(fileobj)


# This function is used to create variations on a base (cropped) image, including
# varying the brightness, contrast and sharpness up and down
def save_base_plus_variants(class_name, image, bucket_name):
    save_image(class_name, image, bucket_name)

    # 1.0 is the baseline, so 1.2 is 20% higher, etc.
    ENHANCED_UP_FACTOR = 1.2
    ENHANCED_DOWN_FACTOR = 0.8

    # brightness up a bit
    enhancer = ImageEnhance.Brightness(image.copy())
    brighter_image = enhancer.enhance(ENHANCED_UP_FACTOR)
    save_image(class_name, brighter_image, bucket_name)

    # brightness down a bit
    darker_image = enhancer.enhance(ENHANCED_DOWN_FACTOR)
    save_image(class_name, darker_image, bucket_name)

    # contrast up a bit
    enhancer = ImageEnhance.Contrast(image.copy())
    more_contrast_image = enhancer.enhance(ENHANCED_UP_FACTOR)
    save_image(class_name, more_contrast_image, bucket_name)

    # contrast down a bit
    less_contrast_image = enhancer.enhance(ENHANCED_DOWN_FACTOR)
    save_image(class_name, less_contrast_image, bucket_name)

    # sharpness up a bit
    enhancer = ImageEnhance.Sharpness(image.copy())
    sharper_image = enhancer.enhance(ENHANCED_UP_FACTOR)
    save_image(class_name, sharper_image, bucket_name)

    # sharpness down a bit
    blurrier_image = enhancer.enhance(ENHANCED_DOWN_FACTOR)
    save_image(class_name, blurrier_image, bucket_name)


def process_results(event):
    # step 1: download the JSON file that contains our annotation data
    url = event["payload"]["s3Uri"]
    bucket_name, file_name = get_bucket_and_key(url)
    data = get_json_from_s3(bucket_name, file_name)
    return_data = []

    # step 2: parse the JSON sent back from the UI for each image
    for item in data:
        # get the name of the original image
        image_file_name = item['dataObject']['s3Uri']
        # use the name for the deskewed version
        deskewed_image_filename = get_name_for_deskewed(os.path.basename(image_file_name))
        # and download it from S3 to local storage as /tmp/temp.jpg
        download_image(bucket_name, deskewed_image_filename)

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
                right = left + width
                bottom = top + height
                label = bbox['label']   # 'Empty' or 'Full'

                # get the portion of the image defined by the bounding box
                # save it to S3, along with all of its variations
                with Image.open(TEMP_IMAGE_NAME) as image:
                    cropped_image = image.crop((left, top, right, bottom))
                    # take care of those images that have some kind of transparency, which doesn't save as a JPEG
                    cropped_image = cropped_image.convert('RGB')
                    # and save a copy in memory
                    base_cropped_image = cropped_image.copy()

                    # save the base extracted image plus adjustments to brightness, contrast and sharpness
                    save_base_plus_variants(label, cropped_image, bucket_name)

                    # and flipped left/right, plus adjusted brightness, contrast and sharpness
                    flipped_image = base_cropped_image.copy()
                    flipped_image = flipped_image.transpose(Image.FLIP_LEFT_RIGHT)
                    save_base_plus_variants(label, flipped_image, bucket_name)

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
