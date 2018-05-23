import bs4
import numpy as np
import pandas as pd
import re
import requests
import sys


def open_url(url, headers=None):
    """Read url and return as BeautifulSoup object."""
    res = requests.get(url, headers=headers)
    res.raise_for_status()
    soup = bs4.BeautifulSoup(res.text, 'lxml')
    return soup


def parse_station_name(soup):
    """Return the station name parsed from html document title"""
    remove = ' - Past 24 Hour Conditions - Environment Canada'
    station_name = soup.title.text.replace(remove, '').strip()

    # Hacky workaround to handle accented e in Montreal
    station_name = station_name.encode('ascii', 'replace').decode('utf-8')
    station_name = station_name.replace('??', 'e')

    return station_name


def parse_latlon(soup):
    """Return lat, lon parsed from html document"""
    coords = {}
    for nm in ['Latitude', 'Longitude']:
        regex = nm + ' [0-9]*.[0-9]'
        matches = re.findall(regex, soup.text)
        if len(matches) == 0:
            raise ValueError('Unable to find latitude')
        coords[nm] = float(matches[0].split(' ')[1].strip())

    # Longitude for all Canadian stations is deg W so convert to negative value
    coords['Longitude'] = -1 * coords['Longitude']
    return coords


def parse_row(row):
    """Return a list of items in the row, with some additional processing to
       clean the text data"""

    # First look for header rows
    entries = row.find_all('th')

     # Then look for table body rows
    if len(entries) == 0:
        entries = row.find_all('td')

    # List of items with extra whitespace stripped from exterior and interior of each string
    items = [re.sub(r'\s+', ' ', entry.text.strip()) for entry in entries]

    # Remove non-ascii characters from column names
    items = [item.encode('ascii', 'ignore').decode('utf-8') for item in items]

    return items


def parse_timezone_code(label):
    """Parse date/time label in table header for the 3-letter timezone code"""
    matches = re.findall('\(.*\)', label)
    if len(matches) == 0:
        raise ValueError(f'Cannot find timezone in {label}')
    timezone = matches[0].replace('(', '').replace(')', '')
    return timezone


def get_timezone(timezone_code):
    """Return timezone name for 3-letter timezone codes"""
    regions = ['Atlantic', 'Central', 'Eastern', 'Mountain', 'Newfoundland',
               'Pacific', 'Yukon']
    tz_dict = {}
    for region in regions:
        tz_dict[region[0] + 'ST'] = 'Canada/' + region
        tz_dict[region[0] + 'DT'] = 'Canada/' + region

    return tz_dict.get(timezone_code)


def parse_temperature(temp_str):
    """Return temperature value parsed from temperature string"""
    matches = re.findall('\(.*\)', temp_str)
    if len(matches) == 0:
        raise ValueError(f'Input {temp_str} does not match expected format')
    temp = float(matches[0].replace('(', '').replace(')', ''))
    return temp


def parse_wind(wind_str):
    """Return wind direction and wind speed parsed from wind string"""
    parts = wind_str.split(' ')
    if len(parts) == 1 and parts[0] == 'calm':
        wind_dir = None
        wind_speed = 0
    elif len(parts) >= 0:
        wind_dir = parts[0].strip()
        wind_speed = float(parts[1].strip())
    else:
        raise ValueError(f'Unable to parse wind {wind_str}')
    series = pd.Series([wind_dir, wind_speed],
                        index=['Wind Direction', 'Wind Speed (km/hr)'])
    return series


def imperial_units(label):
    """Return True if the label identifies a variable in Imperial units"""
    imperial = False
    for nm in ['(F)', '(inches)', '(mph)', '(mi)']:
        if label.endswith(nm):
            imperial = True
            break
    return imperial


