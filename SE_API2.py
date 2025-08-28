import streamlit as st
import requests
import json
import csv
import io
import logging
from datetime import datetime, date, time, timedelta

# --- 1. Logging Configuration ---
# Set up logging to a file for debugging by the app administrator
logging.basicConfig(
    filename='app_errors.log',
    level=logging.ERROR,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

# --- 2. UI Configuration ---
st.set_page_config(page_title="SolarEdge Data Downloader", layout="wide")

# --- 3. Login Function ---
def check_login():
    """Displays a login form and handles authentication."""
    st.title("☀️ SolarEdge Data Downloader")
    st.header("Login")
    with st.form("login_form"):
        username = st.text_input("Username").lower()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            try:
                # Safely get credentials from secrets
                credentials = st.secrets.get("credentials", {})
                stored_usernames = credentials.get("usernames", [])
                stored_passwords = credentials.get("passwords", [])
                user_index = stored_usernames.index(username)
                if stored_passwords[user_index] == password:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Invalid username or password")
            except (ValueError, IndexError):
                st.error("Invalid username or password")
    return False

# --- 4. Main Application ---
def run_app():
    """The main data downloader application, shown after successful login."""

    # --- Header with Title and Logout Button ---
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("☀️ SolarEdge Data Downloader")
    with col2:
        st.write("") # Spacer
        st.write("") # Spacer
        if st.button("Logout", use_container_width=True):
            st.session_state["authenticated"] = False
            st.rerun()
            
    def make_api_call(endpoint, params=None):
        """Makes an API call and returns the JSON response with intelligent error handling."""
        base_url = "https://monitoringapi.solaredge.com"
        full_url = f"{base_url}/{endpoint}"
        if params is None:
            params = {}
            
        api_key = st.secrets.get("solaredge", {}).get("api_key")
        if not api_key:
            st.error("API key not found in secrets. Please have the administrator configure it.")
            return None
        params['api_key'] = api_key
        
        try:
            response = requests.get(full_url, params=params)
            response.raise_for_status() # Raises an exception for 4xx or 5xx status codes
            return response.json()
        except requests.exceptions.RequestException as e:
            # Log the full technical error for the administrator
            logging.error(f"API Error on endpoint '{endpoint}': {e}")
            
            # --- Intelligent, User-Facing Error Logic ---
            if e.response is not None:
                # Check for the specific date-range error
                response_text = e.response.text.lower()
                if e.response.status_code == 403 and "date range" in response_text and "maximum" in response_text:
                    st.error("The date range you selected is too long for the requested Time Unit. Please select a shorter period and try again.")
                else:
                    # Generic error for other API issues
                    st.error(f"An API error occurred (Code: {e.response.status_code}). Please check your parameters and try again.")
            else:
                # Error for network issues where there's no response
                st.error("Could not connect to the SolarEdge server. Please check your network connection and try again.")
            return None

    def create_csv_string(data, fieldnames):
        """Converts a list of dictionaries to a CSV formatted string."""
        string_io = io.StringIO()
        writer = csv.DictWriter(string_io, fieldnames=fieldnames, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(data)
        return string_io.getvalue()

    @st.cache_data
    def get_all_sites():
        """Fetches all sites for the dropdown menu."""
        data = make_api_call("sites/list", params={'size': 100, 'status': 'Active,Pending'})
        if data and 'sites' in data and 'site' in data['sites']:
            site_list = data['sites']['site']
            return {site['name']: site['id'] for site in sorted(site_list, key=lambda x: x['name'])}
        return {"No sites found": None}

    # Define API endpoint descriptions
    endpoint_descriptions = {
        "Site Details": "Details of a chosen site.",
        "Site Energy": "Site energy measurements.",
        "Site Power": "Site power measurements in a 15-minute resolution.",
        "Get Sensor List": "The list of sensors installed in the site.",
        "Get Sensor Data": "The measurements of the sensors installed in site.",
        "Get Meters Data": "Information about each meter in the site including: lifetime energy, metadata and the device to which it’s connected to."
    }
    
    # --- UI Elements ---
    all_sites_dict = get_all_sites()
    st.subheader("1. Select Site and API Endpoint")
    selected_site_name = st.selectbox("Select a Site:", options=list(all_sites_dict.keys()))
    
    api_endpoints = list(endpoint_descriptions.keys())
    selected_endpoint = st.selectbox("Select the API Endpoint:", options=api_endpoints, help="Choose the data you want to download.")
    
    # Display the description for the selected endpoint, italicized
    if selected_endpoint in endpoint_descriptions:
        st.markdown(f"<i>{endpoint_descriptions[selected_endpoint]}</i>", unsafe_allow_html=True)

    st.subheader("2. Set Parameters")
    params = {}
    if selected_endpoint in ["Site Energy", "Get Sensor Data", "Get Meters Data"]:
        col1, col2 = st.columns(2)
        with col1:
            params['start_date'] = st.date_input("Start Date", date.today() - timedelta(days=7))
        with col2:
            params['end_date'] = st.date_input("End Date", date.today())

    if selected_endpoint == "Site Power":
        col1, col2 = st.columns(2)
        with col1:
            params['start_date_power'] = st.date_input("Start Date", date.today() - timedelta(days=1))
            params['start_time_power'] = st.time_input("Start Time", time(0, 0))
        with col2:
            params['end_date_power'] = st.date_input("End Date", date.today())
            params['end_time_power'] = st.time_input("End Time", time(23, 59))

    if selected_endpoint in ["Site Energy", "Get Meters Data"]:
        params['time_unit'] = st.selectbox("Time Unit", ["DAY", "QUARTER_OF_AN_HOUR", "HOUR", "WEEK", "MONTH", "YEAR"])

    st.subheader("3. Generate Files")
    if st.button("Generate Download Files", type="primary"):
        selected_site_id = all_sites_dict.get(selected_site_name)
        if not selected_site_id:
            st.error("Invalid site selected.")
            st.stop()

        with st.spinner(f"Fetching data for '{selected_endpoint}'..."):
            api_data = None
            processed_data = []
            fieldnames = []
            
            # --- API Logic for each endpoint... (This section remains unchanged) ---
            if selected_endpoint == "Site Details":
                api_data = make_api_call(f"site/{selected_site_id}/details")
                if api_data and 'details' in api_data:
                    details = api_data['details']
                    if 'location' in details and isinstance(details['location'], dict):
                        location_data = details.pop('location')
                        details.update({f"location_{k}": v for k, v in location_data.items()})
                    if 'publicSettings' in details and isinstance(details['publicSettings'], dict):
                         public_settings = details.pop('publicSettings')
                         details.update({f"public_{k}": v for k, v in public_settings.items()})
                    if 'uris' in details and isinstance(details['uris'], dict):
                        uris = details.pop('uris')
                        details.update({f"uri_{k.lower().replace(' ', '_')}": v for k, v in uris.items()})
                    processed_data = [details]
                    fieldnames = sorted(details.keys())
            elif selected_endpoint in ["Site Energy", "Site Power"]:
                endpoint_url = "energy" if selected_endpoint == "Site Energy" else "power"
                if selected_endpoint == "Site Energy":
                    api_params = {'startDate': params['start_date'].strftime('%Y-%m-%d'), 'endDate': params['end_date'].strftime('%Y-%m-%d'), 'timeUnit': params['time_unit']}
                else:
                    start_dt = datetime.combine(params['start_date_power'], params['start_time_power'])
                    end_dt = datetime.combine(params['end_date_power'], params['end_time_power'])
                    api_params = {'startTime': start_dt.strftime('%Y-%m-%d %H:%M:%S'), 'endTime': end_dt.strftime('%Y-%m-%d %H:%M:%S')}
                api_data = make_api_call(f"site/{selected_site_id}/{endpoint_url}", params=api_params)
                if api_data and api_data.get(endpoint_url, {}).get('values'):
                    base_info = {'timeUnit': api_data[endpoint_url].get('timeUnit'), 'unit': api_data[endpoint_url].get('unit')}
                    processed_data = [{**base_info, **v} for v in api_data[endpoint_url]['values']]
                    fieldnames = ['date', 'value', 'timeUnit', 'unit']
            elif selected_endpoint == "Get Sensor List":
                api_data = make_api_call(f"equipment/{selected_site_id}/sensors")
                if api_data and api_data.get('SiteSensors', {}).get('list'):
                    for gateway in api_data['SiteSensors']['list']:
                        for sensor in gateway.get('sensors', []):
                            processed_data.append({'gateway': gateway.get('connectedTo'), 'name': sensor.get('name'), 'measurement': sensor.get('measurement'), 'type': sensor.get('type')})
                    if processed_data:
                        fieldnames = ['gateway', 'name', 'measurement', 'type']
            elif selected_endpoint == "Get Sensor Data":
                api_params = {'startDate': params['start_date'].strftime('%Y-%m-%d'), 'endDate': params['end_date'].strftime('%Y-%m-%d')}
                api_data = make_api_call(f"site/{selected_site_id}/sensors", params=api_params)
                if api_data and api_data.get('siteSensors', {}).get('data'):
                    for gateway in api_data['siteSensors']['data']:
                        gateway_name = gateway.get('connectedTo')
                        for telemetry in gateway.get('telemetries', []):
                            entry_date = telemetry.pop('date', None)
                            for key, value in telemetry.items():
                                processed_data.append({'gateway': gateway_name, 'date': entry_date, 'measurement_type': key, 'value': value})
                    if processed_data:
                        fieldnames = ['gateway', 'date', 'measurement_type', 'value']
            elif selected_endpoint == "Get Meters Data":
                start_dt = datetime.combine(params['start_date'], time(0, 0))
                end_dt = datetime.combine(params['end_date'], time(23, 59))
                api_params = {'startTime': start_dt.strftime('%Y-%m-%d %H:%M:%S'), 'endTime': end_dt.strftime('%Y-%m-%d %H:%M:%S'), 'timeUnit': params['time_unit']}
                api_data = make_api_call(f"site/{selected_site_id}/meters", params=api_params)
                if api_data and api_data.get('meterEnergyDetails', {}).get('meters'):
                    base_info = {'timeUnit': api_data['meterEnergyDetails'].get('timeUnit'), 'unit': api_data['meterEnergyDetails'].get('unit')}
                    for meter in api_data['meterEnergyDetails']['meters']:
                        meter_info = {'meterSerialNumber': meter.get('meterSerialNumber'), 'model': meter.get('model'), 'meterType': meter.get('meterType')}
                        for value_entry in meter.get('values', []):
                            processed_data.append({**base_info, **meter_info, **value_entry})
                    if processed_data:
                        fieldnames = ['date', 'value', 'meterSerialNumber', 'model', 'meterType', 'timeUnit', 'unit']

            # --- Display Download Buttons ---
            if api_data and processed_data:
                st.success("✅ Your files are ready to download below!")
                today_str = datetime.now().strftime("%m%d%y")
                time_unit_str = f"_{params['time_unit'].lower()}" if 'time_unit' in params else ""
                base_filename = f'solaredge_{selected_site_id}_{selected_endpoint.replace(" ", "_").lower()}{time_unit_str}_{today_str}'
                raw_json_string = json.dumps(api_data, indent=4)
                processed_csv_string = create_csv_string(processed_data, fieldnames)
                col1, col2 = st.columns(2)
                with col1:
                    st.download_button(label="Download Processed CSV", data=processed_csv_string, file_name=f"{base_filename}.csv", mime='text/csv')
                with col2:
                    st.download_button(label="Download Raw JSON", data=raw_json_string, file_name=f"{base_filename}_raw.json", mime='application/json')
            elif api_data is None:
                pass 
            else:
                st.warning(f"The request was successful, but no data was found for '{selected_endpoint}' on this site with the selected parameters. This could be normal for sites without the specified equipment or for time periods with no data.")

    # --- Footer ---
    st.markdown("---")
    st.markdown("<i>For support or technical issues, please raise a ticket via the <a href='https://helpdesk.lopezgroup.com.ph/' target='_blank'>Service Desk Portal</a>.</i>", unsafe_allow_html=True)

# --- 5. App Entry Point ---
if not st.session_state.get("authenticated", False):
    check_login()
else:
    run_app()