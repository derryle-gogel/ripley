"""
Copyright ©2023. The Regents of the University of California (Regents). All Rights Reserved.

Permission to use, copy, modify, and distribute this software and its documentation
for educational, research, and not-for-profit purposes, without fee and without a
signed licensing agreement, is hereby granted, provided that the above copyright
notice, this paragraph and the following two paragraphs appear in all copies,
modifications, and distributions.

Contact The Office of Technology Licensing, UC Berkeley, 2150 Shattuck Avenue,
Suite 510, Berkeley, CA 94720-1620, (510) 643-7201, otl@berkeley.edu,
http://ipira.berkeley.edu/industry-info for commercial licensing opportunities.

IN NO EVENT SHALL REGENTS BE LIABLE TO ANY PARTY FOR DIRECT, INDIRECT, SPECIAL,
INCIDENTAL, OR CONSEQUENTIAL DAMAGES, INCLUDING LOST PROFITS, ARISING OUT OF
THE USE OF THIS SOFTWARE AND ITS DOCUMENTATION, EVEN IF REGENTS HAS BEEN ADVISED
OF THE POSSIBILITY OF SUCH DAMAGE.

REGENTS SPECIFICALLY DISCLAIMS ANY WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE. THE
SOFTWARE AND ACCOMPANYING DOCUMENTATION, IF ANY, PROVIDED HEREUNDER IS PROVIDED
"AS IS". REGENTS HAS NO OBLIGATION TO PROVIDE MAINTENANCE, SUPPORT, UPDATES,
ENHANCEMENTS, OR MODIFICATIONS.
"""

import boto3
from botocore.exceptions import ClientError, ConnectionError
from flask import current_app as app
from ripley.lib.util import utc_now
import smart_open
import zipstream


def find_all_dated_csvs(folder, csv_name):
    return [key for key in iterate_monthly_folder(folder) if csv_name in key]


def find_last_dated_csv(folder, csv_name):
    csv_dict = find_last_dated_csvs(folder, [csv_name])
    if csv_name in csv_dict:
        return csv_dict[csv_name]


def find_last_dated_csvs(folder, csv_names):
    csvs_by_name = {}
    for object_key in iterate_monthly_folder(folder):
        for csv_name in csv_names:
            if csv_name in object_key:
                csvs_by_name[csv_name] = object_key
    return csvs_by_name


def get_object_text(key):
    s3 = _get_s3_client()
    bucket = app.config['AWS_S3_BUCKET']
    try:
        _object = s3.get_object(Bucket=bucket, Key=key)
        contents = _object.get('Body')
        if not contents:
            app.logger.error(f'Failed to get S3 object contents: bucket={bucket}, key={key})')
            return None
        return contents.read().decode('utf-8')
    except (ClientError, ConnectionError, ValueError) as e:
        app.logger.error(f'Error retrieving S3 object text: bucket={bucket}, key={key}, error={e}')
        return None


def get_signed_urls(bucket, keys, expiration):
    client = _get_s3_client()
    return {key: _generate_signed_url(client, bucket, key, expiration) for key in keys}


def iterate_monthly_folder(folder):
    bucket = app.config['AWS_S3_BUCKET']
    prefix = f"{folder}/{utc_now().strftime('%Y/%m')}"
    session = _get_session()
    s3 = session.client('s3')

    try:
        paginator = s3.get_paginator('list_objects')
        page_iterator = paginator.paginate(Bucket=bucket, Prefix=prefix)
        for page in page_iterator:
            if 'Contents' in page:
                for o in page['Contents']:
                    object_key = o.get('Key')
                    yield object_key
    except Exception as e:
        app.logger.error(f'Search of S3 folder failed (s3://{bucket}/{prefix})')
        app.logger.exception(e)


def put_binary_data_to_s3(key, binary_data, content_type):
    try:
        bucket = app.config['AWS_S3_BUCKET']
        s3 = _get_s3_client()
        s3.put_object(Body=binary_data, Bucket=bucket, Key=key, ContentType=content_type)
        return True
    except Exception as e:
        app.logger.error(f'S3 put operation failed (bucket={bucket}, key={key})')
        app.logger.exception(e)
        return None


def stream_folder_zipped(folder_key):
    bucket = app.config['AWS_S3_BUCKET']
    z = zipstream.ZipFile(mode='w', compression=zipstream.ZIP_DEFLATED)
    session = _get_session()
    s3 = session.client('s3')

    try:
        paginator = s3.get_paginator('list_objects')
        page_iterator = paginator.paginate(Bucket=bucket, Prefix=folder_key)
        for page in page_iterator:
            if 'Contents' in page:
                for o in page['Contents']:
                    object_key = o.get('Key')
                    s3_url = f's3://{bucket}/{object_key}'
                    s3_stream = smart_open.open(s3_url, 'rb', transport_params={'session': session})
                    filename = object_key.replace(f'{folder_key}/', '')
                    z.write_iter(filename, s3_stream)
        return z
    except Exception as e:
        app.logger.error(f'Zip stream of S3 folder failed (s3://{bucket}/{folder_key})')
        app.logger.exception(e)
        return None


def stream_object_text(object_key):
    s3_url = f"s3://{app.config['AWS_S3_BUCKET']}/{object_key}"
    try:
        return smart_open.open(s3_url, 'r', transport_params={'session': _get_session()})
    except Exception as e:
        app.logger.error(f'S3 stream operation failed (s3_url={s3_url})')
        app.logger.exception(e)
        return None


def upload_dated_csv(local_name, remote_name, folder, timestamp):
    with open(local_name, mode='rb') as f:
        return put_binary_data_to_s3(f'{folder}/{timestamp[0:4]}/{timestamp[5:7]}/{timestamp}-{remote_name}.csv', f, 'text/csv')


def _get_s3_client():
    return _get_session().client('s3')


def _get_session():
    return boto3.Session(profile_name=app.config['AWS_PROFILE'])


def _generate_signed_url(client, bucket, key, expiration):
    return client.generate_presigned_url(
        ClientMethod='get_object',
        Params={
            'Bucket': bucket,
            'Key': key,
        },
        ExpiresIn=expiration,
    )
