# CARA-agent

CARA(Context-Aware Recommendation Agent)는 사용자의 현재 탐색 행동, 대화 의도, 예산, 심리적 쇼핑 성향을 함께 반영해 상품을 추천하는 FastAPI 기반 멀티 에이전트 시스템입니다.

## 주요 구성

### 프론트엔드
- `CARA.html`: 사용자가 상품을 검색하고 CARA와 대화하며 추천을 받는 쇼핑 인터페이스
- `admin.html`: CARA 추천 결과와 페르소나 평가 점수를 확인하는 벤치마크 전용 페이지

### 백엔드 서버
- `main.py`: 정적 콘텐츠 제공, RESTful API(검색/추천/관리자), SQLite 통합을 담당하는 FastAPI 서버

### 추천 에이전트 파이프라인
- `planner_agent.py`: 사용자 의도, BrainFry 상태, 예산 제약, 선호 스타일을 통합해 추천 계획 수립
- `conversation_agent.py`: 필요시 2턴 대화 기반 정보 수집 및 텍스트 신호로 인지 과부하 감지
- `executor_agent.py`: 검색 규칙 기반 상품 후보 검색 후 벡터 임베딩과 RAG 점수로 재정렬
- `critic_agent.py`: 예산/평점/스타일 다양성/최소 개수 규칙 적용해 최종 결과 검수

### 검색 및 임베딩
- `search_rules.py`: 한국어 검색어 처리, 카테고리 매핑, 스킨타입 분류 규칙 정의
- `vector_search.py`: Voyage AI 기반 임베딩 생성, 벡터 검색, 유사 상품 추천 함수
- `fill_embeddings.py`: 상품 데이터베이스에 임베딩 벡터 생성 및 저장 스크립트
- `manage_embeddings.py`: 임베딩 스키마 관리, 카운팅, 임베딩 생성 제어 CLI 도구

## 주요 기능

- **벡터 기반 임베딩 검색**: Voyage AI를 활용한 의미론적 상품 검색으로 텍스트 매칭 이상의 유사도 파악
- **한국어 검색 최적화**: 동의어 확장, 카테고리 매핑, 스킨타입 자동 분류로 자연스러운 검색 경험 제공
- **실제 화장품 카탈로그**: `cara.db`에 500개 상품 메타데이터 및 임베딩 벡터 저장
- **사용자 프로필**: `consumers.json`에 200개 소비자 프로필(심리 성향, 구매 이력, 행동 지표) 로드
- **인지 과부하 추적(BrainFry)**: 행동 지표(방문 수, 체류 시간 분산, CTR) + 텍스트 신호로 사용자 상태 감지
- **상황 맞춤 추천 개수**: BrainFry score에 따라 추천 개수 자동 조절 (1~7개)
- **페르소나 기반 보정**: `utilitarian`, `hedonic`, `maximizer`, `value_seeker`, `loss_averse`, `impulsive` 성향별 점수 가중치 적용
- **통합 세션 추적**: SQLite에 채팅 기록, 에이전트 실행 트레이스, 이벤트 로그 저장
- **메인 내 라이브 에이전트 대시보드**: 시연 화면 좌측에서 세션 목록, 에이전트 타임라인, BrainFry/행동 지표를 실시간 표시
- **벤치마크 확인 페이지**: CARA 추천 결과와 페르소나별 만족도/결정 용이성 평가 조회
- **벤치마크 비교**: CARA 추천과 인기순 baseline을 20개 시나리오로 자동 비교

## 프로젝트 구조

