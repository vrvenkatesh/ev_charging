import streamlit as st
import pandas as pd
import numpy as np
import time
import datetime
import pickle
import logging
import altair as alt
import os
from datetime import datetime
import pytz
import folium
from streamlit_folium import folium_static
from typing import Tuple
import base64
from pathlib import Path

print(os.getcwd())
from src.data_preprocessing import datetime_processing, userinput_processing, holiday_processing, create_x, \
    create_wide_y, make_time_features
import src.weather as w
import src.oasis as o
from src.weather import get_processed_hourly_7day_weather
import logging
import streamlit_scrollable_textbox as stx
from streamlit_geolocation import streamlit_geolocation

logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler())
logger.setLevel(logging.INFO)

print("---------------------------")
print("---------------------------")
logger.debug('starting app')
test_mode = True
logger.info(f'test mode is {test_mode}')
minimal = True

##########################################################################
## Establish functions
##########################################################################

@st.cache_resource
def load_model():
    model = pickle.load(open('models/model.pkl', 'rb'))
    model_final = pickle.load(open('models/model_04_10.pkl', 'rb'))
    reg_model = pickle.load(open('models/reg_model.pkl', 'rb'))
    return model, model_final, reg_model


def get_tou_pricing(site, start, end, tz='UTC-07:00'):
    pricing = pd.DataFrame(index=pd.date_range(start, end, inclusive='both', freq='h'), columns=['price', 'Pricing'])
    pricing.index = pricing.index.tz_localize(tz)
    if site == 'Office001':
        for i in list(pricing.index):
            # super off-peak
            if i.hour in range(9, 14):
                pricing.loc[i, 'price'] = 0.18
                pricing.loc[i, 'Pricing'] = 'Super Off-Peak'
            # peak
            elif i.hour in range(16, 22):
                pricing.loc[i, 'price'] = 0.40
                pricing.loc[i, 'Pricing'] = 'Peak'
            # off-peak
            else:
                pricing.loc[i, 'price'] = 0.20
                pricing.loc[i, 'Pricing'] = 'Off-Peak'
    else:
        for i in list(pricing.index):
            # super off-peak
            if i.hour in range(9, 14):
                pricing.loc[i, 'price'] = 0.12
                pricing.loc[i, 'Pricing'] = 'Super Off-Peak'
                # peak
            elif i.hour in range(16, 22):
                pricing.loc[i, 'price'] = 0.40
                pricing.loc[i, 'Pricing'] = 'Peak'
                # off-peak
            else:
                pricing.loc[i, 'price'] = 0.14
                pricing.loc[i, 'Pricing'] = 'Off-Peak'

    return pricing


# function to get all forecasts for each site at session start. to be used after introducting statefulness into the app
@st.cache_data
def get_forecasts(site: str) -> Tuple[pd.DataFrame]:
    lat, long = site2latlon[site]

    # returns the "today_forecast" for the weather in the dashboard, the "weather_df" for the model inference
    today_forecast, weather_df = get_processed_hourly_7day_weather(lat, long, test_mode=False)

    # this demand is for all sites, all time
    demand_forecast = sd.get_demand_forecast(range_start, range_end)
    wind_solar_forecast = sd.get_wind_and_solar_forecast(range_start, range_end)
    wind_solar_forecast['INTERVALSTARTTIME_GMT'] = pd.to_datetime(wind_solar_forecast['INTERVALSTARTTIME_GMT'], utc=True)
    solar_df = wind_solar_forecast[wind_solar_forecast['RENEWABLE_TYPE'] == 'Solar']
    wind_df = wind_solar_forecast[wind_solar_forecast['RENEWABLE_TYPE'] == 'Wind']
    return today_forecast, weather_df,  demand_forecast, solar_df, wind_df, wind_solar_forecast


def set_renewable_chart_legend_pos(chart, x, y):
    chart.layer[0].encoding.color.legend = alt.Legend(
        orient='none',
        legendX=x, legendY=y,
        direction='horizontal',
        titleAnchor='start')

    chart.layer[1].encoding.color.legend = alt.Legend(
        orient='none',
        legendX=x, legendY=y,
        direction='horizontal',
        titleAnchor='start')
    return chart

