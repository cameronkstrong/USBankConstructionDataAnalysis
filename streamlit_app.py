import streamlit as st
import pandas as pd
from ffiec_data_connect import credentials, ffiec_connection, methods
import plotly.express as px  # For pie chart visualization
from datetime import datetime

# Replace with your FFIEC credentials
USERNAME = "cameronkstrong03"
PASSWORD = "AI4aWtaFsaY8TMCyjOsS"

# Load the bank list from the updated CSV file
BANKS_CSV_PATH = "bankswregions_updated.csv"  # Ensure this path matches the file's location
banks_data = pd.read_csv(BANKS_CSV_PATH)

# Convert the DataFrame to a list of dictionaries
BANKS = banks_data.to_dict(orient="records")

# Streamlit app
st.title("Bank Construction Loan Analysis")

# Region selection (default: Northeast)
regions = sorted(banks_data["region"].dropna().unique())
selected_region = st.selectbox("Select Region", ["All"] + regions, index=(["All"] + regions).index("Northeast"))

# Filter states based on selected region
if selected_region == "All":
    filtered_states = banks_data["state"].unique()
else:
    filtered_states = banks_data[banks_data["region"] == selected_region]["state"].unique()

# State selection (default: Maine)
states = ["All"] + sorted(filtered_states)
selected_state = st.selectbox("Select State", states, index=states.index("ME") if "ME" in states else 0)

# County selection (filtered by state if selected, or by region)
if selected_state == "All":
    filtered_counties = banks_data[banks_data["region"] == selected_region]["county"].unique() if selected_region != "All" else banks_data["county"].unique()
else:
    filtered_counties = banks_data[banks_data["state"] == selected_state]["county"].unique()
selected_county = st.selectbox("Select County", ["All"] + sorted(filtered_counties))

# City selection (filtered by state and county, or region if no state is selected)
if selected_county == "All":
    if selected_state == "All":
        filtered_cities = banks_data[banks_data["region"] == selected_region]["city"].unique() if selected_region != "All" else banks_data["city"].unique()
    else:
        filtered_cities = banks_data[banks_data["state"] == selected_state]["city"].unique()
else:
    filtered_cities = banks_data[
        (banks_data["state"] == selected_state) & (banks_data["county"] == selected_county)
    ]["city"].unique()
selected_city = st.selectbox("Select City", ["All"] + sorted(filtered_cities))

# Generate valid reporting dates dynamically, delayed by one quarter
def generate_reporting_dates():
    today = datetime.today()
    current_year = today.year
    quarters = ["3/31", "6/30", "9/30", "12/31"]
    dates = []

    # Determine the most recent valid quarter
    if today.month in [1, 2, 3]:  # Q1: Delay to previous year's Q4
        latest_quarter = f"9/30/{current_year - 1}"
    elif today.month in [4, 5, 6]:  # Q2: Delay to Q1
        latest_quarter = f"12/31/{current_year - 1}"
    elif today.month in [7, 8, 9]:  # Q3: Delay to Q2
        latest_quarter = f"3/31/{current_year}"
    else:  # Q4: Delay to Q3
        latest_quarter = f"6/30/{current_year}"

    # Generate dates up to the most recent valid quarter
    for year in range(current_year, current_year - 5, -1):  # Generate dates for the last 5 years
        for quarter in quarters:
            date_str = f"{quarter}/{year}"
            date_obj = datetime.strptime(date_str, "%m/%d/%Y")
            if date_obj <= datetime.strptime(latest_quarter, "%m/%d/%Y"):
                dates.append(date_str)
    return sorted(dates, key=lambda x: datetime.strptime(x, "%m/%d/%Y"), reverse=True)

# Create the dropdown for reporting periods
reporting_dates = generate_reporting_dates()
reporting_period = st.selectbox("Select Reporting Period", reporting_dates)

# Filter banks based on selections
filtered_banks = [
    bank
    for bank in BANKS
    if (selected_region == "All" or bank["region"] == selected_region)
    and (selected_state == "All" or bank["state"] == selected_state)
    and (selected_county == "All" or bank["county"] == selected_county)
    and (selected_city == "All" or bank["city"] == selected_city)
]