| 파일/디렉토리 | 설명 |
| --- | --- |
| **핵심 서버** | |
| `main.py` | FastAPI 진입점. 정적 콘텐츠, RESTful API, DB 연동 관리 |
| **사용자 인터페이스** | |
| `CARA.html` | 사용자용 쇼핑 및 추천 인터페이스 |
| `admin.html` | 벤치마크 확인 전용 페이지 |
| **추천 에이전트** | |
| `planner_agent.py` | 사용자 컨텍스트 → 추천 계획 변환 |
| `conversation_agent.py` | 2턴 대화 + 텍스트 기반 인지 과부하 감지 |
| `executor_agent.py` | 상품 검색 + 임베딩 기반 점수 계산 |
| `critic_agent.py` | 최종 검수 (예산/평점/다양성/개수 규칙) |
| **데이터 관리** | |
| `database.py` | SQLite ORM, 세션/메시지/트레이스 테이블 정의 |
| **검색 및 임베딩** | |
| `search_rules.py` | 한국어 검색 규칙 (카테고리 매핑, 스킨타입 분류) |
| `vector_search.py` | Voyage AI 임베딩, 벡터 검색 유틸리티 함수 |
| `fill_embeddings.py` | 상품 임베딩 일괄 생성 스크립트 |
| `manage_embeddings.py` | 임베딩 관리 CLI (스키마/개수/유사상품 조회) |
| **평가 및 벤치마크** | |
| `persona_evaluator.py` | 6개 페르소나 기준 추천 품질 평가 |
| `benchmark_runner.py` | 20개 시나리오 벤치마크 (CARA vs 인기순) |
| **데이터 생성** | |
| `generate_synthetic_dataset.py` | 상품/소비자 synthetic 데이터 생성 |
| `generate_product_images.py` | 상품 이미지 PNG 생성 |
| `generate_category_labeled_images.py` | 카테고리별 템플릿 이미지에 상품별 영어 키워드 라벨을 입혀 `P0001`~`P0500` 생성 |
| `generate_skin_labeled_images.py` | 스킨 카테고리 전용 템플릿 라벨 이미지 생성 |
| **데이터 파일** | |
| `cara.db` | SQLite DB (상품 카탈로그, 임베딩 벡터) |
| `consumers.json` | 200명 소비자 프로필 |
| `benchmark_results.json` | 최신 벤치마크 결과 |
| `assets/products/` | 상품 이미지 저장소 |

## 설치

### 요구사항

- Python 3.10 이상
- pip (패키지 관리자)

### 단계별 설치

#### 1. 저장소 클론 및 디렉토리 이동

```bash
git clone https://github.com/sally014701-commits/CARA-agent.git
cd CARA-agent
```

#### 2. 가상 환경 생성 및 활성화

```bash
# Windows
python -m venv .venv
.venv\Scripts\activate

# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

#### 3. 의존성 설치

```bash
pip install -r requirements.txt
```

주요 패키지:
- `fastapi`, `uvicorn`: 웹 서버
- `sqlalchemy`: 데이터베이스 ORM
- `pydantic`: 데이터 검증
- `anthropic`: Claude API 클라이언트
- `openai`: GPT API 클라이언트
- `voyageai`: 임베딩 생성 API
- `pillow`: 상품 이미지 라벨링 및 캔버스 정규화
- `python-dotenv`: 환경 변수 로딩

#### 4. 환경 변수 설정

`.env` 파일을 프로젝트 루트에 생성:

```bash
cp .env.example .env
```

그리고 `.env`에서 API 키 입력

## 환경 변수

`.env` 파일을 프로젝트 루트에 생성합니다 (`.env.example` 참고):

```env
# Anthropic (Claude API)
ANTHROPIC_API_KEY=your_anthropic_api_key

# OpenAI (GPT-4 기반 검색어 정제, 텍스트 신호)
OPENAI_API_KEY=your_openai_api_key

# Voyage AI (임베딩 생성 및 벡터 검색)
VOYAGE_API_KEY=your_voyage_api_key
```

### API 키별 역할

| 환경 변수 | 역할 | 필수 여부 |
| --- | --- | --- |
| `ANTHROPIC_API_KEY` | Conversation Agent 대화, Persona Evaluator 평가 | 권장* |
| `OPENAI_API_KEY` | 검색어 정제, 텍스트 기반 BrainFry 신호 감지 | 권장* |
| `VOYAGE_API_KEY` | 상품 임베딩 생성, 벡터 검색 | 벡터 검색 사용시 필수 |

*키가 없어도 일부 rule-based fallback은 동작하지만, 대화 품질과 LLM 기반 신호 감지는 제한됩니다.

## 실행

### 1. 서버 시작

```bash
python main.py
```

서버가 `0.0.0.0:8000`에서 시작됩니다.

### 2. 웹 인터페이스 접속

- **사용자 화면 (추천 인터페이스)**: http://localhost:8000/
- **벤치마크 확인 페이지**: http://localhost:8000/admin.html
- **헬스 체크**: http://localhost:8000/health

### 3. 임베딩 생성 (선택사항)

벡터 기반 검색을 사용하려면 상품 임베딩을 먼저 생성해야 합니다.

```bash
# 한 번만 실행: 스키마 생성
python manage_embeddings.py ensure-schema

