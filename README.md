# Example of chained custom Ground Truth Jobs

This code demonstrates how to chain two custom AWS SageMaker Ground Truth labeling jobs together in order to perform multi-stage image labeling. In this case, assume we are creating a ML model that determines whether individual bins within a shelving unit are empty or full.

The first labeling job is used to de-skew an image, like a shelving unit photographed from an angle. The individual bins within the shelving unit won't be orthogonal due to the camera angle, so we'd like to isolate just the shelving unit, and also adjust for the angle if we can. The first job allows selection of four corners of the shelving unit using a polygon selection tool.

Once that labeling job is complete, the post-UI Lambda function will isolate the selected portion of the original image and save it as a new image into the same S3 bucket that the source image is in. Since this involves mapping from a non-orthogonal shape to a rectangle, there will be some image distortion in the final image. This process is called warping or deskewing.

The second, chained labeling job will take that new, warped image and do simple bounding box labeling of each bin within the shelving unit. The labels are `Empty` and `Full`, since bin images will be used to train a model to determine if restocking is required. Note that although the image is warped, it is easier selecting rectangular bounding box regions in it, than from the original image photographed from an angle. This is the reason we warped the image in the first place.

Once the second labeling job is complete, the post-UI Lambda function will isolate each labeled rectangle from the source image. Each of those extracted images will then have multiple variations created, including horizontal mirroring, and variations in brightness, contrast, and sharpness. All of those new (augmented) images will be saved in the same S3 bucket that the source image is in, with prefixes that are based on the selected label. These images can then be easily used to train a model.

## Requirements
You'll need AWS SAM and the AWS CLI installed in order to deploy the code.