def make_recommendation(avail_df, pricing_df, solar_df, wind_df):

    wind_solar_df = pd.merge(solar_df, wind_df, on='INTERVALSTARTTIME_GMT', how='outer')
    wind_solar_df['MW'] = wind_solar_df['MW_x'] + wind_solar_df['MW_y']
    wind_solar_df = wind_solar_df.rename(columns={'INTERVALSTARTTIME_GMT': 'datetime'})
    pricing_df['datetime'] = pricing_df.index
    availability = avail_df.loc[avail_df['% available'] > 85, :]
    pricing = pricing_df.loc[pricing_df['price'] < 0.20, :]
    MW = wind_solar_df.loc[wind_solar_df['MW'] > wind_solar_df['MW'].mean(), :]


    if eco & cost:
        recommendation = pd.merge(availability, pricing, on='datetime', how='inner')
        if len(recommendation) > 0:
            if len(pd.merge(recommendation, MW, on='datetime', how='inner')) > 0:
                recommendation = pd.merge(recommendation, MW, on='datetime', how='inner')
                return recommendation
        elif len(pd.merge(availability, MW, on='datetime', how='inner')) > 0:
            recommendation = pd.merge(availability, MW, on='datetime', how='inner')
        elif len(pd.merge(pricing, MW, on='datetime', how='inner')) > 0:
            recommendation = pd.merge(pricing, MW, on='datetime', how='inner')
        else:
            recommendation = availability.reset_index()
        return recommendation
    elif eco:
        recommendation = pd.merge(availability, MW, on='datetime', how='inner')
        if len(recommendation) > 0:
            return recommendation
        else:
            return availability.reset_index()
    elif cost:
        recommendation = pd.merge(pricing, MW, on='datetime', how='inner')
        if len(recommendation) > 0:
            return recommendation
        else:
            return pricing
    else:
        return availability.reset_index()


def get_recommendation_chunks(og_recommendation):
    logger.info(f'getting recommendation chunks {type(og_recommendation)}, shape : {og_recommendation.shape}, columns: {og_recommendation.columns}')
    recommendation = og_recommendation.copy()
    if len(recommendation) == 1:
        return recommendation
    recommendation['time_delta'] = pd.to_datetime(recommendation['datetime']).diff()
    recommendation.loc[0, 'start'] = 1
    for i in range(len(recommendation) - 1):
        if recommendation['time_delta'].iloc[i + 1] != pd.Timedelta('1h'):
            recommendation.loc[i, 'end'] = 1
            recommendation.loc[i + 1, 'start'] = 1
        else:
            recommendation.loc[i, 'end'] = 0
            recommendation.loc[i + 1, 'start'] = 0
    recommendation.loc[len(recommendation) - 1, 'end'] = 1
    small_recommendation = recommendation.loc[(recommendation['start'] == 1) | (recommendation['end'] == 1), :]

    recommendation_start_end = []
    indx = list(small_recommendation.index)
    for count, i in enumerate(indx):
        if (small_recommendation.loc[i, 'start'] == 1) & (small_recommendation.loc[i, 'end'] == 1):
            recommendation_start_end.append(
                (small_recommendation.loc[i, 'datetime'], small_recommendation.loc[i, 'datetime'] + pd.Timedelta('1h')))
        elif small_recommendation.loc[i, 'start'] == 1:
            start = small_recommendation.loc[i, 'datetime']
            for j in indx[count:]:
                if small_recommendation.loc[j, 'end'] == 1:
                    end = small_recommendation.loc[j, 'datetime']
                    recommendation_start_end.append((start, end))
                    break
    final_list = []
    for i in recommendation_start_end:
        if i not in final_list:
            final_list.append(i)
    return final_list

def img_to_bytes(img_path):
    img_bytes = Path(img_path).read_bytes()
    encoded = base64.b64encode(img_bytes).decode()
    return encoded

def img_to_html(img_path):
    img_html = "<img src='data:image/png;base64,{}' class='img-fluid'>".format(
        img_to_bytes(img_path)
    )
    return img_html


##########################################################################
## Initialize variables
##########################################################################
# define locations
caltech_lat = 34.134785646454844
caltech_lon = -118.11691382579643

jpl_lat = 34.20142342818471
jpl_lon = -118.17126565774107

office_lat = 37.33680466796926
office_lon = -121.90743423142634

# create SystemDemand object
sd = o.SystemDemand()

#get today's datetime
today = datetime.today().date()

