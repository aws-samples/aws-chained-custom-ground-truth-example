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
import json
import os
import html

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)


def get_bucket_and_key(url):
    url = html.unescape(url)
    if url.startswith("s3://"):
        url = url[5:]   # strip off
    first_slash = url.find("/")
    bucket_name = url[0:first_slash]
    file_name = url[first_slash + 1:]
    return bucket_name, file_name


def get_name_for_deskewed(image_file_name):
    # note that this also strips off any path
    name, ext = os.path.splitext(os.path.basename(image_file_name))
    new_name = name + '-deskewed' + ext
    print(f'get_name_for_deskewed({image_file_name}) = {new_name}')
    return new_name


def lambda_handler(event, context):
    logger.info(f'In lambda pre_step2 for event {json.dumps(event, indent=2)}')

    # Get source if specified
    source = event['dataObject']['source'] if "source" in event['dataObject'] else None

    # Get source-ref if specified
    source_ref = event['dataObject']['source-ref'] if "source-ref" in event['dataObject'] else None

    # if source field present, take that otherwise take source-ref
    task_object = source if source is not None else source_ref

    # Build response object, but substitute in the deskewed image name
    bucket, fname = get_bucket_and_key(task_object)
    new_image_name = get_name_for_deskewed(fname)
    task_object = f's3://{bucket}/{new_image_name}'

    output = {
        "taskInput": {
            "taskObject": task_object
        },
        "humanAnnotationRequired": "true"
    }

    print(output)

    # If neither source nor source-ref specified, mark the annotation failed
    if task_object is None:
        print(" Failed to pre-process {} !".format(event["labelingJobArn"]))
        output["humanAnnotationRequired"] = "false"

    return output
