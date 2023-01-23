import pandas as pd
import setup_rtd
from connectivity import Connection
from datetime import datetime
from sftp_aws import Transfer
import os

queued_wifi = os.listdir(setup_rtd.parameters['path'] + 'queued/Moana/')

if len(queued_wifi) > 0:
    server_name = ''
    server_id = 1
    conn_type = Connection().conn_type()

    for elem in queued_wifi:
        df_queue = pd.read_csv(setup_rtd.parameters['path'] + 'queued/Moana/' + elem, error_bad_lines=False)
        df_queue.DATETIME = pd.to_datetime(df_queue.DATETIME)
        diff = (datetime.now() - df_queue.DATETIME.max()).total_seconds() / 3600
        if diff <= 1200:
            metadata = ','.join(elem.split('_')) + '\n'
            Transfer(setup_rtd.parameters['path'] + 'merged/Moana/' + elem,
                     setup_rtd.parameters['vessel_name'] + '/merged/Moana/' + elem)
            os.remove(setup_rtd.parameters['path'] + 'queued/Moana/' + elem)
        else:
            df_queue.to_csv(setup_rtd.parameters['path'] + 'logs/no_rtd/' + elem, index=None)
            os.remove(setup_rtd.parameters['path'] + 'queued/Moana/' + elem)