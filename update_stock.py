import FinanceDataReader as fdr
import pandas as pd
import datetime
import os
import json
import time

print("🚀 [시스템 개정] 5대 요구사항 반영 하이브리드 계량 엔진 가동...")

# 1. 한국 시장 전체 보통주 라인업 로드
df_krx = fdr.StockListing('KRX')
df_krx = df_krx[~df_krx['Name'].str.endswith(('우', '우B', '우C'))]
df_krx = df_krx[df_krx['Market'] != 'KONEX']

target_codes = df_krx['Code'].tolist()
name_dict = dict(zip(df_krx['Code'], df_krx['Name']))

# 이평선(60일) 계산을 위해 넉넉하게 120일 전부터 수집
start_date = (datetime.date.today() - datetime.timedelta(days=120)).strftime('%Y-%m-%d')
today_str = datetime.date.today().strftime('%Y-%m-%d')

# 장부 파일 초기화 또는 로드
history_file = "matrix_history.csv"
if os.path.exists(history_file):
    df_history = pd.read_csv(history_file)
    # 기존 장부의 Code 컬럼을 안전하게 문자열로 통일
    df_history['Code'] = df_history['Code'].astype(str).str.zfill(6)
else:
    df_history = pd.DataFrame(columns=[
        'Date', 'Code', 'Name', 'Cell', 'Type1', 'Type2', 'Type3', 
        'Base_Price', '1D_Return', '3D_Return', '5D_Return', 'Settled_Count',
        'Break_MA5', 'Break_MA20', 'Break_MA60'
    ])

matrix_results = {f"R{i}C{j}": [] for i in range(1, 5) for j in range(1, 5)}
today_captured_list = []
ma_breakthrough_stocks = []

print(f"📥 [2단계] {len(target_codes)}개 종목 이동평균선 및 전일비 복합 연산 시작...")

for code in target_codes:
    try:
        code_str = str(code).zfill(6)
        df = fdr.DataReader(code_str, start=start_date, end=today_str)
        if len(df) < 61: continue # 최소 60일선 거래량 확보용
        
        # 이동평균선 생성
        df['MA5'] = df['Close'].rolling(5).mean()
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA60'] = df['Close'].rolling(60).mean()
        
        today_data = df.iloc[-1]
        prev_data = df.iloc[-2]
        
        # 기본 가격/거래량 매칭
        prev_close = prev_data['Close']
        today_close = today_data['Close']
        prev_vol = prev_data['Volume']
        today_vol = today_data['Volume']
        
        if prev_close == 0 or prev_vol == 0: continue
        
        # 수치 계산
        change_rate = ((today_close - prev_close) / prev_close) * 100
        vol_ratio = (today_vol / prev_vol) * 100
        
        if change_rate <= 0: continue # 전일 대비 상승 종목만 타겟팅
        
        # 이평선 상향 돌파(골든크로스) 여부 검증
        break_ma5 = bool(prev_data['Close'] <= prev_data['MA5'] and today_close > today_data['MA5'])
        break_ma20 = bool(prev_data['Close'] <= prev_data['MA20'] and today_close > today_data['MA20'])
        break_ma60 = bool(prev_data['Close'] <= prev_data['MA60'] and today_close > today_data['MA60'])
        
        if break_ma5 or break_ma20 or break_ma60:
            ma_breakthrough_stocks.append({
                "code": code_str, "name": name_dict.get(code_str, code_str),
                "ma5": break_ma5, "ma20": break_ma20, "ma60": break_ma60
            })
            
        # 4x4 매트릭스 포지셔닝
        row = 1 if change_rate < 3 else 2 if change_rate < 6 else 3 if change_rate < 12 else 4
        col = 1 if vol_ratio < 100 else 2 if vol_ratio < 150 else 3 if vol_ratio < 200 else 4
        cell_id = f"R{row}C{col}"
        stock_name = name_dict.get(code_str, code_str)
        
        # 상승률 2개 x 거래량 4개 구간별 유형 정의
        type1 = bool(row in [3, 4] and col in [1, 2, 3, 4]) # 강력 돌파형
        type2 = bool(row in [2, 3] and col in [1, 2, 3, 4]) # 추세 전환형
        type3 = bool(type1 and type2)                       # 중첩 교집합형
        
        # 과거 기록 기반 첫 번째 돌파 날짜 및 유형 추적
        past_records = df_history[df_history['Code'] == code_str] if not df_history.empty else pd.DataFrame()
        if not past_records.empty:
            first_date = str(past_records['Date'].min())
            first_cell = str(past_records[past_records['Date'] == first_date]['Cell'].values[0])
        else:
            first_date = today_str
            first_cell = cell_id
            
        # 매트릭스 결과 묶기
        matrix_results[cell_id].append({
            "code": code_str, "name": stock_name, "change": round(change_rate, 2), "volume": round(vol_ratio, 1),
            "first_date": first_date, "first_cell": first_cell
        })
        
        # 오늘 장부 임시 보관
        today_captured_list.append({
            'Date': today_str, 'Code': code_str, 'Name': stock_name, 'Cell': cell_id,
            'Type1': type1, 'Type2': type2, 'Type3': type3, 'Base_Price': today_close,
            '1D_Return': None, '3D_Return': None, '5D_Return': None, 'Settled_Count': 0,
            'Break_MA5': break_ma5, 'Break_MA20': break_ma20, 'Break_MA60': break_ma60
        })
        
    except Exception as e:
        pass
    time.sleep(0.04)

