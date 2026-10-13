# 공공데이터 활용 명세 · 합성데이터 작성 기준

이음24는 공공데이터(고용24 OpenAPI·공개 지침)와 **실제 형식과 같은 합성(모의)데이터**로 동작합니다.
공공 API 일부는 개인 신청이 어렵거나 승인에 시간이 걸리므로, **실제 API 응답과 항목명·형식이 같은 합성데이터**를 먼저 만들고
승인 후에는 데이터만 실제로 바꿔 끼웁니다.

## 0. 꼭 지킬 규칙

- **실제 개인정보·실존 기업 정보 금지.** 사람은 가명(예: 김하늘), 기업은 가상 이름에 `(가상)`을 붙입니다.
- **사업자등록번호는 `000-`으로 시작**하는 가짜 번호만 씁니다 (예: `000-81-00012`). 실제 번호와 겹치지 않게 하기 위함입니다.
- **항목명(영문 태그·키)은 이 문서와 똑같이** 씁니다. 바꾸면 코드가 읽지 못합니다.
- 날짜는 `YYYY-MM-DD`(API 원형이 `YYYYMMDD`면 그 형식), 금액은 숫자만(원 단위, 쉼표 없음).
- 파일은 `data/synthetic/` 아래에 둡니다. 작업은 브랜치(A: `seeker-data`, B: `company-data`)에서 하고 Pull Request로 올립니다.
- 정상 사례만이 아니라 **점검에 걸려야 하는 오류 사례**도 섞습니다 (각 데이터의 "오류 사례" 참고). 사례마다 `note`에 의도를 적습니다.
- `data/synthetic/`에 **예시 파일이 이미 들어 있습니다.** 복사해서 늘리는 방식으로 작업하세요.

## 작업 → 점검 → 화면 확인 순서

1. 예시 파일을 복사해 데이터를 늘립니다.
2. **자가 점검**: `python3 tools/check_synthetic.py`
   - 항목 빠짐·사업자번호 규칙·파일 연결 오류를 알려 주고(✖ = 꼭 고칠 것),
   - 일부러 넣은 오류 사례를 서비스 점검 기능이 실제로 잡는지 ✅/❌ 로 보여 줍니다(`expect`에 적은 기대 결과와 비교).
3. **화면 확인**: `python3 dev_server.py` → http://127.0.0.1:3000
   - 구직자 화면 '예시 불러오기'에 `seekers.json`의 구직자가, 기업 화면 예시 목록에 `work24_postings.xml`의 공고가 추가됩니다.
   - 공고에는 사업자번호로 기업 정보(피보험자 수·우선지원 여부)와 임금체불 조회 결과가 자동으로 붙습니다.
   - 브랜치에 올리면 PR의 미리보기 주소에서도 같은 화면을 볼 수 있습니다.
4. 자동 테스트(`python3 -m pytest -q tests`)는 내장 데이터 기준으로 돌아가므로, 합성 파일을 바꿔도 깨지지 않습니다.

## 1. 공공데이터 활용 명세

| 연번 | 출처 | 데이터명 | 서비스 URL | 담당 | 합성 파일 |
|---|---|---|---|---|---|
| 1 | 고용24(한국고용정보원) | 채용정보 목록 (OpenAPI) | https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do | A | `data/synthetic/work24_postings.xml` |
| 2 | 고용24(한국고용정보원) | 임금체불 명단공개 사업주 여부 (OpenAPI) | https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L41.do | B | `data/synthetic/work24_arrears.xml` |
| 3 | 고용노동부(공개 문서) | 2026년 청년일자리도약장려금 사업운영 지침 | https://www.moel.go.kr/news/notice/noticeView.do?bbs_seq=20260400705 | 팀장 | `core/rules.py` (규칙DB) |
| 4 | 모의데이터 | 구직자 참여 이력 (국민취업지원제도·청년도전지원사업) | - | A | `data/synthetic/seekers.json` |
| 5 | 모의데이터 | 고용보험 피보험 이력 | - | A | `data/synthetic/seekers.json` (구직자별 `insurance`) |
| 6 | 모의데이터 | 근로계약서 | https://www.moel.go.kr/policy/policydata/view.do?bbs_seq=20250300356 (표준근로계약서 참고) | B | `data/synthetic/contracts.json` |
| 7 | 모의데이터 | 급여명세서 | - | B | `data/synthetic/docs/` + `docs_answer.json` |
| 8 | 모의데이터 | 이체확인증 | - | B | `data/synthetic/docs/` + `docs_answer.json` |
| 9 | 모의데이터 | 채용공고·기업 정보 (시연용) | - | B | `data/synthetic/companies.json` |

연결 키: **사업자등록번호** — 채용정보의 `busino` = 기업 정보의 `busino` = 임금체불 조회의 `brno`.

## 2. 고용24 API 형식 (실제 응답과 같은 구조)

### 연번 1 · 채용정보 목록 `work24_postings.xml` — 목표 20건 (A)

`<wanted>` 하나가 공고 1건입니다. 26개 항목을 모두 채웁니다.

