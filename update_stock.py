from pykrx import stock
import pandas as pd
import datetime
import os
import json
import time

print("🚀 [1단계] KRX 공식 API 기반 시가총액/거래량 스코어링 가동...")

# 1. 날짜 설정 (주말/휴일 방어 로직)
today = datetime.date.today()
today_str = today.strftime('%Y%m%d')

# [에러 해결!] pykrx 자체 버그를 피하기 위해 삼성전자(005930) 차트를 활용하여 최근 영업일 추출
start_date_for_bday = (today - datetime.timedelta(days=10)).strftime('%Y%m%d')
samsung_df = stock.get_market_ohlcv(start_date_for_bday, today_str, "005930")
closest_bdate = samsung_df.index[-1].strftime("%Y%m%d")

print(f"📅 최근 기준 영업일 확인 완료: {closest_bdate}")

# 2. 전 종목 데이터 및 시가총액 일괄 조회
df_ohlcv = stock.get_market_ohlcv(closest_bdate, market="ALL")
df_cap = stock.get_market_cap(closest_bdate, market="ALL")

# 데이터 병합 (인덱스는 종목코드)
df_krx = pd.concat([df_ohlcv, df_cap[['시가총액']]], axis=1)

# [중복 및 노이즈 제거] 종목코드 맨 끝자리가 '0'인 종목(보통주)만 추출하여 우선주 원천 차단
common_tickers = [ticker for ticker in df_krx.index if str(ticker).endswith('0')]
df_krx = df_krx.loc[common_tickers]

# 3. 각각 순위 매기기 및 50% 가중치 합산
df_krx['시총순위'] = df_krx['시가총액'].rank(ascending=False)
df_krx['거래량순위'] = df_krx['거래량'].rank(ascending=False)
df_krx['종합점수'] = (df_krx['시총순위'] * 0.5) + (df_krx['거래량순위'] * 0.5)

# 최정예 500개 종목 선별
final_500 = df_krx.sort_values(by='종합점수').head(500)
target_codes = final_500.index.tolist()

# 500개 종목의 '종목명'만 따로 조회하여 매핑 (API 부하 최소화)
final_500['Name'] = [stock.get_market_ticker_name(code) for code in target_codes]

print(f"🔥 최정예 주도주 {len(target_codes)}개 종목 선별 완료.")
print("📥 [2단계] 데이터 다이어트 및 증분 업데이트 시작 (API 쿨타임 적용)...")

# 4. 500개 종목 데이터 수집 및 업데이트
for code in target_codes:
    file_name = f"data_{code}.csv"
    
    if os.path.exists(file_name):
        df_existing = pd.read_csv(file_name, index_col=0)
        df_existing.index = pd.to_datetime(df_existing.index).strftime('%Y-%m-%d')
        
        # 오늘 하루치 데이터 호출
        df_today = stock.get_market_ohlcv(closest_bdate, closest_bdate, code)
        
        if not df_today.empty:
            # KRX 한글 컬럼을 영문으로 매핑 (기존 장부와 호환)
            df_today = df_today[['시가', '고가', '저가', '종가', '거래량']]
            df_today.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            df_today.index = pd.to_datetime(df_today.index).strftime('%Y-%m-%d')
            
            target_date_formatted = pd.to_datetime(closest_bdate).strftime('%Y-%m-%d')
            
            if target_date_formatted not in df_existing.index:
                df_updated = pd.concat([df_existing, df_today])
                df_updated.to_csv(file_name)
    else:
        # 최초 수집 시 과거 5년 치 호출
        start_date = (today - datetime.timedelta(days=5*365)).strftime('%Y%m%d')
        df_historical = stock.get_market_ohlcv(start_date, closest_bdate, code)
        
        if not df_historical.empty:
            df_historical = df_historical[['시가', '고가', '저가', '종가', '거래량']]
            df_historical.columns = ['Open', 'High', 'Low', 'Close', 'Volume']
            df_historical.index = pd.to_datetime(df_historical.index).strftime('%Y-%m-%d')
            df_historical.to_csv(file_name)
    
    # ⚠️ 매우 중요: KRX 서버 차단을 막기 위한 휴식 시간 
    time.sleep(0.3)

