import FinanceDataReader as fdr
import pandas as pd
import numpy as np
import datetime
import json
import time

print("🚀 [시스템 개정] 구름대(일목균형표) 로직 탑재 & 신규 퀀트 매매 로직 스캐너 가동...")

df_krx = fdr.StockListing('KRX')
df_krx = df_krx[~df_krx['Name'].str.endswith(('우', '우B', '우C'))]
df_krx = df_krx[df_krx['Market'] != 'KONEX']

target_codes = df_krx['Code'].tolist()
name_dict = dict(zip(df_krx['Code'], df_krx['Name']))

start_date = (datetime.date.today() - datetime.timedelta(days=5*365)).strftime('%Y-%m-%d')
today_str = datetime.date.today().strftime('%Y-%m-%d')

quant_captured_stocks = []
ma_breakthrough_stocks = []
new_high_stocks = []

print(f"📥 {len(target_codes)}개 종목 전수조사 및 퀀트 조건 판별 중...")

for code in target_codes:
    try:
        code_str = str(code).zfill(6)
        df = fdr.DataReader(code_str, start=start_date, end=today_str)
        if len(df) < 61: continue 
        
        # 기본 지표 계산
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        
        df['MA20_Vol'] = df['Volume'].rolling(20).mean() 
        df['Std20'] = df['Close'].rolling(20).std()
        df['BB_Upper'] = df['MA20'] + (df['Std20'] * 2) 
        df['High20'] = df['High'].rolling(20).max().shift(1) 
        
        # ☁️ 일목균형표 (구름대) 계산
        df['high9'] = df['High'].rolling(window=9).max()
        df['low9'] = df['Low'].rolling(window=9).min()
        df['tenkan'] = (df['high9'] + df['low9']) / 2
        
        df['high26'] = df['High'].rolling(window=26).max()
        df['low26'] = df['Low'].rolling(window=26).min()
        df['kijun'] = (df['high26'] + df['low26']) / 2
        
        df['senkou_a'] = ((df['tenkan'] + df['kijun']) / 2).shift(26)
        
        df['high52'] = df['High'].rolling(window=52).max()
        df['low52'] = df['Low'].rolling(window=52).min()
        df['senkou_b'] = ((df['high52'] + df['low52']) / 2).shift(26)
        
        today_data = df.iloc[-1]
        prev_data = df.iloc[-2]
        today_close = today_data['Close']
        prev_close = prev_data['Close']
        today_vol = today_data['Volume']
        
        if prev_close == 0 or pd.isna(today_data['BB_Upper']) or today_data['MA20_Vol'] == 0: continue
        
        change_rate = ((today_close - prev_close) / prev_close) * 100
        stock_name = name_dict.get(code_str, code_str)

        # 1. 퀀트 매수 조건
        day_minus_5_data = df.iloc[-6]
        cond1_vol = today_vol >= today_data['MA20_Vol'] * 2 
        cond2_bb = today_data['BB_Upper'] > day_minus_5_data['BB_Upper'] 
        cond3_price = today_close > today_data['High20'] 
        
        if change_rate > 0 and cond1_vol and cond2_bb and cond3_price:
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
                    "senkou_a": [None if pd.isna(x) else round(x, 2) for x in df_120['senkou_a']],
                    "senkou_b": [None if pd.isna(x) else round(x, 2) for x in df_120['senkou_b']],
                    "vol_line": vol_line, "swing_line": swing_line
                }
            })

        # 2. 52주/역사적 신고가
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
                if len(new_high_stocks) < 15:
                    df_120 = df.iloc[-120:]
                    df_240 = df.iloc[-240:] if len(df) >= 240 else df
                    vol_line = float(df_240.loc[df_240['Volume'].idxmax(), 'High'])
                    swing_line = float(df.iloc[-60:]['High'].max())
                    ohlcv_data = {
                        "dates": df_120.index.strftime('%Y-%m-%d').tolist(),
                        "open": df_120['Open'].tolist(), "high": df_120['High'].tolist(),
                        "low": df_120['Low'].tolist(), "close": df_120['Close'].tolist(), "volume": df_120['Volume'].tolist(),
                        "senkou_a": [None if pd.isna(x) else round(x, 2) for x in df_120['senkou_a']],
                        "senkou_b": [None if pd.isna(x) else round(x, 2) for x in df_120['senkou_b']],
                        "vol_line": vol_line, "swing_line": swing_line
                    }
                new_high_stocks.append({ "code": code_str, "name": stock_name, "type": high_type, "ohlcv": ohlcv_data })

        if change_rate <= 0: continue 
        
        # 3. 강력 이평선 돌파
        break_ma5 = bool(prev_data['Close'] <= prev_data['MA5'] and today_close > today_data['MA5'])
        break_ma20 = bool(prev_data['Close'] <= prev_data['MA20'] and today_close > today_data['MA20'])
        break_ma60 = bool(prev_data['Close'] <= prev_data['MA60'] and today_close > today_data['MA60'])
        if break_ma5 or break_ma20 or break_ma60:
            ma_breakthrough_stocks.append({"code": code_str, "name": stock_name, "ma5": break_ma5, "ma20": break_ma20, "ma60": break_ma60})
            
    except Exception as e: pass
    time.sleep(0.01)

print("⚙️ 웹 배포용 고밀도 단일 JSON 패키징 빌드 중...")
final_web_data = {
    "quant_captured": quant_captured_stocks,
    "ma_breakthroughs": ma_breakthrough_stocks,
    "new_highs": new_high_stocks
}

with open('matrix_data.json', 'w', encoding='utf-8') as f:
    json.dump(final_web_data, f, ensure_ascii=False, indent=4)

print("🎉 구름대(일목균형표) 시각화 데이터 배포 완료!")