```xml
<wantedRoot>
  <total>20</total><startPage>1</startPage><display>20</display>
  <wanted>
    <wantedAuthNo>K000000001</wantedAuthNo>   <!-- 구인인증번호: K + 9자리, 겹치지 않게 -->
    <company>한빛소프트랩(가상)</company>       <!-- 회사명 -->
    <busino>0008100012</busino>                 <!-- 사업자등록번호(하이픈 없이 10자리, 000으로 시작) -->
    <indTpNm>소프트웨어 개발 및 공급업</indTpNm> <!-- 업종 -->
    <title>웹 프론트엔드 개발자 (신입)</title>    <!-- 채용제목 -->
    <salTpNm>월급</salTpNm>                     <!-- 임금형태: 월급/연봉/시급 -->
    <sal>280만원 ~ 300만원</sal>                 <!-- 급여(표시용) -->
    <minSal>2800000</minSal>                     <!-- 최소임금액 -->
    <maxSal>3000000</maxSal>                     <!-- 최대임금액 -->
    <region>서울 마포구</region>                  <!-- 근무지역 -->
    <holidayTpNm>주5일근무</holidayTpNm>          <!-- 근무형태 -->
    <minEdubg>학력무관</minEdubg>                 <!-- 최소학력 -->
    <maxEdubg></maxEdubg>                         <!-- 최대학력 -->
    <career>신입</career>                         <!-- 경력 -->
    <regDt>20261001</regDt>                       <!-- 등록일자 -->
    <closeDt>20261031</closeDt>                   <!-- 마감일자 -->
    <infoSvc>VALIDATION</infoSvc>                 <!-- 정보제공처 -->
    <wantedInfoUrl>https://www.work24.go.kr/</wantedInfoUrl>       <!-- 채용정보 URL (가상 공고는 메인 주소) -->
    <wantedMobileInfoUrl>https://m.work24.go.kr/</wantedMobileInfoUrl>
    <zipCd>04000</zipCd>                          <!-- 근무지 우편주소 -->
    <strtnmCd>0</strtnmCd>                        <!-- 근무지 도로명주소 코드 -->
    <basicAddr>서울특별시 마포구 가상로 1</basicAddr> <!-- 근무지 기본주소 -->
    <detailAddr>2층</detailAddr>                  <!-- 근무지 상세주소 -->
    <empTpCd>10</empTpCd>                         <!-- 고용형태코드: 10·11 기간의 정함 없음 / 20·21 기간의 정함 있음 -->
    <jobsCd>133100</jobsCd>                       <!-- 직종코드 -->
    <smodifyDtm>202610010900</smodifyDtm>         <!-- 최종수정일 -->
  </wanted>
  <!-- … 20건 … -->
</wantedRoot>
```

다양하게 구성할 것: 수도권/비수도권, 정규직(10·11)/기간제(20·21), 직무 5종 이상(웹 개발·사무·물류·품질·디자인 등).
**오류 사례 2건 이상**: 월급이 최저임금 미달인 공고, 마감일이 지난 공고.

### 연번 2 · 임금체불 명단공개 사업주 여부 `work24_arrears.xml` — 기업 12곳 (B)

요청: 사업자등록번호(`brno`)로 1건씩 조회. 기업 정보(연번 9)의 모든 `busino`에 대해 1건씩 만듭니다.

```xml
<jdgnList>
  <lnkReqNo>1</lnkReqNo>              <!-- 연계요청번호 -->
  <lnkSucsYn>Y</lnkSucsYn>            <!-- 연계성공여부 Y/N -->
  <brno>0008100012</brno>             <!-- 사업자등록번호 -->
  <bzmn>00000000001</bzmn>            <!-- 사업장관리번호(가상) -->
  <judgReltYn>N</judgReltYn>          <!-- 임금체불 명단공개 사업주 여부 Y=대상 / N=비대상 -->
  <errMsgCd></errMsgCd>               <!-- 오류코드 (예: ERR0001 API KEY 오류, ERR0011 사업장 정보 없음) -->
  <errMsg></errMsg>                   <!-- 오류내용 -->
</jdgnList>
```

**오류 사례**: `judgReltYn=Y` 1곳, 조회 실패(`lnkSucsYn=N`, `errMsgCd=ERR0011`) 1곳.

## 3. 모의데이터 형식

### 연번 4·5 · 구직자 `seekers.json` — 8~10명 (A)

현재 코드(`core/synthetic.py`의 `PERSONAS`)와 같은 구조입니다.

```json
[
  {
    "id": "P-05", "alias": "정다온", "age": 26, "label": "청년도전지원사업 수료",
    "programs": [
      {"type": "청년도전지원사업", "track": "단기 프로그램", "started": "2026-03-02", "completed": "2026-05-29", "status": "수료"}
    ],
    "activities": [
      {"kind": "훈련", "name": "데이터 분석 기초 (엑셀·SQL)", "hours": 120, "done": "2026-07-10"},
      {"kind": "프로젝트", "name": "지역 상권 매출 대시보드 제작", "done": "2026-07-01"}
    ],
    "insurance": [{"company": "○○마트(아르바이트)", "acquired": "2025-01-02", "lost": "2025-06-30"}],
    "desire": {"job": "사무·데이터", "region": "경기"},
    "note": "청년도전 수료 + 참여 전 단기 근로 이력"
  }
]
```

