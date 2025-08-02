import streamlit as st
import requests
import json
import csv
import io
from datetime import datetime, timedelta

# --- 1. UI Configuration ---
st.set_page_config(page_title="SolarEdge Data Downloader", layout="wide")
st.title("☀️ SolarEdge Data Downloader")

# --- 2. Login Function ---
def check_login():
    """Displays a login form and handles authentication."""
    st.header("Login")
    with st.form("login_form"):
        username = st.text_input("Username").lower()
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")

        if submitted:
            try:
                # Retrieve credentials securely from secrets
                stored_usernames = st.secrets.get("credentials", {}).get("usernames", [])
                stored_passwords = st.secrets.get("credentials", {}).get("passwords", [])
                
                user_index = stored_usernames.index(username)
                if stored_passwords[user_index] == password:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("Invalid username or password")
            except (ValueError, IndexError):
                st.error("Invalid username or password")
    return False

# --- 3. Main Application ---
def run_app():
    """The main data downloader application, shown after successful login."""

    # --- Helper Functions ---
    def make_api_call(endpoint, params=None):
        """Makes an API call using the key from st.secrets."""
        base_url = "https://monitoringapi.solaredge.com"
        full_url = f"{base_url}/{endpoint}"
        
        if params is None:
            params = {}
        
        # Securely get API key from secrets for every call
        api_key = st.secrets.get("solaredge", {}).get("api_key")
        if not api_key:
            st.error("API key not found in secrets. Please configure it.")
            return None
        params['api_key'] = api_key
        
        try:
            response = requests.get(full_url, params=params)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            st.error(f"API request failed for {endpoint}: {e}")
            return None

    def create_csv_string(data, fieldnames):
        """Converts a list of dictionaries to a CSV formatted string."""
        string_io = io.StringIO()
        writer = csv.DictWriter(string_io, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)
        return string_io.getvalue()

    # --- Data Fetching Functions ---
    @st.cache_data
    def get_all_sites():
        """Fetches all sites for the dropdown menu."""
        data = make_api_call("sites/list", params={'size': 100})
        if data and data.get('sites', {}).get('site'):
            site_list = data['sites']['site']
            return {site['name']: site['id'] for site in site_list}
        st.warning("Could not fetch site list. Check API key or permissions.")
        return {"No sites found": None}

    def get_site_details(site_id):
        """Fetches site details and returns the raw JSON data."""
        return make_api_call(f"site/{site_id}/details")

    # --- UI Elements ---
    all_sites_dict = get_all_sites()
    
    selected_site_name = st.selectbox("1. Select a Site:", options=list(all_sites_dict.keys()))
    
    # List of endpoints for the UI, but we'll only implement logic for one
    api_endpoints = ["Site Details", "Site Energy", "Site Power", "Get Sensor List", "Get Sensor Data", "Get Meters Data"]
    selected_endpoint = st.selectbox("2. Select the API Endpoint:", options=api_endpoints)
    
    # Generate Files Button
    if st.button("Generate Download Files", type="primary"):
        selected_site_id = all_sites_dict.get(selected_site_name)

        if not selected_site_id:
            st.error("Invalid site selected.")
            return # Stop execution if site is not valid

        # Logic is currently only for "Site Details"
        if selected_endpoint == "Site Details":
            with st.spinner("Fetching site details..."):
                details_data = get_site_details(selected_site_id)

                if details_data:
                    # Prepare data for download buttons
                    raw_json_string = json.dumps(details_data, indent=4)
                    processed_details = details_data.get('details', {})
                    
                    if processed_details:
                        fieldnames = sorted(list(processed_details.keys()))
                        processed_csv_string = create_csv_string([processed_details], fieldnames)

                        st.success("✅ Your files are ready to download below!")
                        
                        col1, col2 = st.columns(2)
                        with col1:
                            st.download_button(
                               label="Download Raw JSON",
                               data=raw_json_string,
                               file_name=f'solaredge_site_{selected_site_id}_details_raw.json',
                               mime='application/json',
                            )
                        with col2:
                            st.download_button(
                               label="Download Processed CSV",
                               data=processed_csv_string,
                               file_name=f'solaredge_site_{selected_site_id}_details.csv',
                               mime='text/csv',
                            )
                    else:
                        st.warning("No processed details found in the API response to create a CSV.")
                else:
                    st.error("Failed to fetch data from the API.")
        else:
            st.warning(f"'{selected_endpoint}' is not implemented in this version. Please select 'Site Details'.")


# --- 4. App Entry Point ---
# Check if user is authenticated. If not, show the login form.
if not st.session_state.get("authenticated", False):
    check_login()
else:
    # If authenticated, show the main application.
    run_app()