sites = ['Office001', 'Caltech', 'JPL']
site_ids = [2, 1, 19]
site2id = {k: v for (k, v) in zip(sites, site_ids)}
site2latlon = {'Caltech': (34.134785646454844, -118.11691382579643),
               'Office001': (37.33680466796926, -121.90743423142634),
               'JPL': (34.20142342818471, -118.17126565774107)}
# map locations to site names
logger.info(f'loaded site lat and long coordinates: {site2latlon.items()}')

site2tac = {2: 'PGE-TAC', 1: 'SCE-TAC', 19: 'SCE-TAC', }
today_forecast, demand_forecast, solar_df, wind_df, pricing, wind_solar_forecast = None, None, None, None, None, None
logger.info('initialized site variables and maps')


##########################################################################
## HTML layout
##########################################################################

st.set_page_config(page_title='Charge Buddy', page_icon=':zap:', layout='wide', initial_sidebar_state='auto')
col01, col02, col03 = st.columns(3)
# title in markdown to allow for styling and positioning
#st.markdown("<h1 style='text-align: center; color: orange;'>Charge Buddy</h1>", unsafe_allow_html=True) d
with col02:
    st.markdown("<p style='text-align: center; color: grey;' > " + img_to_html('img/ChargebuddyIconTransparent.jpeg') + "</p>", unsafe_allow_html=True)


st.markdown("<h3 style='text-align: center; color: green;'>Helping EV Owners find the best time to charge</h3>",
            unsafe_allow_html=True)

# creates a horizontal line
st.divider()

# # create columns for layout of the app (1st column is 70% of the page, 2nd column is 30%)
# col1, col2 = st.columns([0.7, 0.3])
col1 = st.container()
# create a sidebar for user input
st.sidebar.title("When and where?")
st.sidebar.subheader('Select charging site')

# create a dropdown menu for the user to select a site
site = st.sidebar.selectbox('Click below to select a charger location',
                            sites, index=1,
                            key='site',  # adds the site to the session state
                            label_visibility="collapsed"
                            )
logger.info(f'site selected: {st.session_state["site"]}')

m = folium.Map(location=[*site2latlon[st.session_state['site']]], zoom_start=9)
folium.Marker(
    location=[*site2latlon[st.session_state['site']]],
    popup=f"{st.session_state['site']}",
    icon=folium.Icon(color="green")
).add_to(m)

with st.sidebar:
    folium_static(m, width=260, height=200)

st.sidebar.subheader('Select your preference(s)')
eco = st.sidebar.checkbox('Eco-Friendly', key='eco')
cost = st.sidebar.checkbox('Low Cost', key='cost')
logger.info(f'eco selected: {st.session_state["eco"]}\nlow cost selected: {st.session_state["cost"]}')

st.sidebar.subheader('Select date')
start_date = st.sidebar.date_input("Start date", value=today, min_value=today, max_value=today + pd.Timedelta('6d'),
                                   key='start')
end_date = st.sidebar.date_input("End date", value=start_date + pd.Timedelta('1d'), min_value=today + pd.Timedelta('1d'),
                                 max_value=today + pd.Timedelta('7d'), key='end')
logger.info(f'date range selected is: {st.session_state["start"]} - {st.session_state["end"]}')
s_ls = [int(x) for x in str(start_date).split('-')]
e_ls = [int(x) for x in str(end_date).split('-')]
s, e = datetime(s_ls[0], s_ls[1], s_ls[2]), datetime(e_ls[0], e_ls[1], e_ls[2])
start_localized, end_localized = pytz.utc.localize(datetime(s_ls[0], s_ls[1], s_ls[2])), pytz.utc.localize(
    datetime(e_ls[0], e_ls[1], e_ls[2]))
if 'start' not in st.session_state.keys():
    st.session_state['start'] = start_localized
if 'end' not in st.session_state.keys():
    st.session_state['end'] = end_localized
logger.info(f'date range localized is: {st.session_state["start"]} - {st.session_state["end"]}')

range_start_ls = [int(x) for x in str(today).split('-')]
range_end_ls = [int(x) for x in str(today + pd.Timedelta('7d')).split('-')]
range_start = datetime(range_start_ls[0], range_start_ls[1], range_start_ls[2])
range_end = datetime(range_end_ls[0], range_end_ls[1], range_end_ls[2])

