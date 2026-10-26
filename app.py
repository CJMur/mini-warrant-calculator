import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import math
from datetime import datetime, timedelta

st.set_page_config(page_title="MINI Warrant Calculator", layout="wide")

# --- VERSION CONTROL ---
VERSION = "1.34.0"

# --- CSS STYLING ---
st.markdown("""
<style>
    .block-container { padding-top: 2rem !important; padding-bottom: 5rem !important; }
    
    .header-box {
        padding: 1.5rem; background-color: #0e1b32; border-radius: 10px; color: white;
        margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-bottom: 4px solid #1DBFD2;
    }
    .header-title { font-size: 24px; font-weight: 700; margin: 0; color: white;}
    .header-sub { font-size: 14px; opacity: 0.8; margin: 0; color: white;}
    
    .mock-button {
        background-color: #1e293b; 
        color: #f8fafc; 
        padding: 6px 14px; 
        border-radius: 6px; 
        font-size: 14px; 
        font-weight: 600; 
        border: 1px solid #334155;
        display: inline-block;
    }
    
    div[data-testid="stButton"] button[kind="primary"] {
        background-color: #1DBFD2 !important; border: none; color: white !important; font-weight: bold;
    }
    div[data-testid="stButton"] button[kind="primary"]:hover {
        background-color: #16aebf !important;
    }
    div[data-testid="stButton"] button[kind="secondary"] {
        background-color: #f8fafc !important; color: #334155 !important; border: 1px solid #cbd5e1; font-weight: bold;
    }
    
    /* --- SLIDER COLOR FIX (Electric Blue) --- */
    div[data-baseweb="slider"] > div > div > div { background-color: #0050FF !important; }
    div[role="slider"] { background-color: #0050FF !important; border: none !important; box-shadow: none !important; }
    div[data-testid="stSlider"] svg path { fill: #0050FF !important; stroke: #0050FF !important; }
    div[data-testid="stSlider"] p { color: var(--text-color) !important; }
    input[type=range] { accent-color: #0050FF !important; }
    
    /* Dataframe Row Selection Highlight (Teal) */
    [data-testid="stDataFrame"] [aria-selected="true"] > div {
        background-color: rgba(29, 191, 210, 0.4) !important; color: white !important;
    }
    
    .stDataFrame { border: none !important; }
    
    /* Horizontal Radio Button Styling */
    div.row-widget.stRadio > div { flex-direction: row; align-items: center; }
</style>
""", unsafe_allow_html=True)

# ==========================================
# Google Sheets Live Data Links
# ==========================================
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/1ui3weG176qBJt9gVX1NFpiH2h0y9AyWWQU-3WnuTfD8/export?format=csv&gid=0"
FUNDING_CSV_URL = "https://docs.google.com/spreadsheets/d/1ui3weG176qBJt9gVX1NFpiH2h0y9AyWWQU-3WnuTfD8/export?format=csv&gid=773772854"