print("📝 [3단계] 사후 추적관찰(Tracking) 과거 장부 정산 및 흐름 데이터 동기화...")
df_unsettled = df_history[df_history['Settled_Count'] < 3]

for idx, row_data in df_unsettled.iterrows():
    code_str = str(row_data['Code']).zfill(6)
    try:
        df_stock = fdr.DataReader(code_str, start=row_data['Date'], end=today_str)
        passed_days = len(df_stock) - 1
        
        if passed_days >= 1 and pd.isna(df_history.loc[idx, '1D_Return']):
            df_history.loc[idx, '1D_Return'] = round(((df_stock.iloc[1]['Close'] - row_data['Base_Price']) / row_data['Base_Price']) * 100, 2)
            df_history.loc[idx, 'Settled_Count'] += 1
        if passed_days >= 3 and pd.isna(df_history.loc[idx, '3D_Return']):
            idx_3d = min(3, len(df_stock)-1)
            df_history.loc[idx, '3D_Return'] = round(((df_stock.iloc[idx_3d]['Close'] - row_data['Base_Price']) / row_data['Base_Price']) * 100, 2)
            df_history.loc[idx, 'Settled_Count'] += 1
        if passed_days >= 5 and pd.isna(df_history.loc[idx, '5D_Return']):
            idx_5d = min(5, len(df_stock)-1)
            df_history.loc[idx, '5D_Return'] = round(((df_stock.iloc[idx_5d]['Close'] - row_data['Base_Price']) / row_data['Base_Price']) * 100, 2)
            df_history.loc[idx, 'Settled_Count'] += 1
    except:
        pass

# 오늘 데이터 추가 병합
if today_captured_list:
    df_history = pd.concat([df_history, pd.DataFrame(today_captured_list)], ignore_index=True)
df_history.to_csv(history_file, index=False)

print("📊 [4단계] 누적 포착 빈도 카운트 생성 및 고순위 순서 정렬...")
if not df_history.empty:
    count_series = df_history['Code'].value_counts()
    ranking_list = []
    # [버그 수정 완료] .items 뒤에 명확하게 괄호 () 바인딩 추가
    for cd, cnt in count_series.items():
        code_str = str(cd).zfill(6)
        ranking_list.append({
            "code": code_str, "name": name_dict.get(code_str, code_str), "count": int(cnt)
        })
else:
    ranking_list = []

print("⚙️ [5단계] 웹 배포용 고밀도 단일 JSON 패키징 빌드...")
final_web_data = {
    "captured": matrix_results,         
    "rankings": ranking_list,           
    "ma_breakthroughs": ma_breakthrough_stocks 
}

with open('matrix_data.json', 'w', encoding='utf-8') as f:
    json.dump(final_web_data, f, ensure_ascii=False, indent=4)

print("🎉 개정 로직 배포 준비 완료! 무결성 정산이 끝났습니다.")
