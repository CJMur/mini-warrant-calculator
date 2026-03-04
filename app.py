import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="MINI Warrant Calculator", layout="wide")

# ==========================================
# Your live Google Sheet (Formatted for CSV output)
# ==========================================
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vREoxpGZIfWZGWyRF_I_N7KKJOC9OmGNgsPh7F0gRE4RN4RgBUUzhzk1h-ro6vSrlIg5rJRwXS5DXGr/pub?gid=0&single=true&output=csv"

# --- 1. DATA LOADING (Live from Google Sheets) ---
@st.cache_data(ttl=600) # Caches data for 10 mins 
def load_warrant_data():
    try:
        df = pd.read_csv(SHEET_CSV_URL)
        
        # Helper function to extract Yahoo Finance Ticker
        def get_ticker(code):
            if isinstance(code, str) and len(code) >= 3:
                if code.startswith('FX'): 
                    return None 
                return code[:3] + '.AX'
            return None
            
        df['Ticker'] = df['Code'].apply(get_ticker)
        
        # Default Funding Rates (8.7% Long, 0.1% Short) 
        df['Funding Rate'] = np.where(df['Type'] == 'MINI Long', 0.087, 0.001)
        
        # Default FX Rate to 1 for domestic ASX stocks
        df['FX Rate'] = 1.0
        
        return df
    except Exception as e:
        st.error(f"⚠️ Could not load data from Google Sheets. Error: {e}")
        return pd.DataFrame()

warrants_df = load_warrant_data()

# --- 2. SEARCH & SELECT MODULE ---
st.title("MINI Warrant Search & Calculator")

if not warrants_df.empty:
    col1, col2 = st.columns([1, 2])

    with col1:
        st.subheader("1. Search Warrants")
        search_query = st.text_input("Search by Ticker or Underlying (e.g., A2M, WTC):").upper()
        
        if search_query:
            filtered_df = warrants_df[
                warrants_df['Code'].astype(str).str.contains(search_query) | 
                warrants_df['Underlying'].astype(str).str.contains(search_query)
            ]
        else:
            filtered_df = warrants_df

        st.dataframe(
            filtered_df[['Code', 'Underlying', 'Type', 'Strike', 'Stop Loss Trigger Level', 'Bid', 'Ask']], 
            hide_index=True, 
            use_container_width=True
        )
        
        selected_warrant_code = st.selectbox("Select a Warrant Code to Analyze:", filtered_df['Code'].tolist())

    # --- 3. CALCULATOR MODULE ---
    if selected_warrant_code:
        warrant = warrants_df[warrants_df['Code'] == selected_warrant_code].iloc[0]
        
        # Fetch live price from Yahoo Finance
        live_price = warrant.get('Underlying Spot Price', 0.0) 
        
        if pd.notna(warrant['Ticker']):
            try:
                yf_data = yf.Ticker(warrant['Ticker']).history(period="1d")
                if not yf_data.empty:
                    live_price = yf_data['Close'].iloc[-1]
            except:
                pass 

        # Calculate Current Mini Fair Value
        multiplier = warrant.get('Multiplier', 1.0)
        
        if warrant['Type'] == 'MINI Long':
            current_mini_price = max(0, (live_price - warrant['Strike']) / (multiplier * warrant['FX Rate']))
        else:
            current_mini_price = max(0, (warrant['Strike'] - live_price) / (multiplier * warrant['FX Rate']))

        with col2:
            st.subheader(f"2. Calculator: {warrant['Code']}")
            
            # Display Static Info
            i_col1, i_col2, i_col3, i_col4, i_col5 = st.columns(5)
            i_col1.metric("Underlying", warrant['Underlying'])
            i_col2.metric("Type", warrant['Type'])
            i_col3.metric("Strike", f"${warrant['Strike']:.4f}")
            i_col4.metric("Stop Loss", f"${warrant.get('Stop Loss Trigger Level', 0):.2f}")
            i_col5.metric("Current Fair Value", f"${current_mini_price:.2f}")
            
            st.divider()

            # Editable Cyan Inputs
            st.markdown("### Scenario Inputs")
            in_col1, in_col2, in_col3, in_col4 = st.columns(4)
            
            with in_col1:
                base_share_price = st.number_input("Base Share Price", value=float(round(live_price, 2)), step=0.10)
                mini_qty = st.number_input("Mini QTY", value=200, step=100)
            with in_col2:
                adj_share_pct = st.number_input("ADJ Share %", value=2.0, step=1.0)
                adj_date_days = st.number_input("ADJ Date (Days)", value=1, step=1)
            with in_col3:
                calc_type = st.radio("Display Output As:", ["P&L %", "P&L $"])
            with in_col4:
                funding_rate = st.number_input("Funding Rate (%)", value=float(warrant['Funding Rate']*100), step=0.1) / 100
                st.info(f"**Max Risk:** ${(current_mini_price * mini_qty):.2f}")

            # --- MATRIX GENERATION ---
            st.markdown("### Pricing Matrix")
            
            # Generate Rows (Share Prices)
            steps = [10, 8, 6, 4, 2, 0, -2, -4, -6, -8, -10]
            row_prices = [base_share_price * (1 + (step * (adj_share_pct / 100) / 2)) for step in steps]
            
            # Generate Columns (Dates)
            dates = [datetime.today() + timedelta(days=i * adj_date_days) for i in range(7)]
            date_strs = [d.strftime('%m/%d/%Y') for d in dates]
            
            # Calculate daily interest added to strike
            daily_interest = (warrant['Strike'] * funding_rate) / 365
            
            matrix_data = []
            for price in row_prices:
                row_data = {"Share Price": f"${price:.2f}"}
                for i, date_str in enumerate(date_strs):
                    days_passed = i * adj_date_days
                    
                    if warrant['Type'] == 'MINI Long':
                        adj_strike = warrant['Strike'] + (daily_interest * days_passed)
                        mini_val = max(0, (price - adj_strike) / (multiplier * warrant['FX Rate']))
                    else:
                        adj_strike = warrant['Strike'] - (daily_interest * days_passed)
                        mini_val = max(0, (adj_strike - price) / (multiplier * warrant['FX Rate']))
                    
                    # Calculate P&L
                    if current_mini_price > 0:
                        if calc_type == "P&L %":
                            pnl = ((mini_val / current_mini_price) - 1) * 100
                            row_data[date_str] = f"{pnl:.2f}%"
                        else:
                            pnl = (mini_val - current_mini_price) * mini_qty
                            row_data[date_str] = f"${pnl:.2f}"
                    else:
                        row_data[date_str] = "-"
                        
                matrix_data.append(row_data)

            # Display Matrix
            matrix_df = pd.DataFrame(matrix_data)
            st.dataframe(matrix_df, use_container_width=True, hide_index=True)