def get_data(station_code, timezone_index=False):
    """Read past 24 hours weather data for a station and return as a Dataframe"""

    base_url = 'https://weather.gc.ca/past_conditions/index_e.html?station='
    url = base_url + station_code
    print('Loading ' + url)
    soup = open_url(url)
    station_name = parse_station_name(soup)
    coords = parse_latlon(soup)

    # HTML data table
    items = soup.findAll('div', {'id' : 'table-container'})
    table = items[0]
    rows = table.find_all('tr')

    # Nested list of data rows
    data_list = []
    date_str = ''
    header = ['Date'] + parse_row(rows[0])

    # Deal with wonky labels for humidex and wind chill columns
    for nm in ['Humidex', 'Wind chill']:
        if nm in header:
            ind = header.index(nm)
            header[ind] = nm + ' (C)'
        if nm in header:
            ind2 = header.index(nm)
            header[ind2] = nm + ' (F)'

    timezone_code = parse_timezone_code(header[1])
    timezone = get_timezone(timezone_code)
    for row in rows[1:]:
        items = parse_row(row)
        if len(items) == 1:
            # Date header - incorporate as column in the data
            date_str = items[0]
        else:
            data_list.append([date_str] + items)

    # Create dataframe
    data = pd.DataFrame(data_list, columns=header)

    # Remove columns with imperial measurements
    cols_remove = [col for col in data.columns if imperial_units(col)]
    data = data.drop(cols_remove, axis=1)

    # Parse temperature strings
    data['Temperature (C)'] = data['Temperature (C)'].apply(parse_temperature)

    # Parse dates and set index to datetime
    dt_format = '%d %b %Y %H:%M'
    time_col = header[1]
    times = pd.to_datetime(data['Date'] + ' ' + data[time_col], format=dt_format)
    if timezone_index:
        times = pd.DatetimeIndex(times, tz=timezone)
    data = data.set_index(times)
    data.index.name = 'Datetime'
    data = data.drop(['Date', time_col], axis=1)

    # Parse wind data into separation columns for wind direction and speed
    data = data.join(data['Wind(km/h)'].apply(parse_wind))
    data = data.drop('Wind(km/h)', axis=1)

    # Turn * to NaN in humidex data
    if 'Humidex (C)' in data.columns:
        data.loc[data['Humidex (C)'] == '*', 'Humidex (C)'] = np.nan

    # Drop the extra hour at the end, so that the dataframe is 24 hours long
    data = data[:24]

    # Reverse the row order so that time is increasing down the table
    data = data.iloc[::-1, :]

    # Add station code, station name, lat, lon, timezone, and hour of day
    columns = list(data.columns)
    data['Station ID'] = station_code.upper()
    data['Station Name'] = station_name
    data['Latitude'] = coords['Latitude']
    data['Longitude'] = coords['Longitude']
    data['Timezone'] = timezone
    data['Hour of Day'] = data.index.hour
    columns = ['Station ID', 'Station Name', 'Latitude', 'Longitude',
               'Timezone', 'Hour of Day'] + columns
    data = data[columns]

    return data


def main(savefile):
    """Extract weather data and save to csv files"""
    stations = ['yvr', 'yyj', 'yxs', 'yxy', 'yzf', 'yfb', 'yeg', 'yyc', 'yxe',
                'yqr', 'ywg', 'yqt', 'yyz', 'yow', 'yul', 'yqb', 'yfc', 'yhz',
                'yyg', 'yyt']
    df_list = []
    for station in stations:
        df_in = get_data(station)
        df_list.append(df_in)
    data = pd.concat(df_list, axis=0)
    columns = sorted(list(data.columns))
    first_cols = ['Timezone', 'Hour of Day', 'Station ID', 'Station Name',
                  'Latitude', 'Longitude', 'Conditions', 'Temperature (C)',
                  'Relativehumidity(%)']
    for col in first_cols:
        columns.remove(col)
    columns = first_cols + columns

    data = data[columns]
    print('Saving to ' + savefile)
    data.to_csv(savefile)
    return data


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1].endswith('.csv'):
        savefile = sys.argv[1]
    else:
        t0 = pd.datetime.now()
        t0 = t0.strftime('%Y-%m-%d_%H%M')
        savefile = f'weather_stations_{t0}.csv'
    main(savefile)
