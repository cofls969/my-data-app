import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timedelta, timezone

# -----------------------------------------------------------
# 1. 한국 시간(KST) 기준으로 '어제' 날짜 계산하기
# -----------------------------------------------------------
# 배포된 서버의 시간이 미국 시간(UTC)일 수 있으므로, 항상 한국 시간(UTC+9)으로 고정합니다.
KST = timezone(timedelta(hours=9))
today_kst = datetime.now(KST)
yesterday_kst = today_kst - timedelta(days=1)

# API가 요구하는 'YYYYMMDD' 형식(예: 20231024)으로 변환합니다.
target_dt = yesterday_kst.strftime('%Y%m%d')
display_date = yesterday_kst.strftime('%Y년 %m월 %d일')


# -----------------------------------------------------------
# 2. 데이터 가져오기 (캐싱 적용)
# -----------------------------------------------------------
# @st.cache_data를 쓰면 똑같은 요청을 반복하지 않고 결과를 1시간(3600초) 동안 기억합니다.
# ttl=3600 은 Time To Live의 약자로 3600초(1시간)를 의미합니다.
@st.cache_data(ttl=3600)
def fetch_box_office_data(date_str, api_key):
    url = "https://www.kobis.or.kr/kobisopenapi/webservice/rest/boxoffice/searchDailyBoxOfficeList.json"
    # API 요청에 필요한 변수들
    params = {
        "key": api_key,
        "targetDt": date_str
    }
    
    try:
        # 영화진흥위원회 서버로 데이터 요청
        response = requests.get(url, params=params)
        response.raise_for_status() # 인터넷 연결 문제 등이 있으면 여기서 에러를 발생시킴
        return response.json()      # 결과물을 파이썬 딕셔너리로 변환해서 반환
    except Exception as e:
        # 에러가 발생하면 에러 내용을 딕셔너리 형태로 반환
        return {"network_error": str(e)}


# -----------------------------------------------------------
# 3. 스트림릿 화면 구성하기
# -----------------------------------------------------------
st.set_page_config(page_title="어제의 박스오피스", page_icon="🍿")
st.title(f"🍿 어제의 박스오피스")
st.write(f"**기준일:** {display_date}")

# Streamlit 비밀 금고(Secrets)에서 인증키 가져오기
# 코드에 키를 직접 적으면 해킹의 위험이 있으므로 꼭 secrets를 사용해야 합니다.
if "KOBIS_KEY" not in st.secrets:
    st.error("🚨 스트림릿 설정(Secrets)에 `KOBIS_KEY`가 없습니다. 인증키 설정을 확인해 주세요.")
    st.stop() # 여기서 앱 실행을 멈춤

api_key = st.secrets["KOBIS_KEY"]

# 로딩 스피너를 보여주며 데이터 가져오기 함수 실행
with st.spinner("데이터를 불러오는 중입니다..."):
    data = fetch_box_office_data(target_dt, api_key)

# -----------------------------------------------------------
# 4. 에러 및 예외 상황 처리하기
# -----------------------------------------------------------
# 4-1. 네트워크 통신 오류 처리
if "network_error" in data:
    st.error("📡 인터넷 연결이나 영화진흥위원회 서버에 문제가 발생했습니다. 잠시 후 다시 시도해 주세요.")
    st.stop()

# 4-2. API 인증키 오류 처리 (faultInfo)
if "faultInfo" in data:
    error_msg = data["faultInfo"].get("message", "알 수 없는 오류")
    st.error(f"🔑 API 인증키 문제로 데이터를 가져오지 못했습니다.\n\n확인 내용: {error_msg}")
    st.stop()

# 4-3. 데이터 구조 이상 확인
if "boxOfficeResult" not in data or "dailyBoxOfficeList" not in data["boxOfficeResult"]:
    st.error("📉 영화진흥위원회에서 예상치 못한 형태의 데이터를 보냈습니다. 잠시 후 다시 확인해 주세요.")
    st.stop()

# 영화 목록 데이터만 뽑아내기
movie_list = data["boxOfficeResult"]["dailyBoxOfficeList"]

# 4-4. 영화 목록이 비어있는 경우 (아직 집계 전)
if len(movie_list) == 0:
    st.warning("🎬 아직 어제의 박스오피스 결과가 집계되지 않았습니다. 보통 오전 늦게 업데이트되니 나중에 다시 방문해 주세요!")
    st.stop()


# -----------------------------------------------------------
# 5. 데이터 가공 및 화면에 보여주기
# -----------------------------------------------------------
# 가져온 데이터를 다루기 쉽게 판다스(Pandas) 데이터프레임으로 변환
df = pd.DataFrame(movie_list)

# 숫자가 문자열(글자)로 되어 있으므로, 정렬과 계산을 위해 진짜 숫자(정수형)로 변환
df['rank'] = df['rank'].astype(int)
df['audiCnt'] = df['audiCnt'].astype(int)
df['audiAcc'] = df['audiAcc'].astype(int)
df['scrnCnt'] = df['scrnCnt'].astype(int)

st.divider() # 가로 선 긋기

# --- [1위 영화 지표 카드] ---
top1_movie = df.iloc[0] # 첫 번째 줄(1위) 데이터만 가져옴
st.subheader(f"🥇 1위: {top1_movie['movieNm']}")

# 화면을 3칸으로 나누기
col1, col2, col3 = st.columns(3)
# :, 를 사용하면 천 단위마다 콤마(,)가 찍힙니다.
col1.metric(label="일일 관객수", value=f"{top1_movie['audiCnt']:,}명")
col2.metric(label="누적 관객수", value=f"{top1_movie['audiAcc']:,}명")
col3.metric(label="스크린 수", value=f"{top1_movie['scrnCnt']:,}개")

st.divider()

# --- [상위 5편 막대그래프] ---
st.subheader("📊 관객수 상위 5편")
# 상위 5개 데이터만 자르고, 영화명을 기준으로 관객수를 뽑아냅니다.
top5_df = df.head(5)[['movieNm', 'audiCnt']].set_index('movieNm')
# 스트림릿 내장 바 차트 그리기
st.bar_chart(top5_df, y_label="관객수 (명)")

st.divider()

# --- [전체 순위 표] ---
st.subheader("📋 박스오피스 전체 순위")
# 화면에 보여줄 컬럼만 선택하고, 보기 좋게 한국어로 이름을 바꿉니다.
display_df = df[['rank', 'movieNm', 'openDt', 'audiCnt', 'audiAcc', 'scrnCnt']].copy()
display_df.columns = ['순위', '영화명', '개봉일', '관객수', '누적관객수', '스크린수']

# 데이터프레임을 화면에 표로 출력 (인덱스 번호는 숨김)
st.dataframe(display_df, hide_index=True, use_container_width=True)
