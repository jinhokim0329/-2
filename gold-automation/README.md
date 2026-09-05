# 금 시세 자동 반영 프로그램

매일 자동으로 국내 금시세를 가져와서, 스마트스토어 상품 가격을 자동으로 갱신합니다.

## 사용 순서

### 1. products.csv 채우기
`products.csv`를 열어서 (엑셀로 열어도 됩니다) 아래 칸을 상품별로 채워주세요.
- `product_type`: `순금` 또는 `14K/18K` 중 하나 (14K/18K는 자동으로 중량 x 0.64로 순금 환산되어 계산됩니다)
- `weight_g`: 중량(g)
- `labor_fee`: 공임비(원)
- `margin_rate`: 마진율 (예: 15%면 0.15)

`product_no`, `product_name`은 이미 채워져 있습니다. 금시세는 부가세 10%를 자동으로 붙여서 계산합니다.

### 2. GitHub 저장소에 이 폴더 전체를 업로드
GitHub 저장소(gold-price-automation)에 이 폴더의 파일을 모두 올려주세요.
(웹에서 "Add file" > "Upload files"로 드래그 앤 드롭 하면 됩니다)

### 3. GitHub Secrets에 키 3개 등록
저장소 페이지에서 **Settings > Secrets and variables > Actions > New repository secret** 으로 아래 3개를 등록하세요.

| Secret 이름 | 값 |
|---|---|
| `NAVER_CLIENT_ID` | 네이버 커머스 API에서 발급받은 Client ID |
| `NAVER_CLIENT_SECRET` | 네이버 커머스 API에서 발급받은 Client Secret |
| `GOLD_API_SERVICE_KEY` | 공공데이터포털에서 발급받은 서비스키 (Encoding된 값) |

### 4. 금시세 API 연동 완료
`get_gold_price_per_gram()` 함수는 실제 API 응답 확인을 거쳐 이미 완성되어 있습니다.
(KRX 금시장의 "금 99.99_1kg" 종목 종가를 1g당 가격으로 사용합니다)

### 5. 테스트 실행
GitHub 저장소의 **Actions** 탭 > "Daily Gold Price Update" > **Run workflow** 버튼으로
수동 실행해서 정상 작동하는지 먼저 확인해보세요. 로그에서 각 상품의 성공/실패 여부를 볼 수 있습니다.

### 6. 이후에는 자동으로
매일 한국시간 오전 9시에 자동으로 실행됩니다. (스케줄은 `.github/workflows/daily-price-update.yml`에서 변경 가능)

## 주의할 점
- 지금 버전은 상품의 "기본가"만 자동으로 갱신합니다. 옵션(14K/18K, 색상 등)별 추가금액은 그대로 유지됩니다.
- 네이버 API 응답 구조가 실제로는 문서와 다를 수 있어, 처음 한두 번은 로그를 꼭 확인해주세요.
