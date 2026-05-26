import os
from pathlib import Path

import anthropic as _anthropic
import openai as _openai
from dotenv import load_dotenv


load_dotenv(Path(__file__).parent / ".env", override=True)


def _ensure_env_file():
    env_path = Path(".env")
    if not env_path.exists():
        env_path.write_text(
            "ANTHROPIC_API_KEY=\nOPENAI_API_KEY=\n",
            encoding="utf-8",
        )


def _get_api_key(key_name: str, friendly_name: str) -> str:
    value = os.getenv(key_name, "").strip()
    if value:
        return value

    if os.getenv("CODEX_ENV") or os.getenv("CI") or not os.isatty(0):
        print(f"[경고] {key_name} 환경변수가 없습니다. .env 파일에 추가하세요.")
        return ""

    try:
        value = input(f"{friendly_name} API 키를 입력하세요: ").strip()
    except EOFError:
        print(f"[경고] {key_name} 환경변수가 없습니다. .env 파일에 추가하세요.")
        return ""

    if value:
        env_path = Path(".env")
        existing = env_path.read_text(encoding="utf-8") if env_path.exists() else ""
        if key_name in existing:
            lines = [
                f"{key_name}={value}" if line.startswith(key_name) else line
                for line in existing.splitlines()
            ]
            env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        else:
            with env_path.open("a", encoding="utf-8") as f:
                f.write(f"{key_name}={value}\n")
        os.environ[key_name] = value
    return value


_ensure_env_file()
ANTHROPIC_API_KEY = _get_api_key("ANTHROPIC_API_KEY", "Anthropic (Claude)")
OPENAI_API_KEY = _get_api_key("OPENAI_API_KEY", "OpenAI (GPT)")


class BrainFryTextDetector:
    def __init__(self):
        self.client = _openai.OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

    def detect(self, utterance: str) -> float:
        if not self.client or not utterance or len(utterance.strip()) < 2:
            return 0.0

        prompt = f"""당신은 소비자 발화에서 인지 과부하(cognitive overload) 강도를 감지하는 분류기입니다.

인지 과부하 언어 마커:
- 불확실성: 모르겠어, 뭘 사야 할지, 다 비슷해 보여
- 비교 피로: 너무 많아, 계속 보고 있는데, 지쳤어
- 결정 포기: 그냥 아무거나, 골라줘, 추천만 해줘
- 혼란: 헷갈려, 차이를 모르겠어
- 좌절: 그냥 안 살까봐, 너무 복잡해

분석할 발화: "{utterance}"

인지 과부하 강도를 0.0~1.0 숫자 하나로만 출력하라."""

        try:
            resp = self.client.chat.completions.create(
                model="gpt-4o-mini",
                max_tokens=5,
                temperature=0,
                messages=[{"role": "user", "content": prompt}],
            )
            return round(min(max(float(resp.choices[0].message.content.strip()), 0.0), 1.0), 2)
        except Exception:
            return 0.0


SYSTEM_PROMPT = """당신은 CARA(Context-Aware Recommendation Agent)의 대화 에이전트입니다.
소비자와 정확히 2턴의 구조화된 대화를 나눠 추천에 필요한 정보를 확인합니다.

[Turn 1 - 추론 요약 제시]
반드시 아래 형식으로 출력하라 (단, 사용자가 처음부터 "바로 추천", "즉시 추천" 등 바로 추천을 시작하라고 요청하는 경우에는 이 형식을 생략하고 즉시 "알겠습니다! 지금 바로 추천을 시작할게요." 라고 대답하십시오):
"안녕하세요! 고객님의 브라우징 패턴을 분석했어요. 아래 내용이 맞나요?
- 찾고 계신 것: {category}
- 예산: {budget}원 이하
- 선호 스타일: {style}
- 인지 부하 상태: {brainfry_level}

혹시 다른 점이 있다면 알려주세요!"

[Turn 2 - 수정 사항 처리]
소비자가 수정 사항을 말하면 해당 필드만 업데이트하고 나머지는 유지.
수정이 없으면 "알겠습니다! 지금 바로 추천을 시작할게요." 라고 응답.

[BrainFry HIGH 상태일 때만 추가]
Turn 1 마지막에 추가:
"지금 선택이 얼마나 어렵게 느껴지시나요? (1=매우 쉬움, 5=매우 어려움)"

[인지 과부하 발화 감지 시 즉시 반응]
소비자가 혼란, 피로, 결정 포기 신호를 보이면 다음과 같이 응답:
"많이 힘드셨겠어요. 제가 딱 맞는 것 하나만 골라드릴게요."
이후 N_rec을 자동으로 줄여 추천을 단순화한다.

[주의사항 - 절대 준수]
- 당신은 직접 상품 데이터베이스를 검색하거나 상품 리스트를 실시간으로 가져올 수 없습니다. 하지만 절대로 이를 언급하거나 "데이터베이스에 접근할 수 없다"는 식의 대답을 하지 마십시오.
- 사용자가 상품 추천을 해달라고 요구하면, 현재 파악된 예산, 스타일 등의 상황을 요약하여 알려주고, 확인 또는 수정 의견을 묻는 방향으로만 대답을 유도하십시오.
- 이미 사용자가 충분한 조건(예산, 카테고리 등)을 주었거나 바로 추천을 시작하라고 명시적으로 말한 경우, 또는 2턴이 끝난 경우 즉시 대화를 끝내고 추천으로 넘어가도록 "알겠습니다! 지금 바로 추천을 시작할게요."라고 응답하십시오.

항상 한국어로 응답하라. 친근하되 간결하게."""


