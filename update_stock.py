import FinanceDataReader as fdr
import pandas as pd
import datetime
import os
import json
import time

print("🚀 [1단계] 깃허브 IP 차단 우회 데이터 스코어링 가동...")

# 1. 오늘 기준 전 종목 데이터 가져오기 (KRX 차단 우회용 FDR 사용)
df_krx = fdr.StockListing('KRX')

# [중복 및 노이즈 제거] 우선주 및 코넥스 시장 종목 원천 배제
df_krx = df_krx[~df_krx['Name'].str.endswith(('우', '우B', '우C'))]
df_krx = df_krx[df_krx['Market'] != 'KONEX']

# 2. 각각 순위 매기기 및 50% 가중치 합산
df_krx['시총순위'] = df_krx['Marcap'].rank(ascending=False)
df_krx['거래량순위'] = df_krx['Volume'].rank(ascending=False)
df_krx['종합점수'] = (df_krx['시총순위'] * 0.5) + (df_krx['거래량순위'] * 0.5)

# 최정예 500개 종목 추출
final_500 = df_krx.sort_values(by='종합점수').head(500)
target_codes = final_500['Code'].tolist()

print(f"🔥 최정예 주도주 {len(target_codes)}개 종목 선별 완료.")
print("📥 [2단계] 데이터 다이어트 및 증분 업데이트 시작 (API 쿨타임 적용)...")

today_str = datetime.date.today().strftime('%Y-%m-%d')

# 3. 500개 종목을 돌면서 데이터 업데이트
for code in target_codes:
    file_name = f"data_{code}.csv"
    
    if os.path.exists(file_name):
        df_existing = pd.read_csv(file_name, index_col=0)
        df_today = fdr.DataReader(code, start=today_str, end=today_str)
        
        if not df_today.empty:
            if today_str not in df_existing.index:
                df_updated = pd.concat([df_existing, df_today])
                df_updated.to_csv(file_name)
    else:
        start_date = (datetime.date.today() - datetime.timedelta(days=5*365)).strftime('%Y-%m-%d')
        df_historical = fdr.DataReader(code, start=start_date, end=today_str)
        df_historical.to_csv(file_name)
        
    # 서버 부하 및 IP 차단 방지를 위한 미세 딜레이
    time.sleep(0.1)

print("📊 [3단계] 오늘 자 4×4 매트릭스 계산기 가동 (증권사 HTS 상승률 기준)...")
matrix_results = {f"R{i}C{j}": [] for i in range(1, 5) for j in range(1, 5)}
today_captured_list = []

for code in target_codes:
    file_name = f"data_{code}.csv"
    if not os.path.exists(file_name): continue
    
    df = pd.read_csv(file_name)
    if len(df) < 21: continue 
    
    today_data = df.iloc[-1]
    prev_20_days = df.iloc[-21:-1]
    
    # 1. 캔들 필터: '양봉' 조건 (시가보다 종가가 높은 경우)
    if today_data['Close'] <= today_data['Open']: 
        continue
    
    # 2. 증권사 기준 상승률 산출: (오늘 종가 - 어제 종가) / 어제 종가
    prev_close = prev_20_days.iloc[-1]['Close']
    change_rate = ((today_data['Close'] - prev_close) / prev_close) * 100
    
    if change_rate <= 0: 
        continue 
    
    # 3. 거래량 산출: (오늘 거래량 / 과거 20일 평균 거래량)
    avg_volume = prev_20_days['Volume'].mean()
    vol_ratio = (today_data['Volume'] / avg_volume) * 100 if avg_volume > 0 else 0
    
    # 매트릭스 위치 선정 
    row = 1 if change_rate < 3 else 2 if change_rate < 6 else 3 if change_rate < 12 else 4
    col = 1 if vol_ratio < 100 else 2 if vol_ratio < 200 else 3 if vol_ratio < 500 else 4
    
    stock_name = final_500[final_500['Code'] == code]['Name'].values[0]
    cell_id = f"R{row}C{col}"
    
    matrix_results[cell_id].append({
        "code": code, "name": stock_name, "change": round(change_rate, 2), "volume": round(vol_ratio, 1)
    })
    
    today_captured_list.append({
        'Date': today_str, 'Code': code, 'Name': stock_name, 'Cell': cell_id, 'Base_Price': today_data['Close'],
        '1D_Return': None, '3D_Return': None, '5D_Return': None, 'Settled_Count': 0
    })

print("📝 [4단계] 사후 추적관찰(Tracking) 장부 정산 가동...")
history_file = "matrix_history.csv"

if os