print("📊 [3단계] 오늘 자 4×4 매트릭스 계산기 가동 (증권사 HTS 기준)...")
matrix_results = {f"R{i}C{j}": [] for i in range(1, 5) for j in range(1, 5)}
today_captured_list = []
target_date_formatted = pd.to_datetime(closest_bdate).strftime('%Y-%m-%d')

for code in target_codes:
    file_name = f"data_{code}.csv"
    if not os.path.exists(file_name): continue
    
    df = pd.read_csv(file_name)
    if len(df) < 21: continue
    
    today_data = df.iloc[-1]
    prev_20_days = df.iloc[-21:-1]
    
    # 1. 캔들 필터: 양봉 조건
    if today_data['Close'] <= today_data['Open']: 
        continue
    
    # 2. 증권사 기준 상승률 산출
    prev_close = prev_20_days.iloc[-1]['Close']
    change_rate = ((today_data['Close'] - prev_close) / prev_close) * 100
    
    if change_rate <= 0: 
        continue 
    
    # 3. 거래량 산출
    avg_volume = prev_20_days['Volume'].mean()
    vol_ratio = (today_data['Volume'] / avg_volume) * 100 if avg_volume > 0 else 0
    
    row = 1 if change_rate < 3 else 2 if change_rate < 6 else 3 if change_rate < 12 else 4
    col = 1 if vol_ratio < 100 else 2 if vol_ratio < 200 else 3 if vol_ratio < 500 else 4
    
    stock_name = final_500.loc[code, 'Name']
    cell_id = f"R{row}C{col}"
    
    matrix_results[cell_id].append({
        "code": code, "name": stock_name, "change": round(change_rate, 2), "volume": round(vol_ratio, 1)
    })
    
    today_captured_list.append({
        'Date': target_date_formatted, 'Code': code, 'Name': stock_name, 'Cell': cell_id, 'Base_Price': today_data['Close'],
        '1D_Return': None, '3D_Return': None, '5D_Return': None, 'Settled_Count': 0
    })

print("📝 [4단계] 최소 자원 추적관찰(Tracking) 장부 정산 가동...")
history_file = "matrix_history.csv"

if os.path.exists(history_file):
    df_history = pd.read_csv(history_file)
else:
    df_history = pd.DataFrame(columns=['Date', 'Code', 'Name', 'Cell', 'Base_Price', '1D_Return', '3D_Return', '5D_Return', 'Settled_Count'])

df_unsettled = df_history[df_history['Settled_Count'] < 3]

for idx, row_data in df_unsettled.iterrows():
    code = str(row_data['Code']).zfill(6)
    file_name = f"data_{code}.csv"
    if not os.path.exists(file_name): continue
    
    df_stock = pd.read_csv(file_name)
    df_after = df_stock[df_stock.iloc[:, 0] >= row_data['Date']] 
    passed_days = len(df_after) - 1 
    
    if passed_days >= 1 and pd.isna(df_history.loc[idx, '1D_Return']):
        close_1d = df_after.iloc[1]['Close']
        df_history.loc[idx, '1D_Return'] = round(((close_1d - row_data['Base_Price']) / row_data['Base_Price']) * 100, 2)
        df_history.loc[idx, 'Settled_Count'] += 1
        
    if passed_days >= 3 and pd.isna(df_history.loc[idx, '3D_Return']):
        close_3d = df_after.iloc[3]['Close'] if len(df_after) > 3 else df_after.iloc[-1]['Close']
        df_history.loc[idx, '3D_Return'] = round(((close_3d - row_data['Base_Price']) / row_data['Base_Price']) * 100, 2)
