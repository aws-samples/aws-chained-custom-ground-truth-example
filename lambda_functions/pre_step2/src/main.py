import logging
import json
import os

LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
logger = logging.getLogger()
logger.setLevel(LOG_LEVEL)

def lambda_handler(event, context):
    logger.info(f'In lambda pre_step2 for event {json.dumps(event, indent=2)}')
    # nothing to do for the pre-GT Lambda, since the images get sent unaltered
    # to the GT labeling job
    return event
