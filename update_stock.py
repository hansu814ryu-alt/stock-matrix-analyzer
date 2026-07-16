import FinanceDataReader as fdr
import pandas as pd
import datetime
import os
import json
import time

print("🚀 [시스템 개정] AI 차트 분석(수급선/스윙선) & 퀀트 데이터 추출 스캐너 가동...")

df_krx = fdr.StockListing('KRX')
df_krx = df_krx[~df_krx['Name'].str.endswith(('우', '우B', '우C'))]
df_krx = df_krx[df_krx['Market'] != 'KONEX']

target_codes = df_krx['Code'].tolist()
name_dict = dict(zip(df_krx['Code'], df_krx['Name']))

start_date = (datetime.date.today() - datetime.timedelta(days=5*365)).strftime('%Y-%m-%d')
today_str = datetime.date.today().strftime('%Y-%m-%d')

history_file = "matrix_history.csv"
if os.path.exists(history_file):
    df_history = pd.read_csv(history_file)
    df_history['Code'] = df_history['Code'].astype(str).str.zfill(6)
else:
    df_history = pd.DataFrame(columns=[
        'Date', 'Code', 'Name', 'Cell', 'Base_Price', 
        '1D_Return', '3D_Return', '5D_Return', 'Settled_Count'
    ])

matrix_results = {f"R{i}C{j}": [] for i in range(1, 5) for j in range(1, 5)}
today_captured_list = []
ma_breakthrough_stocks = []
new_high_stocks = []
quant_captured_stocks = []

print(f"📥 [2단계] {len(target_codes)}개 종목 전수조사 및 퀀트 조건 판별 중...")

for code in target_codes:
    try:
        code_str = str(code).zfill(6)
        df = fdr.DataReader(code_str, start=start_date, end=today_str)
        if len(df) < 61: continue 
        
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        df['MA60_Vol'] = df['Volume'].rolling(60).mean()
        
        df['MA20_Vol'] = df['Volume'].rolling(20).mean() 
        df['Std20'] = df['Close'].rolling(20).std()
        df['BB_Upper'] = df['MA20'] + (df['Std20'] * 2) 
        df['High20'] = df['High'].rolling(20).max().shift(1) 
        
        today_data = df.iloc[-1]
        prev_data = df.iloc[-2]
        today_close = today_data['Close']
        prev_close = prev_data['Close']
        today_vol = today_data['Volume']
        today_vol_ma60 = today_data['MA60_Vol']
        
        if prev_close == 0 or today_vol_ma60 == 0 or pd.isna(today_data['BB_Upper']): continue
        
        change_rate = ((today_close - prev_close) / prev_close) * 100
        vol_ratio = (today_vol / today_vol_ma60) * 100
        stock_name = name_dict.get(code_str, code_str)

        # 사용자 지정 퀀트 매수 조건 (Plotly 차트를 위한 OHLCV 데이터 추출 포함)
        day_minus_5_data = df.iloc[-6]
        
        cond1_vol = today_vol >= today_data['MA20_Vol'] * 2 
        cond2_bb = today_data['BB_Upper'] > day_minus_5_data['BB_Upper'] 
        cond3_price = today_close > today_data['High20'] 
        
        if change_rate > 0 and cond1_vol and cond2_bb and cond3_price:
            # AI 차트용 120일치 캔들 및 저항선 데이터 생성
            df_120 = df.iloc[-120:]
            df_240 = df.iloc[-240:] if len(df) >= 240 else df
            vol_line = float(df_240.loc[df_240['Volume'].idxmax(), 'High'])
            swing_line = float(df.iloc[-60:]['High'].max())
            
            quant_captured_stocks.append({
                "code": code_str, "name": stock_name, "change": round(change_rate, 2), "volume_ratio": round((today_vol / today_data['MA20_Vol']) * 100, 1),
                "ohlcv": {
                    "dates": df_120.index.strftime('%Y-%m-%d').tolist(),
                    "open": df_120['Open'].tolist(), "high": df_120['High'].tolist(),
                    "low": df_120['Low'].tolist(), "close": df_120['Close'].tolist(), "volume": df_120['Volume'].tolist(),
                    "vol_line": vol_line, "swing_line": swing_line
                }
            })

        # 기존 52주 신고가 로직 (여기에도 AI 차트를 위해 OHLCV 데이터 탑재)
        if change_rate > 0:
            df_1yr = df.iloc[-252:] if len(df) >= 252 else df
            high_52w = df_1yr['High'].max()
            high_all = df['High'].max()
            
            is_new_high = False
            high_type = ""
            if today_close >= high_all:
                is_new_high = True; high_type = "역사적 신고가"
            elif today_close >= high_52w:
                is_new_high = True; high_type = "52주 신고가"
                
            if is_new_high:
                ohlcv_data = None
                if len(new_high_stocks) < 10: # 용량 관리를 위해 10개만 차트 데이터 첨부
                    df_120 = df.iloc[-120:]
                    df_240 = df.iloc[-240:] if len(df) >= 240 else df
                    vol_line = float(df_240.loc[df_240['Volume'].idxmax(), 'High'])
                    swing_line = float(df.iloc[-60:]['High'].max())
                    ohlcv_data = {
                        "dates": df_120.index.strftime('%Y-%m-%d').tolist(),
                        "open": df_120['Open'].tolist(), "high": df_120['High'].tolist(),
                        "low": df_120['Low'].tolist(), "close": df_120['Close'].tolist(), "volume": df_120['Volume'].tolist(),
                        "vol_line": vol_line, "swing_line": swing_line
                    }
                new_high_stocks.append({ "code": code_str, "name": stock_name, "type": high_type, "ohlcv": ohlcv_data })

        if change_rate <= 0: continue 
        
        break_ma5 = bool(prev_data['Close'] <= prev_data['MA5'] and today_close > today_data['MA5'])
        break_ma20 = bool(prev_data['Close'] <= prev_data['MA20'] and today_close > today_data['MA20'])
        break_ma60 = bool(prev_data['Close'] <= prev_data['MA60'] and today_close > today_data['MA60'])
        if break_ma5 or break_ma20 or break_ma60:
            ma_breakthrough_stocks.append({"code": code_str, "name": stock_name, "ma5": break_ma5, "ma20": break_ma20, "ma60": break_ma60})
            
        row = 1 if change_rate < 3 else 2 if change_rate < 6 else 3 if change_rate < 12 else 4
        col = 1 if vol_ratio < 100 else 2 if vol_ratio < 200 else 3 if vol_ratio < 400 else 4
        cell_id = f"R{row}C{col}"
        
        past_records = df_history[df_history['Code'] == code_str] if not df_history.empty else pd.DataFrame()
        if not past_records.empty:
            first_date = str(past_records['Date'].min())
            first_cell = str(past_records[past_records['Date'] == first_date]['Cell'].values[0])
        else:
            first_date = today_str
            first_cell = cell_id
            
        matrix_results[cell_id].append({
            "code": code_str, "name": stock_name, "change": round(change_rate, 2), "volume": round(vol_ratio, 1),
            "first_date": first