# 상품 임베딩 생성 (배치 크기 20, 배치 간 대기 0.5초)
python manage_embeddings.py embed-products --batch-size 20 --sleep 0.5

# 임베딩된 상품 개수 확인
python manage_embeddings.py count

# 특정 상품의 유사 상품 조회
python manage_embeddings.py similar --product-name "그린티 씨드 스킨" --limit 5
```

**주의**: `embed-products` 명령은 Voyage API를 호출하므로 `VOYAGE_API_KEY` 환경 변수가 필요합니다.

## 추천 파이프라인

사용자의 추천 요청부터 최종 상품 반환까지의 흐름:

### 1단계: 계획 수립 (Planner Agent)
- 사용자 입력: 상품명, 예산, 선호 스타일
- 소비자 프로필 로드: 심리 성향, 구매 이력, 현재 행동 지표
- **출력**: 추천 계획 (타겟 카테고리, 예산 범위, 스타일 선호)

### 2단계: 대화 및 신호 감지 (Conversation Agent)
- 필요시 2턴 대화로 추가 정보 수집
- 텍스트 기반 BrainFry 신호 감지 (피로, 혼란, 결정 회피)
- **출력**: 정제된 사용자 의도, 업데이트된 BrainFry score

### 3단계: 상품 검색 및 점수 계산 (Executor Agent)
- **검색 단계**: 검색 규칙 기반 후보 추출
  - 카테고리 매핑 (한국어 → 표준 카테고리)
  - 가격/스타일 필터링
  - Fallback: 유사 카테고리 확대
- **임베딩 기반 재정렬**: Voyage AI 벡터로 의미론적 유사도 계산
- **점수 통합**: 텍스트 매칭 + 임베딩 유사도 + 평점 + 감성 + 페르소나 가중치
- **출력**: 상품 ID와 점수를 내림차순으로 정렬

### 4단계: 최종 검수 (Critic Agent)
- 예산 초과 상품 제거
- 낮은 평점 상품 제거
- 스타일 다양성 확인 (한쪽 스타일 편중 시 반대 스타일 보강)
- 추천 개수 조절: `n_rec = max(1, round(7 * (1 - BrainFry)))`
- 추가 규칙: `impulsive` + 높은 BrainFry → 단일 추천으로 축소
- **출력**: 최종 추천 상품 리스트

### 5단계: 렌더링
- 프론트엔드가 상품 정보, 이미지, 표시 힌트 수신
- 사용자에게 최종 추천 화면 제공
6. 프론트엔드는 최종 추천 상품과 표시 힌트를 받아 화면에 렌더링합니다.

## 주요 API 엔드포인트

### 기본 정보
| 메서드 | 엔드포인트 | 설명 |
| --- | --- | --- |
| `GET` | `/` | CARA.html 입장 (사용자 인터페이스) |
| `GET` | `/health` | 서버 상태 확인 |
| `GET` | `/admin.html` | 벤치마크 확인 페이지 |

### 상품 검색 API
| 메서드 | 엔드포인트 | 설명 |
| --- | --- | --- |
| `GET` | `/products/search` | 키워드/가격/카테고리/스타일 기반 검색 |
| `GET` | `/products/trending` | 리뷰 수 기준 인기 상품 조회 |
| `GET` | `/products/price-distributions` | 카테고리별 가격 분포 통계 |

### 추천 에이전트 API
| 메서드 | 엔드포인트 | 설명 |
| --- | --- | --- |
| `POST` | `/api/plan` | Planner Agent 실행 (계획 수립) |
| `POST` | `/api/chat` | Conversation Agent (대화 턴, 정보 수집) |
| `POST` | `/api/recommend` | 전체 추천 파이프라인 (Planner → Executor → Critic) |

### 소비자 정보 API
| 메서드 | 엔드포인트 | 설명 |
| --- | --- | --- |
| `GET` | `/consumers/{consumer_id}/history` | 소비자 구매 이력 및 선호도 조회 |

### 관리자 API
| 메서드 | 엔드포인트 | 설명 |
| --- | --- | --- |
| `GET` | `/admin/sessions` | 진행 중/종료된 세션 목록 |
| `GET` | `/admin/sessions/{session_id}` | 세션 상세 (에이전트 타임라인, 채팅 기록) |
| `GET` | `/admin/sessions/{session_id}/stream` | 세션 트레이스 실시간 스트림 (SSE) |
| `GET` | `/admin/stats/brainfry` | BrainFry 분포 통계 |
| `POST` | `/admin/benchmark/evaluate` | 단일 추천 요청에 대한 페르소나 평가

## 데이터 스키마

### Product (cara.db - products 테이블)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `product_id` | INT | 상품 고유 ID |
| `category`, `subcategory` | TEXT | 상품 분류 |
| `product_name` | TEXT | 상품명 (기본) |
| `title_en`, `title_ko` | TEXT | 다국어 제품명 |
| `brand` | TEXT | 브랜드/가격대 라벨 |
| `price` | REAL | 상품 가격 (₩) |
| `star_rating` | REAL | 평점 (0.0 ~ 5.0) |
| `review_count` | INT | 리뷰 수 |
| `sentiment_score` | REAL | 리뷰 감성 점수 (-1.0 ~ 1.0) |
| `preference_style` | TEXT | `utilitarian` 또는 `hedonic` |
| `skin_type` | TEXT | 피부 타입 (dry, oily, combination, sensitive 등) |
| `keywords_ko` | TEXT | 한국어 검색 보조 키워드 |
| `embedding` | BLOB | Voyage AI 임베딩 벡터 (1536차원) |
| `stock_status` | INT | 재고 여부 (1: 있음, 0: 없음) |

### Consumer (consumers.json)

| 필드 | 타입 | 설명 |
| --- | --- | --- |
| `consumer_id` | INT | 소비자 고유 ID |
| `psychographic_type` | TEXT | 쇼핑 성향 (6개: utilitarian, hedonic, maximizer, value_seeker, loss_averse, impulsive) |
| `preference_style` | TEXT | 선호 스타일 (utilitarian 또는 hedonic) |
| `budget_level` | TEXT | 예산 수준 (low, mid, high) |
| `purchase_history` | LIST[INT] | 구매한 상품 ID 목록 |
| `session_behavior` | DICT | 현재 세션 행동 지표 |
| └ `page_visits` | INT | 페이지 방문 수 |
| └ `dwell_time_std` | FLOAT | 체류 시간 표준편차 |
| └ `scroll_depth` | FLOAT | 스크롤 깊이 (0.0 ~ 1.0) |
| └ `ctr` | FLOAT | 클릭 through rate |
| └ `brainfry_score` | FLOAT | 인지 과부하 점수 (0.0 ~ 1.0) |

### 세션 데이터 (SQLite - database.py)

| 테이블 | 필드 | 설명 |
| --- | --- | --- |
| `sessions` | `id`, `consumer_id`, `started_at`, `last_updated`, `status` | 추천 세션 메타데이터 |
| `chat_messages` | `id`, `session_id`, `role`, `content`, `created_at` | 대화 기록 |
| `agent_trace` | `id`, `session_id`, `agent_name`, `status`, `output_data`, `started_at` | 에이전트 실행 로그 |
| `session_events` | `id`, `session_id`, `event_type`, `event_data`, `created_at` | 세션 이벤트 타임라인 |

## BrainFry Score: 인지 과부하 지표

BrainFry(0.0 ~ 1.0)는 사용자의 인지 과부하 정도를 측정합니다. 점수가 높을수록 피로하고 결정을 내리기 어려운 상태입니다.

### 계산 요소

**행동 지표 (세션 통계):**
- 페이지 방문 수: 많을수록 증가
- 체류 시간 분산: 편차가 클수록 증가 (불안정한 탐색)
- CTR (Click-Through Rate): 낮을수록 증가 (클릭 주저)
- 재검색/수정: 많을수록 증가 (결정 불안)

**대화 신호 (텍스트 분석):**
- 피로 표현 감지 (예: "너무 힘들어요", "정신없어")
- 혼란 표현 감지 (예: "잘 모르겠어", "뭘 골라야 하지")
- 결정 회피 신호 (예: "있는 대로 추천해줘", "상관없어")

**프로필 기본값:**
- 예산 상한선이 높으면 약간 감소 (여유가 있는 상태)
- `loss_averse` 페르소나는 기본값 상향 (신중함)

### 영향

추천 개수 자동 조절:

```
n_rec = max(1, round(7 * (1 - BrainFry)))