# Manage session state for table display
if "show_selected_banks" not in st.session_state:
    st.session_state.show_selected_banks = False
if "analysis_results" not in st.session_state:
    st.session_state.analysis_results = None
if "chart_option" not in st.session_state:
    st.session_state.chart_option = "Total Construction Loans ($)"

# Run Analysis button
if st.button("Run Analysis"):
    if not filtered_banks:
        st.warning("No banks match the selected filters.")
    else:
        st.session_state.show_selected_banks = True
        creds = credentials.WebserviceCredentials(username=USERNAME, password=PASSWORD)
        conn = ffiec_connection.FFIECConnection()

        results = []
        for bank in filtered_banks:
            try:
                time_series = methods.collect_data(
                    session=conn,
                    creds=creds,
                    rssd_id=bank["rssd_id"],
                    reporting_period=reporting_period,
                    series="call"
                )

                # Filter for RCONF158 and RCONF159
                rconf158_data = next((item for item in time_series if item.get("mdrm") == "RCONF158"), None)
                rconf159_data = next((item for item in time_series if item.get("mdrm") == "RCONF159"), None)

                # Extract values
                rconf158_value = (rconf158_data.get("int_data", 0) * 1000) if rconf158_data else 0
                rconf159_value = (rconf159_data.get("int_data", 0) * 1000) if rconf159_data else 0
                total_construction_loans = rconf158_value + rconf159_value

                results.append({
                    "Bank Name": bank["name"],
                    "City": bank["city"],
                    "State": bank["state"],
                    "County": bank["county"],
                    "1-4 Family Residential Construction Loans ($)": rconf158_value,
                    "Other Construction and Land Development Loans ($)": rconf159_value,
                    "Total Construction Loans ($)": total_construction_loans,
                })
            except Exception as e:
                st.error(f"Error analyzing {bank['name']}: {e}")
                results.append({
                    "Bank Name": bank["name"],
                    "City": bank["city"],
                    "State": bank["state"],
                    "County": bank["county"],
                    "1-4 Family Residential Construction Loans ($)": "Error",
                    "Other Construction and Land Development Loans ($)": "Error",
                    "Total Construction Loans ($)": "Error",
                })

        st.session_state.analysis_results = pd.DataFrame(results)

# Only show the Selected Banks table if the analysis is not yet run
if st.session_state.show_selected_banks and st.session_state.analysis_results is None:
    st.write(f"### Selected Banks ({len(filtered_banks)} total)")
    st.dataframe(pd.DataFrame(filtered_banks))

# Display analysis results
if st.session_state.analysis_results is not None:
    df = st.session_state.analysis_results
    st.write("### Analysis Results")
    st.write("*Note: All amounts are presented in ones ($).*")

    # Pie chart visualization for construction loans
    st.write("### Construction Loans Distribution")
    st.session_state.chart_option = st.selectbox(
        "Select Loan Type for Pie Chart",
        ["Total Construction Loans ($)", "1-4 Family Residential Construction Loans ($)", "Other Construction and Land Development Loans ($)"]
    )
    try:
        pie_chart = px.pie(
            df,
            names="Bank Name",
            values=st.session_state.chart_option,
            title=f"{st.session_state.chart_option} by Bank",
            hole=0.4,
        )
        st.plotly_chart(pie_chart)
    except Exception as e:
        st.error(f"Error creating the pie chart: {e}")

    # Top 10 lenders table
    st.write("### Top 10 Lenders by Loan Size")
    try:
        df_filtered = df[df[st.session_state.chart_option].apply(lambda x: isinstance(x, (int, float)))].copy()
        top_10 = df_filtered[["Bank Name", st.session_state.chart_option]].sort_values(
            by=st.session_state.chart_option, ascending=False
        ).head(10).reset_index(drop=True)
        top_10.index += 1  # Adjust the index to start at 1
        st.write(f"Top 10 Lenders for {st.session_state.chart_option}")
        st.dataframe(top_10, use_container_width=True)
    except Exception as e:
        st.error(f"Error creating the top 10 table: {e}")

    # Option to download results
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Download Results as CSV",
        data=csv,
        file_name="bank_analysis_results.csv",
        mime="text/csv",
    )
