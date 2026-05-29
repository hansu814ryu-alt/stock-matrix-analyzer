import FinanceDataReader as fdr
import pandas as pd
import datetime
import os
import json
import time

print("🚀 [1단계] KRX 전체 종목(전수조사) 필터링 가동...")

# 1. 오늘 기준 전 종목 데이터 가져오기 
df_krx = fdr.StockListing('KRX')

# [중복 및 노이즈 제거] 우선주 및 코넥스 시장 종목 원천 배제
df_krx = df_krx[~df_krx['Name'].str.endswith(('우', '우B', '우C'))]
df_krx = df_krx[df_krx['Market'] != 'KONEX']

# [로직 변경] Top 500 컷오프 삭제! 전체 종목을 타겟으로 설정 (약 2,000여 개)
# 단, 대형주/중소형주 거래량 기준(300% vs 500%)을 나누기 위해 시가총액 순위표만 미리 만들어 둡니다.
df_krx['시총순위'] = df_krx['Marcap'].rank(ascending=False)
target_codes = df_krx['Code'].tolist()

print(f"🔥 조건 없이 전체 {len(target_codes)}개 종목 전수조사 대상 확정.")
print("📥 [2단계] 데이터 다이어트 및 증분 업데이트 시작 (API 쿨타임 적용)...")

today_str = datetime.date.today().strftime('%Y-%m-%d')

# 2. 전체 종목을 돌면서 데이터 업데이트
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
        # 최초 1회 실행 시 5년 치 수집
        start_date = (datetime.date.today() - datetime.timedelta(days=5*365)).strftime('%Y-%m-%d')
        df_historical = fdr.DataReader(code, start=start_date, end=today_str)
        df_historical.to_csv(file_name)
        
    # 서버 부하 및 IP 차단 방지를 위한 미세 딜레이
    time.sleep(0.1)

print("📊 [3단계] 4×4 매트릭스 계산기 가동 (전체 종목 대상)...")
matrix_results = {f"R{i}C{j}": [] for i in range(1, 5) for j in range(1, 5)}
today_captured_list = []

for code in target_codes:
    file_name = f"data_{code}.csv"
    if not os.path.exists(file_name): continue
    
    df = pd.read_csv(file_name)
    if len(df) < 21: continue 
    
    today_data = df.iloc[-1]
    prev_20_days = df.iloc[-21:-1]
    
    # 1. 캔들 필터: 점상한가/십자도지(시가=종가) 허용 (확실한 음봉만 탈락)
    if today_data['Close'] < today_data['Open']: 
        continue
    
    # 2. 증권사 기준 상승률 산출: (오늘 종가 - 어제 종가) / 어제 종가
    prev_close = prev_20_days.iloc[-1]['Close']
    change_rate = ((today_data['Close'] - prev_close) / prev_close) * 100
    
    if change_rate <= 0: 
        continue 
    
    # 3. 거래량 산출: (오늘 거래량 / 과거 20일 평균 거래량)
    avg_volume = prev_20_days['Volume'].mean()
    vol_ratio = (today_data['Volume'] / avg_volume) * 100 if avg_volume > 0 else 0
    
    # 종목의 체급(시총순위) 확인
    mc_rank = df_krx[df_krx['Code'] == code]['시총순위'].values[0]
    
    # 대형주(100위 이내)는 300%를 폭발 기준으로, 중소형주는 500%를 폭발 기준으로 적용
    c4_threshold = 300 if mc_rank <= 100 else 500
    
    # 매트릭스 위치 선정 
    row = 1 if change_rate < 3 else 2 if change_rate < 6 else 3 if change_rate < 12 else 4
    col = 1 if vol_ratio < 100 else 2 if vol_ratio < 200 else 3 if vol_ratio < c4_threshold else 4
    
    stock_name = df_krx[df_krx['Code'] == code]['Name'].values[0]
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
        df_history.loc[idx, 'Settled_Count'] += 1
        
    if passed_days >= 5 and pd.isna(df_history.loc[idx, '5D_Return']):
        close_5d = df_after.iloc[5]['Close'] if len(df_after) > 5 else df_after.iloc[-1]['Close']
        df_history.loc[idx, '5D_Return'] = round(((close_5d - row_data['Base_Price']) / row_data['Base_Price']) * 100, 2)
        df_history.loc[idx, 'Settled_Count'] += 1

if today_captured_list:
    df_today_captured = pd.DataFrame(today_captured_list)
    df_history = pd.concat([df_history, df_today_captured], ignore_index=True)

df_history.to_csv(history_file, index=False)

print("📊 [4.5단계] 카테고리별 누적 통계(승률) 계산 중...")
stats_results = {f"R{i}C{j}": {"total": 0, "success": 0, "win_rate": 0} for i in range(1, 5) for j in range(1, 5)}

if not df_history.empty:
    df_settled = df_history[df_history['5D_Return'].notna()]
    for idx, row_data in df_settled.iterrows():
        cell = row_data['Cell']
        if cell in stats_results:
            stats_results[cell]["total"] += 1
            if row_data['5D_Return'] > 0: 
                stats_results[cell]["success"] += 1

    for cell in stats_results:
        tot = stats_results[cell]["total"]
        suc = stats_results[cell]["success"]
        stats_results[cell]["win_rate"] = round((suc / tot) * 100, 1) if tot > 0 else 0

final_web_data = {
    "captured": matrix_results,  
    "stats": stats_results       
}

with open('matrix_data.json', 'w', encoding='utf-8') as f:
    json.dump(final_web_data, f, ensure_ascii=False, indent=4)

print("🎉 전체 종목 전수조사 적용 완료! 이제 놓치는 주도주는 없습니다.")
