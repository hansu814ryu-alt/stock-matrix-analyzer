import FinanceDataReader as fdr
import pandas as pd
import datetime
import os
import json
import time

print("🚀 [1단계] 복잡한 조건 폐기! KRX 전체 종목 초경량 스캔 가동...")

# 1. 한국 시장 전체 종목 리스트 가져오기
df_krx = fdr.StockListing('KRX')

# 우선주 및 코넥스 종목만 필터링 (순수 보통주만 남김)
df_krx = df_krx[~df_krx['Name'].str.endswith(('우', '우B', '우C'))]
df_krx = df_krx[df_krx['Market'] != 'KONEX']

target_codes = df_krx['Code'].tolist()
name_dict = dict(zip(df_krx['Code'], df_krx['Name'])) # 빠른 이름 찾기를 위한 사전

print(f"🔥 타겟 종목: {len(target_codes)}개 (전수조사 확정)")
print("📥 [2단계] 과거 파일 삭제! 실시간 '어제 vs 오늘' 1:1 데스매치 필터링 시작...")

# 데이터 조회를 위한 날짜 설정 (휴일 고려 넉넉하게 10일 전부터 오늘까지)
start_date = (datetime.date.today() - datetime.timedelta(days=10)).strftime('%Y-%m-%d')
today_str = datetime.date.today().strftime('%Y-%m-%d')

matrix_results = {f"R{i}C{j}": [] for i in range(1, 5) for j in range(1, 5)}
today_captured_list = []

# 2. 전체 종목을 돌며 '어제와 오늘'만 비교
for code in target_codes:
    try:
        # 최근 데이터 호출 (가장 마지막 줄이 오늘, 그 윗줄이 어제)
        df = fdr.DataReader(code, start=start_date, end=today_str)
        
        if len(df) < 2: 
            continue # 신규 상장 등으로 어제 데이터가 없으면 패스
            
        today_data = df.iloc[-1]
        prev_data = df.iloc[-2]
        
        prev_close = prev_data['Close']
        today_close = today_data['Close']
        prev_vol = prev_data['Volume']
        today_vol = today_data['Volume']
        
        # 1) Y축 상승률 계산: 어제 종가 대비 오늘 0.1%라도 올랐는가?
        if prev_close == 0: continue
        change_rate = ((today_close - prev_close) / prev_close) * 100
        
        if change_rate <= 0: 
            continue # 하락하거나 보합인 종목은 즉시 컷아웃
            
        # 2) X축 거래량 비율 계산: 어제 거래량 대비 오늘 얼마나 터졌는가?
        if prev_vol == 0:
            vol_ratio = 9999 # 어제 거래정지 등으로 거래량이 0이었다면 폭발로 간주
        else:
            vol_ratio = (today_vol / prev_vol) * 100
            
        # 3) 새로운 4×4 매트릭스 위치 선정 (절대 규칙)
        # 상승률 4구간
        row = 1 if change_rate < 3 else 2 if change_rate < 6 else 3 if change_rate < 12 else 4
        # 거래량 4구간 (전일 대비)
        col = 1 if vol_ratio < 100 else 2 if vol_ratio < 150 else 3 if vol_ratio < 200 else 4
        
        cell_id = f"R{row}C{col}"
        stock_name = name_dict.get(code, code)
        
        matrix_results[cell_id].append({
            "code": code, "name": stock_name, "change": round(change_rate, 2), "volume": round(vol_ratio, 1)
        })
        
        today_captured_list.append({
            'Date': today_str, 'Code': code, 'Name': stock_name, 'Cell': cell_id, 'Base_Price': today_close,
            '1D_Return': None, '3D_Return': None, '5D_Return': None, 'Settled_Count': 0
        })
        
    except Exception as e:
        pass # API 통신 에러가 나면 해당 종목만 건너뜀
        
    time.sleep(0.05) # IP 차단 방지용 미세 딜레이 (전체 다 돌려도 2~3분 소요)

print("📝 [3단계] 사후 추적관찰(Tracking) 장부 정산 가동 (CSV 없이 실시간 검증)...")
history_file = "matrix_history.csv"

# 과거 기록 장부 읽기
if os.path.exists(history_file):
    df_history = pd.read_csv(history_file)
else:
    df_history = pd.DataFrame(columns=['Date', 'Code', 'Name', 'Cell', 'Base_Price', '1D_Return', '3D_Return', '5D_Return', 'Settled_Count'])

# 정산이 안 끝난 과거 포착 종목들 실시간 검증
df_unsettled = df_history[df_history['Settled_Count'] < 3]

for idx, row_data in df_unsettled.iterrows():
    code = str(row_data['Code']).zfill(6)
    try:
        # 포착된 날짜부터 오늘까지만 딱 조회해서 수익률 채점
        df_stock = fdr.DataReader(code, start=row_data['Date'], end=today_str)
        passed_days = len(df_stock) - 1 
        
        if passed_days >= 1 and pd.isna(df_history.loc[idx, '1D_Return']):
            close_1d = df_stock.iloc[1]['Close']
            df_history.loc[idx, '1D_Return'] = round(((close_1d - row_data['Base_Price']) / row_data['Base_Price']) * 100, 2)
            df_history.loc[idx, 'Settled_Count'] += 1
            
        if passed_days >= 3 and pd.isna(df_history.loc[idx, '3D_Return']):
            close_3d = df_stock.iloc[3]['Close'] if len(df_stock) > 3 else df_stock.iloc[-1]['Close']
            df_history.loc[idx, '3D_Return'] = round(((close_3d - row_data['Base_Price']) / row_data['Base_Price']) * 100, 2)
            df_history.loc[idx, 'Settled_Count'] += 1
            
        if passed_days >= 5 and pd.isna(df_history.loc[idx, '5D_Return']):
            close_5d = df_stock.iloc[5]['Close'] if len(df_stock) > 5 else df_stock.iloc[-1]['Close']
            df_history.loc[idx, '5D_Return'] = round(((close_5d - row_data['Base_Price']) / row_data['Base_Price']) * 100, 2)
            df_history.loc[idx, 'Settled_Count'] += 1
    except:
        pass
    time.sleep(0.05)

# 오늘 새롭게 포착된 종목들을 장부 맨 밑에 추가
if today_captured_list:
    df_today_captured = pd.DataFrame(today_captured_list)
    df_history = pd.concat([df_history, df_today_captured], ignore_index=True)

df_history.to_csv(history_file, index=False)

print("📊 [4단계] 카테고리별 누적 통계(승률) 최종 계산 중...")
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

print("🎉 리셋 완료! 완전히 새로워진 초정밀 4x4 매트릭스 데이터가 생성되었습니다.")