# --- 1. DATA LOADING ---
@st.cache_data(ttl=600) 
def load_warrant_data():
    funding_error = None
    data_warnings = []
    default_long_rate = 0.087
    default_short_rate = -0.015

    try:
        try:
            funding_df = pd.read_csv(FUNDING_CSV_URL)
            long_col = [c for c in funding_df.columns if 'Long' in str(c) or 'long' in str(c)][0]
            short_col = [c for c in funding_df.columns if 'Short' in str(c) or 'short' in str(c)][0]

            def parse_rate(raw_val):
                # "8.70%" -> 0.087. Plain numbers: anything under 0.25 is read as a decimal
                # (0.087 = 8.7%), anything larger as a percentage number (8.7 = 8.7%, 0.4 = 0.4%).
                raw_val = str(raw_val).strip().replace(',', '')
                if '%' in raw_val: return float(raw_val.replace('%', '')) / 100.0
                val = float(raw_val)
                return val if abs(val) < 0.25 else val / 100.0

            default_long_rate = parse_rate(funding_df[long_col].iloc[0])
            default_short_rate = parse_rate(funding_df[short_col].iloc[0])

            for label, rate in [("Long", default_long_rate), ("Short", default_short_rate)]:
                if not -0.20 <= rate <= 0.30:
                    data_warnings.append(f"The {label} funding rate read from the Funding tab is {rate*100:.2f}%, which looks wrong. Check the value in the sheet.")
        except Exception as e:
            funding_error = str(e)

        df = pd.read_csv(SHEET_CSV_URL)
        
        def get_ticker(code):
            if not isinstance(code, str) or len(code) < 3:
                return None
            if code.startswith('FX'): 
                return None 
                
            prefix = code[:3].upper()
            
            special_tickers = {
                'XJO': '^AXJO',   
                'SPF': '^GSPC',   
                'NDX': '^NDX',    
                'DJX': '^DJI',    
                'RTY': '^RUT',    
                'NI2': '^N225',   
                'ZGC': 'GC=F',    
                'ZSI': 'SI=F',    
                'ZCL': 'CL=F',    
                'ZHG': 'HG=F'     
            }
            
            if prefix in special_tickers:
                return special_tickers[prefix]
                
            return prefix + '.AX'
            
        df['Ticker'] = df['Code'].apply(get_ticker)
        df['Funding Rate'] = np.where(df['Type'] == 'MINI Long', default_long_rate, default_short_rate)
        
        # --- NEW: COMPREHENSIVE LIVE FX RATE CONVERSION ---
        # Fetching precise "To-AUD" multipliers
        fx_tickers = ['USDAUD=X', 'JPYAUD=X', 'EURAUD=X', 'GBPAUD=X', 'NZDAUD=X']
        # NaN = not fetched. Rows using a missing rate get blank Bid/Ask instead of a silent 1.0.
        fx_rates = {t: np.nan for t in fx_tickers}

        try:
            # 5 days so a weekend or holiday still gives the latest close
            fx_data = yf.download(fx_tickers, period="5d", progress=False)
            if 'Close' in fx_data:
                for ticker in fx_tickers:
                    try:
                        series = fx_data['Close'] if len(fx_tickers) == 1 else fx_data['Close'][ticker]
                        series = series.dropna()
                        if not series.empty:
                            fx_rates[ticker] = float(series.iloc[-1])
                    except Exception:
                        pass
        except Exception:
            pass

        df['FX Rate'] = 1.0
        
        # 1. USD Underlyings
        usd_assets = [
            'Copper Future', 'Crude Oil Future', 'Dow Jones Future', 
            'Gold Future', 'Nasdaq Future', 'S&P 500 Future', 
            'Silver Future', 'Russell 2000 Future', 'AUD-USD FX Currency Pair'
        ]
        df.loc[df['Underlying'].isin(usd_assets), 'FX Rate'] = fx_rates['USDAUD=X']
        
        # 2. JPY Underlyings
        df.loc[df['Underlying'].isin(['Nikkei Future', 'AUD-JPY FX Currency Pair']), 'FX Rate'] = fx_rates['JPYAUD=X']
        
        # 3. EUR, GBP, NZD Underlyings
        df.loc[df['Underlying'] == 'AUD-EUR FX Currency Pair', 'FX Rate'] = fx_rates['EURAUD=X']
        df.loc[df['Underlying'] == 'AUD-GBP FX Currency Pair', 'FX Rate'] = fx_rates['GBPAUD=X']
        df.loc[df['Underlying'] == 'AUD-NZD FX Currency Pair', 'FX Rate'] = fx_rates['NZDAUD=X']

        failed_fx = [t.replace('=X', '') for t in fx_tickers if pd.isna(fx_rates[t])]
        fx_missing = df['FX Rate'].isna()
        if fx_missing.any():
            affected = sorted(df.loc[fx_missing, 'Underlying'].dropna().astype(str).unique().tolist())
            data_warnings.append(f"Live FX rates could not be loaded for {', '.join(failed_fx)}. Bid/Ask are blank for: {', '.join(affected)}.")

        df['Type'] = df['Type'].replace({
            'MINI Long': '🟩 MINI Long ▲', 
            'MINI Short': '🟥 MINI Short ▼'
        })
        
        cols_to_clean = ['Strike', 'Stop Loss Trigger Level', 'Multiplier', 'Underlying Spot Price']
        pct_cols_to_clean = ['Effective gearing', 'Effective Gearing', 'Distance to Knock-Out', 'Distance to Stop Loss']
        
        for col in cols_to_clean:
            if col in df.columns: 
                df[col] = df[col].astype(str).str.replace(',', '', regex=False).str.replace('$', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        for col in pct_cols_to_clean:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace('%', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')
                if df[col].dropna().max() <= 10.0: df[col] = df[col] * 100

        # --- GLOBAL BULK LIVE PRICING FETCH ---
        df['Price Source'] = 'Sheet'
        unique_tickers = [t for t in df['Ticker'].dropna().unique().tolist() if t]
        if unique_tickers:
            try:
                live_data = yf.download(unique_tickers, period="5d", progress=False)
                if 'Close' in live_data:
                    close_data = live_data['Close']
                    for ticker in unique_tickers:
                        try:
                            series = close_data if len(unique_tickers) == 1 else close_data[ticker]
                            series = series.dropna()

                            if not series.empty:
                                df.loc[df['Ticker'] == ticker, 'Underlying Spot Price'] = float(series.iloc[-1])
                                df.loc[df['Ticker'] == ticker, 'Price Source'] = 'Live'
                        except Exception:
                            pass
            except Exception:
                pass

        # FX pair codes have no Yahoo ticker, so the sheet price is expected for them
        stale_rows = (df['Price Source'] == 'Sheet') & df['Ticker'].notna()
        if stale_rows.any():
            data_warnings.append(f"Live prices could not be loaded for {int(stale_rows.sum())} warrant(s), so they use the Google Sheet price. These show 'Sheet' in the Price column.")

        # --- GLOBAL DYNAMIC BID/ASK MATH ---
        spot = pd.to_numeric(df['Underlying Spot Price'], errors='coerce')
        strike = pd.to_numeric(df['Strike'], errors='coerce')
        # A blank or 0 multiplier is treated as missing (not 1), so Bid/Ask stay blank instead of mispriced
        mult = pd.to_numeric(df['Multiplier'], errors='coerce')
        mult = mult.where(mult != 0)
        df['Multiplier'] = mult

        bad_mult = mult.isna()
        if bad_mult.any():
            codes = df.loc[bad_mult, 'Code'].astype(str).tolist()
            shown = ', '.join(codes[:10]) + (f" and {len(codes) - 10} more" if len(codes) > 10 else "")
            data_warnings.append(f"The Multiplier is blank or 0 in the Google Sheet for: {shown}. These have no Bid/Ask and can't be opened in the calculator.")

        fx = pd.to_numeric(df['FX Rate'], errors='coerce')

        is_long = df['Type'].str.contains('Long', case=False, na=False)
        midpoints = np.where(is_long, (spot - strike) * mult, (strike - spot) * mult)
        midpoints = np.maximum(0.0, midpoints)  # NaN inputs stay NaN

        # Apply the FX conversion (Multiplying to convert to AUD)
        midpoints = midpoints * fx

        df['Bid'] = np.maximum(0.0, midpoints - 0.01)
        df['Ask'] = midpoints + 0.01

        return df, funding_error, data_warnings
    except Exception as e:
        st.error(f"⚠️ Could not load data from Google Sheets. Error: {e}")
        return pd.DataFrame(), funding_error, data_warnings

warrants_df, current_funding_error, current_data_warnings = load_warrant_data()

if current_funding_error:
    st.error(f"⚠️ **Connection Alert:** The app could not read your new Funding Tab link, so it is temporarily using safety fallbacks (8.7% and -1.5%). Update the `FUNDING_CSV_URL` in your code with the correct tab GID. *(Error: {current_funding_error})*")

for warning_msg in current_data_warnings:
    st.warning(f"⚠️ {warning_msg}")

# --- 2. SEARCH MODULE ---
if not warrants_df.empty:
    
    st.markdown(f"""
    <div class="header-box">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div class="header-title">MINI Warrant Search</div>
                <div class="header-sub">Click a row below to select a warrant</div>
            </div>
            <div style="text-align: right;">
                <span class="mock-button">Search & Analyze v{VERSION}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    search_col1, search_col2 = st.columns(2)
    
    with search_col1:
        unique_underlyings = sorted(warrants_df['Underlying'].dropna().astype(str).unique().tolist())
        dropdown_options = ["-- View All --"] + unique_underlyings
        selected_underlying = st.selectbox("Select or Search Underlying Asset:", options=dropdown_options)
        
    with search_col2:
        search_code = st.text_input("Or Search by Specific Code (e.g., BHPKCA, XAU):")
    
    filtered_df = warrants_df.copy()
    
    if selected_underlying != "-- View All --":
        filtered_df = filtered_df[filtered_df['Underlying'].astype(str) == selected_underlying]
        
    if search_code:
        filtered_df = filtered_df[filtered_df['Code'].astype(str).str.contains(search_code, case=False, na=False)]

    display_cols = ['Code', 'Underlying', 'Type', 'Strike', 'Stop Loss Trigger Level', 'Multiplier']
    
    gearing_col = 'Effective gearing' if 'Effective gearing' in filtered_df.columns else 'Effective Gearing'
    if gearing_col in filtered_df.columns: display_cols.append(gearing_col)
    
    ko_col = 'Distance to Knock-Out'
    if ko_col in filtered_df.columns: display_cols.append(ko_col)
        
    sl_dist_col = 'Distance to Stop Loss'
    if sl_dist_col in filtered_df.columns: display_cols.append(sl_dist_col)
    
    display_cols.extend(['Bid', 'Ask', 'Price Source'])
    display_cols = [c for c in display_cols if c in filtered_df.columns]

    selection_event = st.dataframe(
        filtered_df[display_cols], 
        hide_index=True, 
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Stop Loss Trigger Level": st.column_config.NumberColumn("Stop Loss", format="$%.2f"),
            "Strike": st.column_config.NumberColumn("Strike", format="$%.4f"),
            gearing_col: st.column_config.NumberColumn("Effective Gearing", format="%.2f%%"),
            ko_col: st.column_config.NumberColumn("Dist. to Knock-Out", format="%.2f%%"),
            sl_dist_col: st.column_config.NumberColumn("Distance to Stop", format="%.2f%%"),
            "Bid": st.column_config.NumberColumn("Bid", format="$%.3f"),
            "Ask": st.column_config.NumberColumn("Ask", format="$%.3f"),
            "Price Source": st.column_config.TextColumn("Price", help="Live = Yahoo Finance. Sheet = Google Sheet price (live price unavailable).")
        }
    )

    selected_rows = selection_event.selection.rows

    # --- 3. CALCULATOR MODULE ---
    if selected_rows:
        selected_index = selected_rows[0]
        selected_warrant_code = filtered_df.iloc[selected_index]['Code']
        warrant = warrants_df[warrants_df['Code'] == selected_warrant_code].iloc[0]
        
        sheet_price = warrant.get('Underlying Spot Price')
        live_price = float(sheet_price) if pd.notna(sheet_price) else 0.0

        if pd.isna(warrant.get('Multiplier')):
            st.error(f"⚠️ {warrant['Code']} has no Multiplier in the Google Sheet, so it can't be priced. Fix the sheet and refresh.")
            st.stop()
        if pd.isna(warrant.get('FX Rate')):
            st.error(f"⚠️ The live FX rate for {warrant['Underlying']} couldn't be loaded, so {warrant['Code']} can't be priced in AUD. Try again in a few minutes.")
            st.stop()

        strike = float(warrant['Strike']) if pd.notna(warrant['Strike']) else 0.0
        multiplier = float(warrant['Multiplier'])
        fx_rate = float(warrant['FX Rate'])
        stop_loss = float(warrant.get('Stop Loss Trigger Level', 0.0)) if pd.notna(warrant.get('Stop Loss Trigger Level')) else 0.0

        if 'current_warrant_code' not in st.session_state or st.session_state.current_warrant_code != warrant['Code']:
            st.session_state.current_warrant_code = warrant['Code']
            st.session_state.base_price_input = float(round(live_price, 2))
            
            if 'Long' in warrant['Type']:
                init_price = max(0.0, (st.session_state.base_price_input - strike) * multiplier * fx_rate)
            else:
                init_price = max(0.0, (strike - st.session_state.base_price_input) * multiplier * fx_rate)
                
            st.session_state.qty_input = 200
            st.session_state.risk_input = float(200 * init_price)
            
        dynamic_base_price = st.session_state.base_price_input
        
        if 'Long' in warrant['Type']:
            current_mini_price = max(0.0, (dynamic_base_price - strike) * multiplier * fx_rate)
        else:
            current_mini_price = max(0.0, (strike - dynamic_base_price) * multiplier * fx_rate)

        def update_risk_cb(price):
            st.session_state.risk_input = float(st.session_state.qty_input * price)

        def update_qty_cb(price):
            if price > 0:
                st.session_state.qty_input = int(math.floor(st.session_state.risk_input / price))
                st.session_state.risk_input = float(st.session_state.qty_input * price)
            else:
                st.session_state.qty_input = 0
                st.session_state.risk_input = 0.0

        expected_risk = float(st.session_state.qty_input * current_mini_price)
        if not math.isclose(st.session_state.risk_input, expected_risk, rel_tol=1e-5):
            st.session_state.risk_input = expected_risk

        st.markdown("<br><br>", unsafe_allow_html=True)
        
        st.markdown(f"""
        <div class="header-box">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <div class="header-title">MINI Warrant Calculator</div>
                    <div class="header-sub">{warrant['Underlying']} ({warrant['Type']})</div>
                </div>
                <div style="text-align: right;">
                    <div class="header-title" style="color: #4ade80;">${live_price:.2f}</div>
                    <div class="header-sub">Current Underlying Spot ({'Live' if warrant.get('Price Source') == 'Live' else 'Google Sheet price'})</div>
                    <span class="mock-button" style="margin-top: 5px;">{warrant['Code']}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
            
        i_col1, i_col2, i_col3, i_col4, i_col5 = st.columns(5)
        i_col1.metric("Selected Code", warrant['Code'])
        i_col2.metric("Multiplier", f"{multiplier:g}")
        i_col3.metric("Strike", f"${strike:.4f}")
        i_col4.metric("Stop Loss", f"${stop_loss:.2f}")
        i_col5.metric("Current Fair Value", f"${current_mini_price:.2f}", help="The theoretical current price of the warrant based on your chosen Base Share Price.")
        
        st.divider()

        st.markdown("### Scenario Inputs")
        in_col1, in_col2, in_col3, in_col4 = st.columns(4)
        
        with in_col1:
            base_share_price = st.number_input("Base Share Price", step=0.10, key="base_price_input")
            mini_qty = st.number_input("Mini QTY", step=100, key="qty_input", on_change=update_risk_cb, args=(current_mini_price,))
        with in_col2:
            adj_share_pct = st.number_input("ADJ Share %", value=2.0, step=1.0)
            adj_date_days = st.number_input("ADJ Date (Days)", value=1, step=1)
        with in_col3:
            calc_type = st.radio("Display Output As:", ["P&L %", "P&L $"])
        with in_col4:
            funding_rate = st.number_input("Funding Rate (%)", value=float(warrant['Funding Rate']*100), step=0.1, disabled=True) / 100
            max_risk = st.number_input("Max Risk ($)", step=100.0, key="risk_input", on_change=update_qty_cb, args=(current_mini_price,))

        st.markdown("### Payoff Matrix")
        
        steps = [10, 8, 6, 4, 2, 0, -2, -4, -6, -8, -10]
        row_prices = [base_share_price * (1 + (step * (adj_share_pct / 100) / 2)) for step in steps]
        
        dates = [datetime.today() + timedelta(days=i * adj_date_days) for i in range(7)]
        date_strs = [d.strftime('%d/%m/%Y') for d in dates]
        
        daily_interest = (strike * funding_rate) / 365
        
        matrix_data = []
        for price in row_prices:
            is_spot = math.isclose(price, base_share_price, rel_tol=1e-5)
            row_label = f"» ${price:.2f} (SPOT) «" if is_spot else f"${price:.2f}"
            
            row_data = {"Share Price": row_label}
            for i, date_str in enumerate(date_strs):
                days_passed = i * adj_date_days
                
                adj_strike = strike + (daily_interest * days_passed)
                
                if 'Long' in warrant['Type']:
                    mini_val = max(0.0, (price - adj_strike) * multiplier * fx_rate)
                else:
                    mini_val = max(0.0, (adj_strike - price) * multiplier * fx_rate)
                
                if current_mini_price > 0:
                    if calc_type == "P&L %":
                        pnl = ((mini_val / current_mini_price) - 1) * 100
                    else:
                        pnl = (mini_val - current_mini_price) * mini_qty
                    row_data[date_str] = pnl 
                else:
                    row_data[date_str] = np.nan 
                    
            matrix_data.append(row_data)

        df_mx = pd.DataFrame(matrix_data).set_index("Share Price")
        
        def format_pnl(val):
            if pd.isna(val): return "-"
            if calc_type == "P&L %": return f"{val:.2f}%"
            return f"${val:.2f}"

        def make_heatmap(df):
            max_val = df.max().max()
            min_val = df.min().min()
            abs_max = max(abs(max_val), abs(min_val), 1)
            
            styles_df = pd.DataFrame('', index=df.index, columns=df.columns)
            for idx in df.index:
                is_spot = "SPOT" in str(idx)
                for col in df.columns:
                    val = df.loc[idx, col]
                    s = ""
                    if pd.notna(val):
                        if val > 0:
                            intensity = min(val / abs_max, 1.0)
                            alpha = 0.05 + 0.35 * intensity
                            s = f"background-color: rgba(74, 222, 128, {alpha:.2f});"
                        elif val < 0:
                            intensity = min(abs(val) / abs_max, 1.0)
                            alpha = 0.05 + 0.35 * intensity
                            s = f"background-color: rgba(248, 113, 113, {alpha:.2f});"
                    
                    if is_spot:
                        s += "font-weight: bold;"
                        
                    styles_df.loc[idx, col] = s
            return styles_df

        st.dataframe(df_mx.style.apply(make_heatmap, axis=None).format(format_pnl), width="stretch", height=450)