[SAM Installation instructions](https://aws.amazon.com/serverless/sam/)

[AWS CLI Installation instructions](https://aws.amazon.com/cli/)

## Repo Structure

  ```text
  ├── README.md               - this file
  ├── template.yml            - SAM template to create Lambdas + IAM role
  ├── ground_truth            - HTML pages for custom GT labeling jobs
  ├── lambda_functions
      ├── pre_step1           - code for the first pre-human lambda function
      ├── post_step1          - code for the first post-human lambda function
      ├── pre_step2           - code for the second pre-human lambda function
      └── post_step2          - code for the second post-human lambda function
  ```

## Part 1: Deploy the infrastructure

The first step is to create all of the required infrastructure, which is done using `template.yml`.  SAM uses CloudFormation-style scripts to create required infrastructure, which in this case includes

- Lambda functions for the pre- and post-GT lamdbas
- An S3 bucket to store the original images, and generated images

To deploy the pipeline, go to the top level directory of your local version of this repo and use the following commands:

`sam build --use-container`

(Note that "--use-container" may not be necessary for you, depending on the operating system used.  On Windows computers it's generally needed, but you can try it without.)

Once the package is built, deployment can be performed using the following command:

`sam deploy --guided`

The "--guided" parameter instructs SAM to ask questions in order to deploy the SAM package.  When deploying locally, this is a good option to use.


## Part 2: Create a Ground Truth workforce
Using the AWS console, go to the SageMaker service, then click on `Labeling workforces`, which is located under `Ground Truth`.  To use a private workforce, click on the `Private` tab along the top of the screen.

Click on the `Create private team` button, enter a team name, and then click on the `Create private team` button on the lower right.

You can add people to your team by selecting it, then clicking on the `Workers` tab.  Then click on the `Add workers to team` button and enter the person's email address.

Please note the team ARN, which is visible when you select the team.  You'll need that ARN when setting up the GT labeling job.

## Part 3: Deploy the first Ground Truth job

Unfortunately, setting up labeling jobs in GT isn't supported by SAM or CloudFormation templates.  Because of this, you'll need to create it using the AWS console - that process is described next.

Your training images must be stored in an S3 bucket with CORS enabled.  The bucket created by the SAM template (described above) sets up the bucket with the correct CORS settings.

First, upload your training images to S3. These are the image files that show an entire shelving unit, photographed from an angle.  From a local directory that contains the images, issue the following command to copy them to an S3 bucket:

`aws s3 sync . s3://BUCKET_NAME`

The next step is to create a labeling job.

Go to the Ground Truth console (found under Amazon SageMaker), select `Labeling jobs`, then click on `Create labeling job`.  Choose a name for the job ('Step1' is a reasonable choice), then make sure that `Input data setup` is set to `Automated data setup`.  Browse to the S3 location where your images are stored, set the `Data type` to be `Image`, then create an IAM role with access to the S3 bucket your images reside in.  Once all this information is completed, click on the `Complete data setup` button.  This step will create a manifest file that lists out the image files available for the labeling job.

Under the `Task type` header, choose `Custom` as the Task category, then click on the `Next` button.

On the next page you'll specify the Worker Type as `Private` and choose the private workteam you set up in the earlier step.  Then copy the code from the `step1.html` file found in this repo and paste it into the text box under `Templates`.  Make sure the template type is set to `Custom`.  Next, using the dropdowns at the bottom of the page, select the pre- and post-GT Lambda functions for `Step1` that were created by the `cloudformation.yml` file you deployed in part 1 of these instructions.  Then click on the `Create` button to create the labeling job.

## Part 4: Do the labeling

At this point, log in as a labeler (a member of the labeling team created in step 2). You'll see a labeling job waiting for processing (if you do not, please wait 5 minutes and hit refresh, since there is sometimes a delay between creating a labeling job and it showing up for a labeler to process). Once the labeling job is started, click on the image at the four corners of the shelving unit in order to define a polygon. Be sure to click on the first vertex in order to close the polygon. Repeat this process for each of the original images.

## Part 5: Adding a chained labeling job

Once the first labeling job is complete, go to the Ground Truth console and stop the job. Wait until the status shows `Stopped`, and then select the job and choose `Chain Job`.  Since this is a chained job, many of the fields will be filled in for you. Be sure to paste in the HTML markup from `step2.html` (found under the the `ground_truth` folder in this repo), and select the `Step2` pre- and post-Lambdas from the dropdowns.

## Part 6: Do the labeling

The second chained labeling job is used to define bounding boxes around each bin in the now-deskewed image. Be sure to choose the label ("Empty" or "Full") and then draw bounding boxes for each bin.  Complete the labeling job.

## Part 7: Examine the results

The post-GT Lambda function for the `step2` labeling job extracts an image of each bin and then augments it through different image processing techniques such as horizontal flipping, and creating variations of brightness, contrast, and sharpness. The final resulting images are uploaded to the original S3 bucket, with a `training_data` prefix, and a "subfolder" based on the labels. These resulting images can then be used for model training.

## Security

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for more information.

## License

This library is licensed under the MIT-0 License. See the LICENSE file.

## Content Security Legal Disclaimer
The sample code; software libraries; command line tools; proofs of concept; templates; or other related technology (including any of the foregoing that are provided by our personnel) is provided to you as AWS Content under the AWS Customer Agreement, or the relevant written agreement between you and AWS (whichever applies). You should not use this AWS Content in your production accounts, or on production or other critical data. You are responsible for testing, securing, and optimizing the AWS Content, such as sample code, as appropriate for production grade use based on your specific quality control practices and standards. Deploying AWS Content may incur AWS charges for creating or using AWS chargeable resources, such as running Amazon EC2 instances or using Amazon S3 storage.

## Operational Metrics Collection
This solution collects anonymous operational metrics to help AWS improve the quality and features of the solution. Data collection is subject to the AWS Privacy Policy (https://aws.amazon.com/privacy/). To opt out of this feature, simply remove the tag(s) starting with “uksb-” or “SO” from the description(s) in any CloudFormation templates or CDK TemplateOptions.
