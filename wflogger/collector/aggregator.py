## Copyright 2009 Laurent Bovet <laurent.bovet@windmaster.ch>
##                Jordi Puigsegur <jordi.puigsegur@gmail.com>
##
##  This file is part of wfrog
##
##  wfrog is free software: you can redistribute it and/or modify
##  it under the terms of the GNU General Public License as published by
##  the Free Software Foundation, either version 3 of the License, or
##  (at your option) any later version.
##
##  This program is distributed in the hope that it will be useful,
##  but WITHOUT ANY WARRANTY; without even the implied warranty of
##  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
##  GNU General Public License for more details.
##
##  You should have received a copy of the GNU General Public License
##  along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import base
import datetime
import wfcommon.meteo

MAX_TH_SENSORS = 10  # 0 ..9 
MAIN_TH_SENSOR = 1   # sensor number 1 is the main TH sensor
INT_TH_SENSOR = 0    # sensor number 0 is the interior TH sensor

class AggregatorCollector(base.BaseCollector):
    '''
    Collects events, compute aggregated values incrementally and issues
    samples to an underlying storage on 'flush events'. Typically wrapped
    in a !flush element to receive the 'flush events'.

    [ Properties ]

    storage [storage]:
        The underlying storage receiving the aggregated samples.
    '''

    storage = None

    logger = logging.getLogger('collector.aggregator')

    ## Init internal data
    _rain_last = None

    initialized = False

    def init(self):
        if not self.initialized:
            self._new_period()
            self.initialized = True

    def _new_period(self):
        ## Temperature (up to 10 sensors, sensor number 1 is the main sensor)
        self._temp = {}
        for sensor in xrange(MAX_TH_SENSORS):
            self._temp[sensor] = []
        ## Humidity  (up to 10 sensors, sensor number 1 is the main sensor)
        self._hum = {}
        for sensor in xrange(MAX_TH_SENSORS):
            self._hum[sensor] = []
        ## Wind
        self._wind = []
        self._wind_dir = []
        ## Wind gust
        self._wind_gust = 0.0
        self._wind_gust_dir = None
        ## Rain
        if self._rain_last != None:
            self._rain_first = self._rain_last
        else:
            self._rain_first = None
        self._rain_rate = 0.0
        ## Pressure
        self._pressure = []
        ## UV
        self._uv_index = None
        ## Solar Rad
        self._solar_rad = []
        ## Log
        self._timestamp_last = None
        self.logger.info ('New period')


    def _report_rain(self, total, rate):
        if self._rain_first == None:
            self._rain_first = total
        self._rain_last = total
        if self._rain_rate < rate:
            self._rain_rate = rate

    def _report_wind(self, avgSpeed, dirDeg, gustSpeed, gustDir):
        self._wind_dir.append((avgSpeed, dirDeg))  # Keep vector to calculate composite wind direction
        self._wind.append(avgSpeed)
        if self._wind_gust < gustSpeed:
            self._wind_gust = gustSpeed
            self._wind_gust_dir = gustDir

    def _report_barometer_sea_level(self, pressure):
        self._pressure.append(pressure)

    def _report_temperature(self, temp, sensor):
        if sensor >= 0 and sensor < MAX_TH_SENSORS:
            self._temp[sensor].append(temp)

    def _report_humidity(self, humidity, sensor):
        if sensor >= 0 and sensor < MAX_TH_SENSORS:
            self._hum[sensor].append(humidity)

    def _report_uv(self, uv_index):
        if self._uv_index == None or self._uv_index < uv_index:
            self._uv_index = uv_index

    def _report_solar_rad(self, solar_rad):
        self._solar_rad.append(solar_rad)


    def get_data(self):
        data = {
            'temp': None,
            'hum': None,
            'pressure' : None,
            'wind': None,
            'wind_dir': None,
            'wind_gust' : None,
            'wind_gust_dir': None,
            'rain': None,
            'rain_rate': None,
            'uv_index' : None,
            'dew_point' : None,
            'solar_rad' : None
        }

        for sensor in xrange(MAX_TH_SENSORS):
            if sensor == MAIN_TH_SENSOR:
                tsn = 'temp'
                hsn = 'hum'
            elif sensor == INT_TH_SENSOR:
                tsn = 'tempint'
                hsn = 'humint'
            else:
                tsn = 'temp%d' % sensor
                hsn = 'hum%d' % sensor

            if len(self._temp[sensor]) > 0:
                data[tsn] = round(sum(self._temp[sensor])/len(self._temp[sensor]), 1)
            elif sensor == MAIN_TH_SENSOR:
                self.logger.warning('Missing temperature data from main sensor')

            if len(self._hum[sensor]) > 0:
                data[hsn] = round(sum(self._hum[sensor])/len(self._hum[sensor]), 1)
            elif sensor == MAIN_TH_SENSOR:
                self.logger.warning('Missing humidity data from main sensor')

        if len(self._wind) > 0:
            data['wind'] = round(sum(self._wind)/len(self._wind), 1)
            data['wind_dir'] = round(wfcommon.meteo.WindPredominantDirection(self._wind_dir), 1)
            data['wind_gust_dir'] = self._wind_gust_dir

            # Wind gust cannot be smaller than wind average
            # (might happen due to different sampling periods)
            if data['wind'] <= self._wind_gust:
                data['wind_gust'] = round(self._wind_gust, 1)
            else:
                data['wind_gust'] = round(data['wind'], 1)
        else:
            self.logger.warning('Missing wind data')

        if self._rain_first is not None:
            if self._rain_last > self._rain_first:
                data['rain'] = round(self._rain_last - self._rain_first, 1)
                data['rain_rate'] = round(self._rain_rate, 1)
            else:
                data['rain'] = 0.0
                data['rain_rate'] = 0.0
        else:
            self.logger.warning('Missing rain data')

        if len(self._pressure) > 0:
            ## QFF pressure (Sea Level Pressure)
            pressure = round(sum(self._pressure)/len(self._pressure), 1)
            data['pressure'] = pressure
        else:
            self.logger.warning('Missing pressure data')

        if data['temp'] and data['hum']:
            ## Dew Point
            data['dew_point'] = round(wfcommon.meteo.DewPoint(data['temp'], data['hum'], 'vaDavisVP'), 1)

        ## UV
        if self._uv_index != None:
            data['uv_index'] = int(self._uv_index)

        ## Solar rad
        if len(self._solar_rad) > 0:
            solar_rad = round(sum(self._solar_rad)/len(self._solar_rad), 1)
            data['solar_rad'] = solar_rad

        data['localtime'] = self._timestamp_last

        self.logger.debug('data = %s', data)

        return data

    def flush(self, context):
        if self._timestamp_last is not None:
            sample = self.get_data()
            self._new_period()

            self.logger.debug("Flushing sample: "+repr(sample))

            self.storage.write_sample(sample, context=context)
