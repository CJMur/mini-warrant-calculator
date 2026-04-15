import streamlit as st
import pandas as pd
import yfinance as yf
import numpy as np
import math
from datetime import datetime, timedelta

st.set_page_config(page_title="MINI Warrant Calculator", layout="wide")

# --- VERSION CONTROL ---
VERSION = "1.13.0"

# --- CSS STYLING ---
st.markdown("""
<style>
    /* --- WHITE-LABEL INVISIBILITY CLOAK --- */
    #MainMenu {visibility: hidden;}
    header {visibility: hidden;}
    footer {visibility: hidden;}
    div[class^="viewerBadge_container"] {display: none !important;}
    [data-testid="stDecoration"] {display: none !important;}

    .block-container { padding-top: 2rem !important; padding-bottom: 5rem !important; }
    
    /* Overall Font Size Increases */
    p, span, label, div[data-testid="stMarkdownContainer"] {
        font-size: 16px;
    }
    
    [data-testid="stMetricValue"] {
        font-size: 2.2rem !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 1.1rem !important;
        font-weight: 600;
        color: #94a3b8;
    }

    .header-box {
        padding: 1.5rem; background-color: #0e1b32; border-radius: 10px; color: white;
        margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        border-bottom: 4px solid #1DBFD2;
    }
    .header-title { font-size: 28px; font-weight: 700; margin: 0; }
    .header-sub { font-size: 16px; opacity: 0.8; margin: 0; }
    .status-tag {
        background-color: rgba(255,255,255,0.15); padding: 4px 10px; border-radius: 4px;
        font-size: 14px; font-family: monospace;
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
    div[data-testid="stSlider"] p { color: white !important; }
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
SHEET_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR41nrL5N0HqOryvFqisPgJI68Klmki4XIQV5U9SivNgsBuit34urkUZxfePE-XkbXLtM9DLUhaNgs_/pub?gid=0&single=true&output=csv"
FUNDING_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vR41nrL5N0HqOryvFqisPgJI68Klmki4XIQV5U9SivNgsBuit34urkUZxfePE-XkbXLtM9DLUhaNgs_/pub?gid=773772854&single=true&output=csv"

# --- 1. DATA LOADING ---
@st.cache_data(ttl=600) 
def load_warrant_data():
    funding_error = None
    default_long_rate = 0.087
    default_short_rate = -0.015
    
    try:
        # 1. Fetch Dynamic Funding Rates First
        try:
            funding_df = pd.read_csv(FUNDING_CSV_URL)
            
            # Intelligently find the correct columns regardless of exact naming
            long_col = [c for c in funding_df.columns if 'Long' in str(c) or 'long' in str(c)][0]
            short_col = [c for c in funding_df.columns if 'Short' in str(c) or 'short' in str(c)][0]
            
            # Helper to strip percent signs and properly format decimals
            def parse_rate(raw_val):
                raw_val = str(raw_val).strip()
                if '%' in raw_val:
                    return float(raw_val.replace('%', '')) / 100.0
                val = float(raw_val)
                return val / 100.0 if abs(val) > 0.5 else val
                
            default_long_rate = parse_rate(funding_df[long_col].iloc[0])
            default_short_rate = parse_rate(funding_df[short_col].iloc[0])
            
        except Exception as e:
            funding_error = str(e)

        # 2. Fetch Main Warrant Data
        df = pd.read_csv(SHEET_CSV_URL)
        
        def get_ticker(code):
            if isinstance(code, str) and len(code) >= 3:
                if code.startswith('FX'): return None 
                return code[:3] + '.AX'
            return None
            
        df['Ticker'] = df['Code'].apply(get_ticker)
        
        df['Funding Rate'] = np.where(df['Type'] == 'MINI Long', default_long_rate, default_short_rate)
        df['FX Rate'] = 1.0
        
        df['Type'] = df['Type'].replace({
            'MINI Long': '🟩 MINI Long ▲', 
            'MINI Short': '🟥 MINI Short ▼'
        })
        
        cols_to_clean = ['Strike', 'Stop Loss Trigger Level', 'Multiplier', 'Underlying Spot Price']
        pct_cols_to_clean = ['Effective gearing', 'Effective Gearing', 'Distance to Knock-Out', 'Distance to Stop Loss']
        
        for col in cols_to_clean:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
        for col in pct_cols_to_clean:
            if col in df.columns:
                df[col] = df[col].astype(str).str.replace('%', '', regex=False)
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
                if df[col].dropna().max() <= 10.0:
                    df[col] = df[col] * 100
                    
        return df, funding_error
    except Exception as e:
        st.error(f"⚠️ Could not load data from Google Sheets. Error: {e}")
        return pd.DataFrame(), funding_error

warrants_df, current_funding_error = load_warrant_data()

if current_funding_error:
    st.error(f"⚠️ **Connection Alert:** The app could not read your new Funding Tab link, so it is temporarily using safety fallbacks (8.7% and -1.5%). Update the `FUNDING_CSV_URL` in your code with the correct tab GID. *(Error: {current_funding_error})*")

# --- 2. SEARCH MODULE ---
if not warrants_df.empty:
    
    st.markdown(f"""
    <div class="header-box">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <div class="header-title">MINI Warrant Search</div>
                <div class="header-sub">Click a row below to select a warrant and load the calculator</div>
            </div>
            <div style="text-align: right;">
                <span class="status-tag">v{VERSION}</span>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Updated Placeholder Text to indicate Commodities
    search_query = st.text_input("Search by Code or Underlying (e.g., BHP, Gold, Silver):")
    
    if search_query:
        # THE FIX: Added case=False and na=False to completely ignore capitalization
        filtered_df = warrants_df[
            warrants_df['Code'].astype(str).str.contains(search_query, case=False, na=False) | 
            warrants_df['Underlying'].astype(str).str.contains(search_query, case=False, na=False)
        ]
    else:
        filtered_df = warrants_df

    display_cols = ['Code', 'Underlying', 'Type', 'Strike', 'Stop Loss Trigger Level', 'Multiplier']
    
    gearing_col = 'Effective gearing' if 'Effective gearing' in filtered_df.columns else 'Effective Gearing'
    if gearing_col in filtered_df.columns: display_cols.append(gearing_col)
    
    ko_col = 'Distance to Knock-Out'
    if ko_col in filtered_df.columns: display_cols.append(ko_col)
        
    sl_dist_col = 'Distance to Stop Loss'
    if sl_dist_col in filtered_df.columns: display_cols.append(sl_dist_col)
    
    display_cols.extend(['Bid', 'Ask'])
    display_cols = [c for c in display_cols if c in filtered_df.columns]

    selection_event = st.dataframe(
        filtered_df[display_cols], 
        hide_index=True, 
        use_container_width=True,
        on_select="rerun",
        selection_mode="single-row",
        column_config={
            "Stop Loss Trigger Level": st.column_config.NumberColumn("Stop Loss", format="$%.2f", help="The price level where the warrant is 'stopped out' to prevent further losses."),
            "Strike": st.column_config.NumberColumn("Strike", format="$%.4f", help="The financing level used to calculate the intrinsic value of the warrant."),
            gearing_col: st.column_config.NumberColumn("Effective Gearing", format="%.2f%%", help="The degree of leverage the warrant provides compared to the underlying share."),
            ko_col: st.column_config.NumberColumn("Dist. to Knock-Out", format="%.2f%%", help="The percentage distance between the current spot price and the Strike (financing level)."),
            sl_dist_col: st.column_config.NumberColumn("Distance to Stop", format="%.2f%%", help="The percentage distance between the current spot price and the Stop Loss trigger level."),
            "Bid": st.column_config.NumberColumn("Bid", format="$%.3f", help="The current highest price a buyer is willing to pay."),
            "Ask": st.column_config.NumberColumn("Ask", format="$%.3f", help="The current lowest price a seller is willing to accept.")
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

        if 'Long' in warrant['Type']:
            current_mini_price = max(0.0, (live_price - strike) / (multiplier * fx_rate))
        else:
            current_mini_price = max(0.0, (strike - live_price) / (multiplier * fx_rate))

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
                    <div class="header-sub">Current Underlying Spot</div>
                    <span class="status-tag">{warrant['Code']}</span>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
            
        i_col1, i_col2, i_col3, i_col4, i_col5 = st.columns(5)
        i_col1.metric("Selected Code", warrant['Code'], help="The ASX code of the warrant currently being analyzed.")
        i_col2.metric("Multiplier", int(multiplier), help="The number of warrants required to equal one underlying share.")
        i_col3.metric("Strike", f"${strike:.4f}", help="The current financing level (strike price) of the warrant.")
        i_col4.metric("Stop Loss", f"${stop_loss:.2f}", help="The price point at which the warrant is knocked out.")
        i_col5.metric("Current Fair Value", f"${current_mini_price:.2f}", help="The theoretical current price of the warrant based on the underlying spot price.")
        
        st.divider()

        st.markdown("### Scenario Inputs")
        in_col1, in_col2, in_col3, in_col4 = st.columns(4)
        
        with in_col1:
            base_share_price = st.number_input("Base Share Price", value=float(round(live_price, 2)), step=0.10, help="The starting share price for the middle 'SPOT' row of the payoff matrix.")
            mini_qty = st.number_input("Mini QTY", value=200, step=100, help="The total quantity of MINI warrants purchased.")
        with in_col2:
            adj_share_pct = st.number_input("ADJ Share %", value=2.0, step=1.0, help="The percentage step-size for the share price rows moving up and down the matrix.")
            adj_date_days = st.number_input("ADJ Date (Days)", value=1, step=1, help="The number of days between each column in the matrix.")
        with in_col3:
            calc_type = st.radio("Display Output As:", ["P&L %", "P&L $"], help="Toggle whether the matrix displays profit/loss as a percentage or in absolute dollars.")
        with in_col4:
            funding_rate = st.number_input("Funding Rate (%)", value=float(warrant['Funding Rate']*100), step=0.1, disabled=True, help="The annualized interest rate used to calculate daily financing costs (Auto-updates via Google Sheets).") / 100
            st.info(f"**Max Risk:** ${(current_mini_price * mini_qty):.2f}")

        st.markdown("### Payoff Matrix")
        
        steps = [10, 8, 6, 4, 2, 0, -2, -4, -6, -8, -10]
        row_prices = [base_share_price * (1 + (step * (adj_share_pct / 100) / 2)) for step in steps]
        
        dates = [datetime.today() + timedelta(days=i * adj_date_days) for i in range(7)]
        date_strs = [d.strftime('%m/%d/%Y') for d in dates]
        
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
                    mini_val = max(0.0, (price - adj_strike) / (multiplier * fx_rate))
                else:
                    mini_val = max(0.0, (adj_strike - price) / (multiplier * fx_rate))
                
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

        st.dataframe(df_mx.style.apply(make_heatmap, axis=None).format(format_pnl), use_container_width=True, height=450)
