import boto3
# import pysftp
import config
import setup_rtd

class Transfer(object):
	def __init__(self, local_path, remote_path):
		self.metadata = config.s3_details['development']
		self.s3 = boto3.client(self.metadata['service'],
							   aws_access_key_id=self.metadata['access_key'],
							   aws_secret_access_key=self.metadata['access_pwd'])

		self.s3.upload_file(local_path, self.metadata['s3_bucket_name'], remote_path)