BrainFry: 0.0  →  n_rec = 7개 (최대)
BrainFry: 0.5  →  n_rec = 4개 (중간)
BrainFry: 0.9  →  n_rec = 1개 (최소)
```

**Critic Agent의 추가 규칙:**
- BrainFry ≥ 0.7 & `impulsive` 성향 → 단일 추천으로 축소

## 점수 계산 및 검수 메커니즘

### Executor Agent: 후보 점수 계산

각 상품에 대해 다음 요소를 종합해 점수 계산 (0.0 ~ 1.0):

1. **텍스트 매칭** (20%): 검색어와 상품명/카테고리 유사도
2. **임베딩 검색** (30%): Voyage AI 벡터 코사인 유사도
3. **평점/리뷰** (15%): 별점 높음, 리뷰 수 많음
4. **감성 점수** (10%): 리뷰 텍스트의 긍정 감성
5. **페르소나 가중치** (25%): 사용자 심리 성향에 맞는 상품 보정
   - `utilitarian`: 기능성/가성비 강조 상품 ↑
   - `hedonic`: 럭셔리/프리미엄 상품 ↑
   - `maximizer`: 평점/리뷰 많은 상품 ↑
   - `value_seeker`: 가격 대비 성능 ↑
   - `loss_averse`: 안정적(평점 높음) 상품 ↑
   - `impulsive`: 핫트렌드/신상품 ↑

### Critic Agent: 최종 검수 규칙

후보 리스트를 아래 순서로 검수:

1. **예산 필터링**: 예산 초과 상품 제거
2. **품질 필터링**: 평점 3.0 미만 상품 제거
3. **스타일 다양성**: 
   - 모든 후보가 동일 스타일(utilitarian 또는 hedonic)이면
   - 반대 스타일 상품 일부 보강 (점수 우수 순)
4. **개수 조절**: BrainFry 기반 최적 추천 개수로 top-N 선택
5. **이상 조건 처리**:
   - 후보 부족 시: 예산 상한선 완화 (1단계: 10%, 2단계: 20%)
   - `impulsive` + BrainFry ≥ 0.7: 단일 추천으로 축소 (최고 점수만)

## 벤치마크 실행

### 자동 벤치마크

서버를 먼저 실행한 뒤 별도 터미널에서:

```bash
python benchmark_runner.py
```

벤치마크는 20개 시나리오를 대상으로 CARA 추천과 인기순 baseline을 자동 비교하고 `benchmark_results.json`을 갱신합니다.

**평가 지표:**
- **평균 만족도**: CARA 추천 만족도 vs Baseline 만족도
- **Hit@N**: Top-N 추천에서 사용자 선호도와 맞는 상품 비율
- **예산 준수율**: 예산 범위 내 추천 비율
- **선호 스타일 정렬도**: 사용자 선호 스타일 반영도

### 페르소나 평가

관리자 API를 통해 단일 추천에 대한 페르소나별 평가:

```bash
POST /admin/benchmark/evaluate
{
  "consumer_id": 1,
  "query": "보습 로션",
  "budget_min": 30000,
  "budget_max": 80000
}
```

6개 페르소나(Utilitarian, Hedonic, Maximizer, Value Seeker, Loss Averse, Impulsive) 관점에서 추천 품질을 평가합니다.
- BrainFry 감소 추정치
- 페르소나별 만족도와 결정 용이성

## 데이터와 이미지 재생성

상품/소비자 데이터를 다시 생성합니다.

```bash
python generate_synthetic_dataset.py
```

상품 이미지를 다시 생성합니다.

```bash
python generate_product_images.py
```

이미지는 `assets/products/{product_id}.png` 경로에 저장됩니다.

## 개발 참고

- 서버 실행 시 `cara.db`의 상품과 `consumers.json`의 소비자 프로필을 메모리에 로드합니다.
- 세션 로그는 `cara_sessions.db` SQLite 파일에 저장됩니다.
- `cara.db`, `cara_sessions.db`, `.env`는 로컬 실행 산출물로 취급하는 것이 좋습니다.
- 에이전트 단독 예시는 각 파일의 `main()`에서 실행할 수 있지만, 대부분 FastAPI 서버가 켜져 있어야 정상 동작합니다.
