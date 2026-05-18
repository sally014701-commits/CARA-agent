# CARA-agent

CARA 추천 시스템 백엔드 벤치마크를 위한 합성 데이터셋 저장소입니다.

이 저장소는 Python 3.11 환경에서 별도 DB 서버 없이 JSON 파일을 내장 DB처럼 로드해서 사용할 수 있도록 구성되어 있습니다.

## Files

| File | Description |
| --- | --- |
| `generate_synthetic_dataset.py` | 상품/소비자 mock data를 생성하는 Python 스크립트 |
| `main.py` | 에이전트들이 호출하는 FastAPI Tool Use Module |
| `planner_agent.py` | Executor Agent에 전달할 추천 계획을 생성하는 Planner Agent |
| `products.json` | 상품 카탈로그 데이터 200개 |
| `consumers.json` | 소비자 프로필 및 세션 행동 데이터 50명 |

## Dataset Overview

### products.json

총 200개의 상품 데이터를 포함합니다.

상품은 5개 카테고리와 각 카테고리의 5개 세부 품목으로 구성되며, 세부 품목마다 8개씩 균등하게 생성됩니다.

| Category | Item Types |
| --- | --- |
| `electronics` | `smartphones`, `laptops`, `earbuds`, `tablets`, `smartwatches` |
| `fashion` | `sneakers`, `jackets`, `jeans`, `dresses`, `bags` |
| `home living` | `desk lamps`, `air purifiers`, `coffee makers`, `pillows`, `storage boxes` |
| `beauty` | `moisturizers`, `sunscreens`, `serums`, `lip balms`, `shampoos` |
| `sports equipment` | `yoga mats`, `dumbbells`, `running shoes`, `water bottles`, `resistance bands` |

#### Product Schema

```json
{
  "product_id": "P0172",
  "category": "sports equipment",
  "item_type": "dumbbells",
  "name": "Dumbbells 0172",
  "price": 1483000,
  "style_type": "design",
  "rating": 4.4,
  "review_count": 175
}
```

| Field | Type | Description |
| --- | --- | --- |
| `product_id` | string | `P0001` 형식의 상품 고유 ID |
| `category` | string | 상위 상품 카테고리 |
| `item_type` | string | 카테고리 내 세부 품목 |
| `name` | string | mock 상품명 |
| `price` | integer | 5,000원부터 1,500,000원 사이의 가격, 1,000원 단위 |
| `style_type` | string | `practical` 또는 `design` |
| `rating` | float | 3.5부터 5.0 사이의 평점, 소수점 첫째 자리 |
| `review_count` | integer | 10부터 5,000 사이의 리뷰 수 |

#### Product Generation Rules

- `price`는 균등 분포에서 샘플링한 뒤 1,000원 단위로 반올림합니다.
- `style_type`은 `practical`, `design` 중 50% 확률로 할당합니다.
- `rating`은 `[3.5, 5.0]` 구간에서 균등 샘플링합니다.
- `review_count`는 `numpy.random.pareto` 기반 long-tail 분포로 생성합니다.
- 대부분의 상품은 10~200개의 리뷰를 갖고, 극소수 상품만 5,000에 가까운 리뷰 수를 갖도록 조정합니다.

### consumers.json

총 50명의 소비자 프로필과 동적 세션 행동 데이터를 포함합니다.

#### Consumer Schema

```json
{
  "consumer_id": "C0001",
  "preference_style": "design",
  "budget_level": "high",
  "purchase_history": ["P0161", "P0051", "P0002"],
  "session_behavior": {
    "page_visits": 27,
    "dwell_times": [43.73, 78.92, 65.2],
    "dwell_time_variance": 1665.72,
    "scroll_depths": [0.9, 0.99, 0.784],
    "average_scroll_depth": 0.801,
    "ctr": 0.3,
    "brainfry_score": 0.62
  },
  "ctr": 0.3,
  "brainfry_score": 0.62
}
```

