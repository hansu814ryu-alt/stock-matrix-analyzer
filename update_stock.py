import FinanceDataReader as fdr
import pandas as pd
import datetime
import os
import json

print("🚀 [1단계] 시가총액/거래량(Volume) 복합 스코어링 필터 가동...")
df_krx = fdr.StockListing('KRX')

# [중복 및 노이즈 제거] 우선주 및 코넥스 시장 종목 원천 배제
df_krx = df_krx[~df_krx['Name'].str.endswith(('우', '우B', '우C'))]
df_krx = df_krx[df_krx['Market'] != 'KONEX']

# 각각 순위 매기기 및 50% 가중치 합산
df_krx['시총순위'] = df_krx['Marcap'].rank(ascending=False)
df_krx['거래량순위'] = df_krx['Volume'].rank(ascending=False)
df_krx['종합점수'] = (df_krx['시총순위'] * 0.5) + (df_krx['거래량순위'] * 0.5)

final_500 = df_krx.sort_values(by='종합점수').head(500)
target_codes = final_500['Code'].tolist()

print(f"🔥 최정예 주도주 {len(target_codes)}개 종목 선별 완료.")
print("📥 [2단계] 데이터 다이어트 및 증분 업데이트 시작...")

today_str = datetime.date.today().strftime('%Y-%m-%d')

# 500개 종목 데이터 업데이트
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

print("📊 [3단계] 오늘 자 4×4 매트릭스 계산기 가동 (증권사 상승률 기준)...")
matrix_results = {f"R{i}C{j}": [] for i in range(1, 5) for j in range(1, 5)}
today_captured_list = []

for code in target_codes:
    file_name = f"data_{code}.csv"
    if not os.path.exists(file_name): continue
    
    df = pd.read_csv(file_name)
    if len(df) < 21: continue
    
    today_data = df.iloc[-1]
    prev_20_days = df.iloc[-21:-1]
    
    # [핵심 변경] 증권사 기준: 전일 종가 대비 당일 종가의 상승률
    prev_close = prev_20_days.iloc[-1]['Close']
    change_rate = ((today_data['Close'] - prev_close) / prev_close) * 100
    
    # 거래량 비율: 최근 20일 평균 대비 당일 거래량
    avg_volume = prev_20_days['Volume'].mean()
    vol_ratio = (today_data['Volume'] / avg_volume) * 100 if avg_volume > 0 else 0
    
    # [필터링 1] 전일 대비 하락하거나 오르지 않은 종목 제외
    if change_rate <= 0: continue 
    
    # [필터링 2] '양봉' 원칙 유지 (어제보다 올랐어도 오늘 시가보다 종가가 낮은 '음봉'이면 제외)
    # 만약 음봉이든 양봉이든 증권사 기준 상승률만 맞으면 모두 포함하려면 아래 줄을 지우거나 주석(#) 처리하세요.
    if today_data['Close'] < today_data['Open']: continue 
    
    # 매트릭스 위치 선정 (상승률 4구간)
    row = 1 if change_rate < 3 else 2 if change_rate < 6 else 3 if change_rate < 12 else 4
    
    # 매트릭스 위치 선정 (거래량 4구간)
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

if os.path.exists(history_file) and not df_history.empty:
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

print("🎉 증권사 상승률 기준 전 프로세스 및 누적 승률 계산이 성공적으로 끝났습니다!")