class ConversationAgent:
    def __init__(self):
        self.anthropic_client = _anthropic.Anthropic(api_key=ANTHROPIC_API_KEY) if ANTHROPIC_API_KEY else None
        self.detector = BrainFryTextDetector()

    def run_turn(self, messages: list, plan_context: dict) -> dict:
        last_user_content = messages[-1]["content"] if messages else ""
        b_text = self.detector.detect(last_user_content)

        updated_context = dict(plan_context)
        updated_context["text_brainfry_score"] = b_text

        current_level = updated_context.get("brainfry_level", "LOW")
        if b_text >= 0.5 and current_level == "LOW":
            updated_context["brainfry_level"] = "MID"
        elif b_text >= 0.8 and current_level in ("LOW", "MID"):
            updated_context["brainfry_level"] = "HIGH"

        b_behavioral = float(updated_context.get("brainfry_score", 0.0)) / 0.7
        b_self = float(updated_context.get("self_report_score", 0.0))
        b_final_new = round(min(0.7 * b_behavioral + 0.2 * b_self + 0.1 * b_text, 1.0), 4)
        updated_context["brainfry_score"] = b_final_new
        updated_context["n_rec"] = max(1, round(7 * (1 - b_final_new)))

        system = SYSTEM_PROMPT
        system = system.replace("{category}", updated_context.get("top_category") or "상품")
        system = system.replace("{budget}", str(updated_context.get("budget_ceiling", 200000)))
        style_label = "감성적" if updated_context.get("preferred_style") == "hedonic" else "실용적"
        system = system.replace("{style}", style_label)
        system = system.replace("{brainfry_level}", updated_context.get("brainfry_level", "LOW"))

        reply = "[API 키 없음 - 테스트 응답]"
        if self.anthropic_client:
            try:
                response = self.anthropic_client.messages.create(
                    model="claude-sonnet-4-5",
                    max_tokens=500,
                    system=system,
                    messages=messages,
                )
                reply = response.content[0].text
            except Exception as e:
                reply = f"[오류: {e}]"

        turn_complete = (
            len(messages) >= 3 
            or "추천을 시작할게요" in reply 
            or "추천을 시작합니다" in reply
            or "추천해 드릴게요" in reply
            or "추천해 드리겠습니다" in reply
        )

        import re

        last_msg = last_user_content.lower()
        numbers = re.findall(r"\d[\d,]*", last_msg.replace(",", ""))
        if ("예산" in last_msg or "원" in last_msg) and numbers:
            val = int(numbers[0])
            if "만" in last_msg and val < 10000:
                val *= 10000
            updated_context["budget_ceiling"] = val
            updated_context["budget_source"] = "explicit_chat_correction"

        if any(w in last_msg for w in ["실용", "기능", "편한", "utilitarian"]):
            updated_context["preferred_style"] = "utilitarian"
        elif any(w in last_msg for w in ["디자인", "감성", "예쁜", "hedonic"]):
            updated_context["preferred_style"] = "hedonic"

        self_report_score = None
        score_match = re.search(r"\b([1-5])\b", last_msg)
        if score_match and updated_context.get("brainfry_level") == "HIGH":
            raw = int(score_match.group(1))
            self_report_score = round((raw - 1) / 4.0, 2)
            updated_context["self_report_score"] = self_report_score

        return {
            "reply": reply,
            "updated_context": updated_context,
            "turn_complete": turn_complete,
            "self_report_score": self_report_score,
            "b_text": b_text,
        }