| Field | Type | Description |
| --- | --- | --- |
| `consumer_id` | string | `C0001` 형식의 소비자 고유 ID |
| `preference_style` | string | `practical` 또는 `design` |
| `budget_level` | string | `low`, `mid`, `high` |
| `purchase_history` | array[string] | 구매 이력으로 선택된 상품 ID 목록 |
| `session_behavior` | object | 임시 세션 행동 기록 |
| `ctr` | float | 소비자 단위 클릭률 |
| `brainfry_score` | float | 소비자 단위 인지 과부하 점수 |

#### Consumer Generation Rules

- `preference_style`은 `practical`, `design` 중 50% 확률로 할당합니다.
- `budget_level`은 `low`, `mid`, `high` 중 동일 확률로 할당합니다.
- `purchase_history`는 전체 상품 200개 중 3~20개 상품 ID를 무작위로 선택합니다.
- 구매 이력은 소비자의 `preference_style`과 상품의 `style_type`이 일치하는 상품이 더 높은 확률로 포함되도록 편향되어 있습니다.

## Session Behavior

소비자별로 벤치마크 테스트용 동적 세션 행동을 생성합니다.

| Preference Style | Page Visits | Dwell Time | Scroll Depth |
| --- | --- | --- | --- |
| `design` | 20~30 | 30~180초 | 0.6~1.0 |
| `practical` | 5~15 | 15~90초 | 0.3~0.8 |

`design` 선호 소비자는 탐색적 성향을 반영해 더 많은 페이지를 방문하고, 더 오래 머무르며, 더 깊게 스크롤합니다.

`practical` 선호 소비자는 효율적 탐색 성향을 반영해 상대적으로 적은 페이지를 방문합니다.

## CTR and BrainFry

CTR은 `[0.0, 1.0]` 범위의 실수입니다.

페이지 방문 수와 체류 시간 분산이 클수록 클릭률이 낮아지도록 역상관 구조로 생성합니다. 이는 많은 페이지를 수동적으로 훑지만 실제 클릭은 줄어드는 정보 과부하 상태를 mock으로 재현하기 위한 설계입니다.

BrainFry score는 아래 공식으로 계산합니다.

```text
B = 0.4 * (n / 30) + 0.3 * (sigma_squared / 10000) + 0.3 * (1 - CTR)
```

| Symbol | Meaning |
| --- | --- |
| `B` | BrainFry score |
| `n` | page visits |
| `sigma_squared` | dwell time variance |
| `CTR` | click-through rate |

## How to Regenerate Dataset

```bash
python generate_synthetic_dataset.py
```

실행하면 같은 디렉터리에 아래 파일이 다시 생성됩니다.

- `products.json`
- `consumers.json`

현재 스크립트는 `RANDOM_SEED = 42`를 사용하므로 동일한 환경에서는 재현 가능한 데이터셋을 생성합니다.

## Tool Use Module

FastAPI 서버를 실행합니다.

```bash
python main.py
```

주요 엔드포인트는 다음과 같습니다.

| Endpoint | Purpose |
| --- | --- |
| `GET /consumers/{consumer_id}/history` | 소비자 구매 이력, 세션 행동, 선호 벡터 조회 |
| `GET /products/search` | 키워드 및 필터 기반 상품 후보군 검색 |
| `GET /products/trending` | 리뷰 수 기준 인기 상품 Top 20 조회 |

`/consumers/{consumer_id}/history` 응답의 `preference_vector`에는 Planner Agent가 사용하는 `top_style`, `average_historical_spend`, `maximum_historical_spend`, `brainfry_score`가 포함됩니다.

## Planner Agent

Planner Agent는 FastAPI Tool Use Module의 `get_consumer_history` 도구를 호출한 뒤, 다음 순서로 Executor Agent에 전달할 추천 계획을 생성합니다.

1. 소비자 프로필 및 구매 이력 조회
2. 현재 세션 기반 BrainFry score 계산
3. 이전 세션 BrainFry score와 비교해 더 큰 값 선택
4. 예산 상한선 추론
5. 스타일 선호도 추론

실행 예시는 다음과 같습니다.

```bash
python planner_agent.py
```

반환되는 plan 딕셔너리 예시는 다음과 같습니다.

```json
{
  "consumer_id": "C0001",
  "budget_ceiling": 1414000,
  "preferred_style": "design",
  "brainfry_level": "MID",
  "brainfry_score": 0.62
}
```
