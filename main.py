###########################################################################################
###### MAIN SCRIPT
###########################################################################################

import time
import os
import serial
import pandas as pd
from merge import *
from ftp_reader import *
from gps_reader import *
import serial.tools.list_ports as stlp
import sys
from connectivity import Connection
from sftp_aws import Transfer
from datetime import datetime, timedelta
import logging
import setup_rtd
import paramiko
import ftplib
import warnings

warnings.filterwarnings('ignore')

logging.basicConfig(filename=setup_rtd.parameters['path'] + 'logs/main.log',
                    format='%(levelname)s %(asctime)s :: %(message)s',
                    level=logging.DEBUG)
logging.debug('Start recording..')


class Profile(object):
    def __init__(self, sensor_type):
        self.vessel_name = setup_rtd.parameters['vessel_name']  # depending on the vessel
        self.l_sensors = sensor_type
        self.tow_num = len(os.listdir(setup_rtd.parameters['path'] + 'merged'))
        self.path = setup_rtd.parameters['path']
        self.gear = setup_rtd.parameters['gear_type']
        self.flag_gps = True

    def main(self):
        device = self.list_ports('USB-Serial Controller D')
        if self.flag_gps: gps = GPS(device, self.path)

        for sensor in self.l_sensors:
            # NKE necessary variable
            if sensor == 'NKE':
                ftp_conn = sensor(self.path)

            # Moana necessary variables
            elif sensor == 'Moana':
                d_moana_ini = {sn: os.listdir(self.path + 'logs/raw/Moana/' + sn) for sn in
                               os.listdir(self.path + 'logs/raw/Moana/')}

            # Lowell necessary variable
            elif sensor == 'Lowell':
                l_lowell = os.listdir(self.path + 'logs/raw/Lowell')

        old_time = datetime.now()

        while True and self.flag_gps:
            curr_time = datetime.now()
            gps.add_df()
            if (curr_time - old_time).total_seconds() / 60 > 5:
                logging.debug('Adding data to gps file')
                print('Adding data to gps file')
                gps.store_all_csv()
                old_time = curr_time
                stats = os.stat(self.path + 'gps/gps_merged.csv')
                if stats.st_size > 1728000:
                    gps.zip_file()

            for sensor in self.l_sensors:
                if sensor == 'NKE':
                    try:
                        if ftp_conn.file_received():
                            logging.debug('New file downloading: ')
                            l_rec_file = ftp_conn.transfer()
                            logging.debug('Downloading completed ' + l_rec_file[0])
                            logging.debug('Adding data to gps file')
                            print('Adding data to gps file')
                            gps.store_all_csv()
                            try:
                                self.connect_wireless(l_rec_file, sensor)
                            except:
                                pass
                            ldata = Merge().merge(l_rec_file, sensor, self.gear)  # set sensor type as WiFi or Bluetooth
                            self.cloud(ldata, sensor)

                            print('waiting...')
                            time.sleep(5)

                            ftp_conn = sensor(self.path)
                    except ftplib.all_errors:
                        ftp_conn.reconnect()

                elif sensor == 'Moana':
                    with open(self.path + 'status.txt') as f_ble:
                        d_moana = {sn: os.listdir(self.path + 'logs/raw/Moana/' + sn) for sn in
                                   os.listdir(self.path + 'logs/raw/Moana/')}
                        l_rec_file = []
                        if len(d_moana_ini) != len(d_moana):
                            sn_news = [sn for sn in d_moana if sn not in d_moana_ini]
                            for sn_new in sn_news:
                                if '1' in f_ble.readline():
                                    l_rec_file = [sn_new + '/' + file for file in d_moana[sn_new]]
                                    l_rec_file.sort()
                        else:
                            for sn in d_moana:
                                if len(d_moana_ini[sn]) != len(d_moana[sn]):
                                    if '1' in f_ble.readline():
                                        l_rec_file = [sn + '/' + file for file in d_moana[sn] if
                                                      file not in d_moana_ini[sn]]
                                        l_rec_file.sort()

                        if len(l_rec_file) > 0:
                            print('New Moana sensor file completely transferred to the RPi')
                            logging.debug('Adding data to gps file')
                            print('Adding data to gps file')
                            gps.store_all_csv()

                            try:
                                self.connect_wireless(l_rec_file, sensor)
                            except:
                                pass
                            ldata = Merge().merge(l_rec_file, sensor,
                                                  self.gear)  # set sensor type as WiFi or Bluetooth

                            # leMOLT = [self.add_eMOLT_header(e[0], e[1], sensor) for e in ldata]  # creates files with eMOLT format
                            # self.eMOLT_cloud(leMOLT)  # sends merged data to eMOLT endpoint
                            self.cloud(ldata, sensor)
                            d_moana_ini = d_moana.copy()
                            print('waiting for the next profile...')

                elif sensor == 'Lowell':  # there are more than one type of sensor onboard
                    ln_lowell = os.listdir(self.path + 'logs/raw/Lowell')
                    if len(ln_lowell) > len(l_lowell):
                        print('New sensor data from Lowell logger')
                        n_lowell = [e for e in ln_lowell if e not in l_lowell]  # stores only new Lowell data
                        gps.store_all_csv()  # necessary to store any gps data between the 10 minutes gps gap
                        self.connect_wireless(n_lowell, 'Lowell')  # sends raw data to BDC endpoint
                        ldata = Merge().merge(n_lowell, sensor, self.gear)  # merges sensor data and GPS

                        # leMOLT = [self.add_eMOLT_header(e[0], e[1], sensor) for e in ldata]  # creates files with eMOLT format
                        # self.eMOLT_cloud(leMOLT)  # sends merged data to eMOLT endpoint
                        self.cloud(ldata, sensor)  # sends merged data to BDC endpoint
                        print('waiting for the next profile...')

    def cloud(self, ldata, sensor):
        for filename, df in ldata:
            if len(df) < 2:
                print('Merged file is too small to be uploaded')
                continue
            conn_type = Connection().conn_type()
            if conn_type:  # wifi
                print('There is internet connection')
                Transfer(self.path + 'merged/{sensor}/'.format(sensor=sensor) + filename,
                         self.vessel_name + '/merged/' + sensor + '/' + filename)
                print('Data transferred successfully to the AWS endpoint')
            else:
                logging.debug('There is no network available')
                print(
                    'There is no network available, merged data has not been uploaded, queued routine will try to upload the data later')
                df.to_csv(self.path + 'queued/{sensor}/'.format(sensor=sensor) + filename, index=False)
            self.tow_num += 1

    def connect_wireless(self, l_rec_file, sensor):
        conn_type = Connection().conn_type()
        if conn_type:
            data_gps = pd.read_csv(self.path + 'gps/gps_merged.csv')
            data_gps['DATETIME'] = pd.to_datetime(data_gps['DATETIME'])
            data_gps = data_gps[data_gps['DATETIME'] > (datetime.utcnow() - timedelta(days=1))]
            gps_name = 'gps' + datetime.utcnow().strftime('%y%m%d') + '.csv'
            data_gps.to_csv(self.path + 'logs/gps/' + gps_name, index=False)
            try:
                Transfer(self.path + 'logs/gps/' + gps_name, self.vessel_name + '/gps/' + gps_name)
            except paramiko.ssh_exception.SSHException:
                logging.debug('GPS data was not uploaded')
                print('GPS data was not uploaded')

            for file in l_rec_file:
                Transfer(self.path + 'logs/raw/{sensor}/'.format(sensor=sensor) + file,
                         self.vessel_name + '/raw/' + sensor + '/' + file.split('/')[-1])

    def dd2dms(self, dd):
        mnt, sec = divmod(dd * 3600, 60)
        deg, mnt = divmod(mnt, 60)
        mnts = '0' + str(int(mnt)) if len(str(int(mnt))) == 1 else str(int(mnt))
        return str(int(deg)) + str(int(mnt)) + '.' + str(int(sec * 1000))[:4]

    def satellite(self, dev, msg):
        device = self.list_ports(dev)
        rb = rockBlock.rockBlock(device, self)
        rb.sendMessage(msg)
        rb.close()
        time.sleep(5)

    def eMOLT_cloud(self, ldata):
        for filename, df in ldata:
            # print u
            session = ftplib.FTP('', '', '')
            file = open(filename, 'rb')
            session.cwd("/BDC")
            # session.retrlines('LIST')               # file to send
            session.storbinary("STOR " + filename.split('/')[-1], fp=file)  # send the file
            # session.close()
            session.quit()  # close file and FTP
            time.sleep(1)
            file.close()
            print(filename.split('/')[-1], 'uploaded in eMOLT endpoint')

    def add_eMOLT_header(self, filename, data, sensor):
        date_file = data['DATETIME'].iloc[-1]
        # date_file = datetime.strptime(date_file, '%Y-%m-%d %H:%M:%S')
        date_file = date_file.strftime('%Y%m%d_%H%M%S')
        logger_timerange_lim = setup_rtd.metadata['time_range']
        logger_pressure_lim = setup_rtd.metadata['Fathom'] * 1.8288  # convert from fathom to meter
        transmit = setup_rtd.metadata['transmitter']
        boat_type = setup_rtd.metadata['gear_type']
        vessel_num = str(setup_rtd.metadata['vessel_num'])
        vessel_name = setup_rtd.metadata['vessel_name']
        tilt = setup_rtd.metadata['tilt']
        if sensor == 'Lowell':
            MAC_FILTER = [setup_rtd.metadata['mac_addr']]
            MAC_FILTER[0] = MAC_FILTER[0].lower()
            new_filename = self.path + 'merged/eMOLT/{sensor}/'.format(
                sensor=sensor) + 'li_{SN}_{date}_{vessel}.csv'.format(SN=MAC_FILTER[0][-5:], date=date_file,
                                                                      vessel=vessel_name)
        elif sensor == 'Moana':
            MAC_FILTER = [setup_rtd.parameters['moana_SN']]
            new_filename = self.path + 'merged/eMOLT/{sensor}/'.format(
                sensor=sensor) + 'zt_{SN}_{date}_{vessel}.csv'.format(SN=MAC_FILTER[0][-5:], date=date_file,
                                                                      vessel=vessel_name)
        header_file = open(self.path + 'header.csv', 'w')
        header_file.writelines('Probe Type,{sensor}\nSerial Number,'.format(sensor=sensor) + MAC_FILTER[0][
                                                                                             -5:] + '\nVessel Number,' + vessel_num + '\nVessel Name,' + vessel_name + '\nDate Format,YYYY-MM-DD\nTime Format,HH24:MI:SS\nTemperature,C\nDepth,m\n')  # create header with logger number
        header_file.close()

        # AFTER GETTING THE TD DATA IN A DATAFRAME
        data.rename(columns={'DATETIME': 'datet(GMT)', 'TEMPERATURE': 'Temperature (C)', 'PRESSURE': 'Depth (m)',
                             'LATITUDE': 'lat', 'LONGITUDE': 'lon'},
                    inplace=True)

        data['HEADING'] = 'DATA'  # add header DATA line
        data.reset_index(level=0, inplace=True)
        data.index = data['HEADING']
        data = data[['datet(GMT)', 'lat', 'lon', 'Temperature (C)', 'Depth (m)']]
        data.to_csv(self.path + 'merged/{sensor}/{file}'.format(sensor=sensor, file=filename[:-4]) + '_S1.csv')

        os.system(
            'cat ' + self.path + 'header.csv ' + self.path + 'merged/{sensor}/{file}_S1.csv > '.format(sensor=sensor,
                                                                                                       file=filename[
                                                                                                            :-4]) + new_filename)
        os.system('rm ' + self.path + 'merged/{sensor}/{file}_S1.csv'.format(sensor=sensor, file=filename[:-4]))

        print('New file created as {file} to be sent to eMOLT endpoint'.format(file=new_filename))
        return new_filename, data

    def list_ports(self, desc):
        list_usb = []
        if sys.platform.startswith('linux'):
            list_usb = serial.tools.list_ports.comports()

        for port in list_usb:
            try:
                if port.description == desc:
                    return port.device
            except (OSError, serial.SerialException):
                print('GPS puck is not connected')
                pass
        return


# when power on
while True:
    try:
        print("RPi started recording the main routine.\n")
        Profile(setup_rtd.parameters['sensor_type']).main()
    except:
        print('Unexpected error:', sys.exc_info()[0])
