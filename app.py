import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

st.set_page_config(page_title="MINI Warrant Calculator", layout="wide")

# ==========================================
# Your live Google Sheet 
# ==========================================
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vREoxpGZIfWZGWyRF_I_N7KKJOC9OmGNgsPh7F0gRE4RN4RgBUUzhzk1h-ro6vSrlIg5rJRwXS5DXGr/pub?gid=0&single=true&output=csv"

# --- 1. DATA LOADING (Live from Google Sheets) ---
@st.cache_data(ttl=600) 
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
        df['Funding Rate'] = np.where(df['Type'] == 'MINI Long', 0.087, 0.001)
        df['FX Rate'] = 1.0
        
        # --- THE FIX: Clean up nasty strings in number columns ---
        cols_to_clean = ['Strike', 'Stop Loss Trigger Level', 'Multiplier', 'Underlying Spot Price']
        for col in cols_to_clean:
            if col in df.columns:
                # This forces any text (like "-") into NaN (Not a Number)
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
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
        search_query = st.text_input("Search by Ticker or Underlying (e.g., A2M, BHP):").upper()
        
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
        
        # --- THE FIX: Safely extract variables as Floats ---
        # Use 0.0 as a fallback if the sheet value is blank/NaN
        sheet_price = warrant.get('Underlying Spot Price')
        live_price = float(sheet_price) if pd.notna(sheet_price) else 0.0
        
        if pd.notna(warrant['Ticker']):
            try:
                yf_data = yf.Ticker(warrant['Ticker']).history(period="1d")
                if not yf_data.empty:
                    live_price = float(yf_data['Close'].iloc[-1])
            except:
                pass 

        strike = float(warrant['Strike']) if pd.notna(warrant['Strike']) else 0.0
        multiplier = float(warrant.get('Multiplier', 1.0)) if pd.notna(warrant.get('Multiplier')) else 1.0
        fx_rate = float(warrant.get('FX Rate', 1.0))
        stop_loss = float(warrant.get('Stop Loss Trigger Level', 0.0)) if pd.notna(warrant.get('Stop Loss Trigger Level')) else 0.0

        # Calculate Current Mini Fair Value
        if warrant['Type'] == 'MINI Long':
            current_mini_price = max(0.0, (live_price - strike) / (multiplier * fx_rate))
        else:
            current_mini_price = max(0.0, (strike - live_price) / (multiplier * fx_rate))

        with col2:
            st.subheader(f"2. Calculator: {warrant['Code']}")
            
            i_col1, i_col2, i_col3, i_col4, i_col5 = st.columns(5)
            i_col1.metric("Underlying", warrant['Underlying'])
            i_col2.metric("Type", warrant['Type'])
            i_col3.metric("Strike", f"${strike:.4f}")
            i_col4.metric("Stop Loss", f"${stop_loss:.2f}")
            i_col5.metric("Current Fair Value", f"${current_mini_price:.2f}")
            
            st.divider()

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

            st.markdown("### Pricing Matrix")
            
            steps = [10, 8, 6, 4, 2, 0, -2, -4, -6, -8, -10]
            row_prices = [base_share_price * (1 + (step * (adj_share_pct / 100) / 2)) for step in steps]
            
            dates = [datetime.today() + timedelta(days=i * adj_date_days) for i in range(7)]
            date_strs = [d.strftime('%m/%d/%Y') for d in dates]
            
            daily_interest = (strike * funding_rate) / 365
            
            matrix_data = []
            for price in row_prices:
                row_data = {"Share Price": f"${price:.2f}"}
                for i, date_str in enumerate(date_strs):
                    days_passed = i * adj_date_days
                    
                    if warrant['Type'] == 'MINI Long':
                        adj_strike = strike + (daily_interest * days_passed)
                        mini_val = max(0.0, (price - adj_strike) / (multiplier * fx_rate))
                    else:
                        adj_strike = strike - (daily_interest * days_passed)
                        mini_val = max(0.0, (adj_strike - price) / (multiplier * fx_rate))
                    
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

            matrix_df = pd.DataFrame(matrix_data)
            st.dataframe(matrix_df, use_container_width=True, hide_index=True)