- `programs[].type`: `국민취업지원제도`(필드: `track` I유형/II유형, `qualified` 수급자격 인정일, `iap` 취업활동계획 수립일, `status`) 또는 `청년도전지원사업`(`track`, `started`, `completed`, `status` 수료/참여 중)
- `activities[].kind`: 상담 / 훈련 / 프로젝트 / 직무체험 / 자격
- 섞을 것: 국취 참여 후 취업 이력 없음, 국취 참여 **후** 이미 취업(배지 비대상), 청년도전 미수료, 참여 이력 없음, 만 34세·35세 경계

### 연번 6 · 근로계약서 `contracts.json` (B)

키는 근로계약 점검 코드(`core/labor.py`)의 입력과 같습니다.

```json
[
  {
    "id": "C-01", "worker": "김하늘", "busino": "0008100012",
    "employment_type": "정규직", "start_date": "2026-03-03", "end_date": "",
    "wage_type": "월급", "base_wage": 2600000, "allowances": 0,
    "weekly_hours": 40, "daily_hours": 8, "break_minutes": 60,
    "has_holiday": true, "has_leave": true, "has_place": true, "has_job": true, "has_payday": true,
    "expect": "적정", "note": "정상"
  }
]
```

`expect`: 기대하는 점검 결과 — `적정` / `확인 필요` / `위반 의심`.

**오류 사례 각 1건 이상**: 최저임금 미달, 휴게시간 부족(8시간에 30분), 주 40시간 초과, 필수 기재사항 누락(`has_*` 중 하나 false), 기간제인데 `end_date` 없음.

### 연번 7·8 · 급여명세서·이체확인증 `docs/` + `docs_answer.json` (B)

- 이미지(`.png`/`.jpg`)로 만듭니다. 양식 2~3종(기업·은행마다 배치가 다르게). 현재 생성기: `js/claimdocs.js`.
- 이미지마다 **정답값**을 `docs_answer.json`에 적습니다. AI 판독 결과와 비교하는 기준입니다.
- 같은 달 명세서와 이체확인증은 같은 `case` 값으로 묶고, `expect`에 기대 결과(`일치` / `확인 필요` / `불일치`)를 적습니다.
- 이미지는 `data/synthetic/docs/`에 둡니다. 기업 화면의 월별 서류 점검에 직접 올려 AI 판독을 시험할 수 있습니다(배포 환경에 AI 키 필요).

```json
[
  {"case": "A-2026-08", "file": "docs/payslip_A_2026-08.png", "kind": "payslip", "name": "김하늘", "ym": "2026-08", "gross": 2600000, "net": 2301000, "pay_date": "2026-09-10", "expect": "불일치", "note": "실지급액과 이체액 3만원 차이"},
  {"case": "A-2026-08", "file": "docs/transfer_A_2026-08.png", "kind": "transfer", "recipient": "김하늘", "date": "2026-09-10", "amount": 2271000, "expect": "불일치", "note": "실지급액과 이체액 3만원 차이"}
]
```

**오류 사례**: 실지급액≠이체액, 성명 불일치, 귀속월 불일치, 최저임금 미달.

### 연번 9 · 채용공고·기업 정보 `companies.json` — 12곳 (B)

```json
[
  {
    "busino": "0008100012", "company": "한빛소프트랩(가상)", "indTpNm": "소프트웨어 개발 및 공급업",
    "region": "서울 마포구", "insured": 18, "priority": true,
    "weekly_hours": 40, "note": "수도권·우선지원대상기업·정상"
  }
]
```

- `insured`: 피보험자 수, `priority`: 우선지원대상기업 여부
- 섞을 것: 비수도권 기업, 피보험자 5인 미만, 우선지원대상 아님

## 4. 실제 공공데이터 연동 계획 (팀장)

| 데이터 | 상태 | 활용 |
|---|---|---|
| 국세청 사업자등록 상태조회 (공공데이터포털) | 계획 — 인증키 보유, 연동 코드 준비 | 기업 사업자번호로 계속·휴업·폐업 확인 → 휴·폐업 사업장 사전 안내 |
| 국민연금 가입 사업장 내역 (공공데이터포털) | 검토 — 활용신청 필요 | 업종·가입자 수로 지원 제외 업종·기업 규모 사전 점검 (사업자번호 앞 6자리만 공개 → 사업장명·주소로 매칭) |
| 고용24 채용정보·임금체불 명단공개 | 승인 후 전환 | 위 합성 XML을 실제 응답으로 교체 (`core/work24.py`, 키: `WORK24_KEY`) |

인증키는 코드·채팅에 쓰지 않고 Vercel 환경 변수에만 넣습니다.