# st.sidebar.info('EDIT ME: This app is a simple example of '
#                 'using Streamlit to create a financial data web app.\n'
#                 '\nIt is maintained by [Paduel]('
#                 'https://twitter.com/paduel_py).\n\n'
#                 'Check the code at https://github.com/paduel/streamlit_finance_chart')

# TODO: is this a switch?


# pull data here
st.session_state.key = 0
##########################################################################
## Fetching Data
##########################################################################

today_forecast, future_weather_df, demand_forecast, solar_df, wind_df, wind_solar_forecast = get_forecasts(st.session_state.site)
pricing = get_tou_pricing(site, s, e)

# populate main column with availability chart
col1.column_config = {'justify': 'center'}
with col1:

    st.markdown(f"<h2 style='text-align: center; color: green;'>Availability at {site} </h2>",
                unsafe_allow_html=True)


with st.sidebar:
    if not minimal:
        user_loc = streamlit_geolocation()
        if any(list(user_loc.values())):
            st.write("Current Location: ")
            st.write("Latitude: ", str(user_loc['latitude']))
            st.write("Longitude: ", str(user_loc['longitude']))
            folium.Marker(
                location=[user_loc["latitude"], user_loc["longitude"]],
                popup="Your Current Location",
                icon=folium.Icon(color="green", icon="fa-user", prefix="fa-solid")
            ).add_to(m)
        else:
            st.write('Waiting for location...')

col1.column_config = {'justify': 'right'}
with col1:

##########################################################################
## Model Inference
##########################################################################
    # get time, demand, and weather features
    # combine the 3 feature sets
    # perform inference

    model, model_final, reg_model = load_model()

    logger.info(f'start date type {type(start_localized)} and value is {start_localized}')
    time_df = make_time_features(start_date, end_date)
    time_df['site'] = st.session_state['site']
    assert {'site', 'index'}.issubset(time_df.reset_index().columns)

    # future weather already loaded, add current site
    future_weather_df['site'] = st.session_state['site']
    assert {'site', 'time_utc'}.issubset(future_weather_df.reset_index().columns), f" site and time are not in {future_weather_df.reset_index().columns}"

    #demand_forecast = st.session_state[f'{site}_demand_forecast']
    logger.info(f'demand forecast loaded with shape {demand_forecast.shape} and columns: {demand_forecast.columns}')
    demand_forecast['datetime'] = pd.to_datetime(demand_forecast['OPR_DT']) + pd.to_timedelta(demand_forecast['OPR_HR'],
                                                                                              unit='h')
    # filter for location, via TAC
    demand = demand_forecast.loc[
             demand_forecast['TAC_AREA_NAME'] == site2tac[site2id[site]], :].set_index('datetime')
    # filter for only 7 day ahead
    demand = demand[demand['MARKET_RUN_ID'] == '7DA']

    demand['site'] = st.session_state['site']
    demand = demand.rename(columns={'MW': 'actual_demand_MW'}).sort_index()
    demand.index = demand.index.tz_localize('UTC-07:00')

    logger.info(f'demand loaded with shape {demand.shape} and columns: {demand.columns}')
    print(demand.reset_index().head())
    assert 'site' in demand.columns and 'datetime' in demand.reset_index().columns

    # combine
    features = ['dow', 'hour', 'month', 'is_holiday', 'actual_demand_MW',
                'temperature_degC', 'dewpoint_degC', 'relative_humidity_%',
                'wind_speed_mph', 'site']
    X = pd.DataFrame({}, columns=features)

    try:
        X = pd.merge(time_df.reset_index(), demand.reset_index(), how='left', left_on=['index', 'site'],
                     right_on=['datetime', 'site'])
    except:
        assert 1 == 0, 'failed to merge time_df and demand'
    try:
        X = pd.merge(X, future_weather_df.reset_index(), how='left', left_on=['index', 'site'],
                     right_on=['time_utc', 'site'])
    except:
        logger.info('failed to merge time, weather, and demand features')

    # set the datetime to the index
    X.index = X['index_x'].rename('datetime')

    # the demand is always missing midnight for some reason, so copy 1AM and imput it
    X.loc[X.index[0], 'actual_demand_MW'] = X.loc[X.index[1], 'actual_demand_MW']

    # keep only the feature columns desired for modeling
    X = X[features]
    logger.info(f"the X values for the model have features {X.columns}")
    logger.info(X.head(2))

    # for testing, uncomment these
    #X.to_csv('test/test_X.csv')
    #time_df.to_csv('test/test_time.csv')
    #demand.to_csv('test/test_demand.csv')
    #future_weather_df.to_csv('test/test_future_weather.csv', index_label='index')
    prediction = pd.Series(model_final.predict(X) * 100, index=X.index, name='% available')

    # regression messes up sometimes, bound the values between [0, 100]
    prediction[prediction > 100] = 100
    prediction[prediction < 0] = 0

    X['% available'] = prediction

    wind_solar_forecast = wind_solar_forecast.sort_values('INTERVALSTARTTIME_GMT').loc[
        (wind_solar_forecast['INTERVALSTARTTIME_GMT'] >= start_localized) & (
                    wind_solar_forecast['INTERVALSTARTTIME_GMT'] <= end_localized)]
    solar_df = solar_df.sort_values('INTERVALSTARTTIME_GMT').loc[
        (solar_df['INTERVALSTARTTIME_GMT'] >= X.index.min()) & (solar_df['INTERVALSTARTTIME_GMT'] <= X.index.max())]
    wind_df = wind_df.sort_values('INTERVALSTARTTIME_GMT').loc[
        (wind_df['INTERVALSTARTTIME_GMT'] >= X.index.min()) & (wind_df['INTERVALSTARTTIME_GMT'] <= X.index.max())]

    recommendation = make_recommendation(X, pricing, solar_df, wind_df)
    recommendation.to_csv('test/test_recommendation.csv')

    # TODO: move this line to the make_recommendations function
    recommendation = recommendation.drop_duplicates(subset=['datetime']).reset_index(drop=True)
