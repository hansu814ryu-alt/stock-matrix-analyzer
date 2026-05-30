import FinanceDataReader as fdr

# LG이노텍(011070)의 최근 5일치 데이터를 불러옵니다.
df = fdr.DataReader('011070')
print("=== LG이노텍 최근 주가 및 거래량 원본 데이터 ===")
print(df.tail(3))