##########################################################################
## Plotting
##########################################################################
    if len(recommendation) > 0:
        recommendation_chunks = get_recommendation_chunks(recommendation)
        rec_string_header = "Based on selected preferences, the recommended time(s) to charge are: "
        st.markdown(
            f"<p style='text-align: left; color: green;'>{rec_string_header}</p>",
            unsafe_allow_html=True)
        rec_string = ''
        for rec in recommendation_chunks:
            rec_string += f"{rec[0]:%A, %B %dth} from {rec[0].strftime('%I %p')} to {rec[1].strftime('%I %p')}\n"
        stx.scrollableTextbox(rec_string, height=100)
    else:
        st.markdown(f"<p style='text-align: left; color: green;'>No recommendations available based on your stated preferences</p>", unsafe_allow_html=True)
    st.write('Availability from ', start_date, ' to ', end_date)

    # create a column in the X dataframe that is true if the time is in the recommendation
    X['recommended'] = X.index.isin(recommendation['datetime'])

    def categorize_availability(val):
        availability = ['Very Available', 'Moderate', 'Busy', 'Very Busy']
        availability_txt = ''
        if val > 85:
            availability_txt = availability[0]
        elif val > 70:
            availability_txt = availability[1]
        elif val > 50:
            availability_txt = availability[2]
        else:
            availability_txt = availability[3]
        return availability_txt

    X['Availability'] = X['% available'].apply(categorize_availability)
    av_domain = ['Very Available', 'Moderate', 'Busy', 'Very Busy']
    av_range = ['seagreen', 'yellow', 'orange', 'firebrick']

    availability_chart = alt.Chart(X.reset_index()).mark_bar().encode(
        x=alt.X('datetime:T', title='Time'),
        y=alt.Y('% available:Q', title='Availability (%)'),
        tooltip=[alt.Tooltip('datetime:T', format="%Y-%m-%dT%H:%M:%S", title='Date'),
                 alt.Tooltip('% available:Q', format=",.1f", title='Availability (%)'),
                 alt.Tooltip('Availability')],
        color=alt.Color('Availability').scale(domain=av_domain, range=av_range).legend(orient="right")#alt.condition(alt.expr.datum['recommended'], alt.value('green'), alt.value('steelblue'))
    ).interactive()
    p_domain = ['Super Off-Peak', 'Off-Peak', 'Peak']
    p_range = ['seagreen', 'lightgreen', 'orange']
    #logger.info(f'pricing is {pricing.reset_index().info()}')
    pricing_chart = alt.Chart(pricing.reset_index(), title='Pricing').mark_bar().encode(
        x=alt.X('index:T', title='Time'),
        y=alt.Y('price:Q', title='Price ($/kWh)'),
        tooltip=[alt.Tooltip('index', title='Time'),
                 alt.Tooltip('price', title='Price ($/kWh)')],
        color=alt.Color('Pricing').scale(domain=p_domain, range=p_range).legend(orient='right')
    ).interactive()

    solar = alt.Chart(solar_df, title='Solar Forecast').mark_bar().encode(
        x=alt.X('INTERVALSTARTTIME_GMT:T', title='Time'),
        y=alt.Y('MW', title='Forecasted Solar Energy (MW)'),
        tooltip=[alt.Tooltip('INTERVALSTARTTIME_GMT', title='Time'),
                 alt.Tooltip('MW', title='Solar (MW)')],
        color=alt.Color('RENEWABLE_TYPE:N', title='Renewable Type').legend(orient="right")
    ).interactive()

    wind = alt.Chart(wind_df, title='Wind Forecast').mark_bar().encode(
        x=alt.X('INTERVALSTARTTIME_GMT:T', title='Time'),
        y=alt.Y('MW', title='Forecasted Wind Energy (MW)'),
        tooltip=[alt.Tooltip('INTERVALSTARTTIME_GMT', title='Time'),
                 alt.Tooltip('MW', title='Wind (MW)')],
        color=alt.Color('RENEWABLE_TYPE:N', title='Renewable Type').legend(orient="right")
    ).interactive()

    solar_chart = solar + wind
    solar_chart = solar_chart.properties(title='Renewable Energy Forecast')
    solar_chart.layer[0].encoding.y.title = 'Energy (MW)'
    solar_chart.layer[1].encoding.y.title = 'Energy (MW)'

    if eco & cost:
        #st.altair_chart(alt.vconcat(availability_chart, pricing_chart).resolve_scale(x='shared', y='independent'), use_container_width=True)
        st.altair_chart(availability_chart, use_container_width=True)
        st.divider()
        st.altair_chart(pricing_chart, use_container_width=True)
        st.divider()
        st.altair_chart(solar_chart, use_container_width=True)
        #solar_chart = set_renewable_chart_legend_pos(solar_chart, 700, 690)
        #st.altair_chart(alt.vconcat(availability_chart, pricing_chart, solar_chart).resolve_scale(x='shared', y='independent'), use_container_width=True)
    elif eco:
        st.altair_chart(availability_chart, use_container_width=True)
        st.divider()
        st.altair_chart(solar_chart, use_container_width=True)
        #solar_chart = set_renewable_chart_legend_pos(solar_chart, 700, 310)
        #st.altair_chart(alt.vconcat(availability_chart, solar_chart).resolve_scale(x='shared', y='independent'), use_container_width=True)
    elif cost:
        st.altair_chart(availability_chart, use_container_width=True)
        st.divider()
        st.altair_chart(pricing_chart, use_container_width=True)
        #st.altair_chart(alt.vconcat(availability_chart, pricing_chart).resolve_scale(x='shared', y='independent'), use_container_width=True)
    else:
        st.altair_chart(availability_chart, use_container_width=True)



    st.subheader(f'How often are spots available at {site}?')
    avg_availability = np.round(X['% available'].mean(), 1)

    availability_txt = categorize_availability(avg_availability)
    st.text(f'{availability_txt}. Average availability: ' + str(avg_availability) + '%')
    st.text('More locations coming soon!')

##########################################################################
## Weather Forecast
##########################################################################
#
# if not minimal:
#     col2.column_config = {'justify': 'right'}
#     with col2:
#         st.markdown(
#             f"<h3 style='text-align: center; color: white;'>Weather Forecast for {site} {today_forecast['name'].iloc[0]} </h3>",
#             unsafe_allow_html=True)
#         col2_1, col2_2 = st.columns([0.5, 0.5])
#         if today_forecast is not None:
#             logger.info(today_forecast.columns)
#             assert 'temperature_degF' in today_forecast.columns, f"no temperature in {today_forecast.columns}"
#             col2_1.metric('Temperature (F)', today_forecast['temperature_degF'].iloc[0])
#             col2_2.image(today_forecast['icon'].iloc[0], use_column_width=False)
#             col2_1.write(today_forecast['detailedForecast'].iloc[0])
#         else:
#             col2_1.write('Unable to retrieve forecast data')
#             if col2_1.button('Retry'):
#                 get_forecasts(site)
#         st.subheader("EV Charging Station Location")
#         folium_static(m, width=450, height=450)
