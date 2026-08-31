# 블로거 자동 발행

`blogger-posts/` 에 글 파일을 넣고 main에 올리면, GitHub Actions가 **worldtraveler111.blogspot.com** 에 자동으로 발행합니다.

- 처음이면 → 새 글로 발행
- 내용을 고쳐서 다시 올리면 → **기존 글을 수정** (중복 발행 안 됨)
- 바뀐 게 없으면 → 건너뜀

---

## 1회 설정 (약 10분)

한 번만 해두면 이후에는 글만 추가하면 됩니다.

### ① 구글 클라우드에서 Blogger API 켜기

1. https://console.cloud.google.com 접속 (블로그 소유 계정으로 로그인)
2. 상단에서 **프로젝트 만들기** → 이름은 아무거나 (예: `blog-auto`)
3. 검색창에 `Blogger API` 입력 → **Blogger API v3** 선택 → **사용 설정**

### ② OAuth 동의 화면 만들기

1. 좌측 메뉴 **API 및 서비스 → OAuth 동의 화면**
2. User Type: **외부** 선택 → 만들기
3. 앱 이름/이메일만 채우고 저장 (나머지는 기본값)
4. **대상(Audience)** 화면에서 **테스트 사용자**에 본인 구글 계정 추가
   - 이걸 빠뜨리면 인증할 때 "액세스 차단됨" 오류가 납니다

### ③ OAuth 클라이언트 ID 발급

1. **API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기 → OAuth 클라이언트 ID**
2. 애플리케이션 유형: **데스크톱 앱** 선택 (중요)
3. 만들어지면 **클라이언트 ID**와 **클라이언트 보안 비밀번호**를 복사해 둡니다

### ④ 리프레시 토큰 받기 (본인 PC에서 1회)

본인 컴퓨터 터미널에서 실행하세요. 브라우저가 열리고 구글 로그인 → 권한 허용하면 토큰이 출력됩니다.

```bash
pip install requests
python3 .github/scripts/blogger-get-token.py <클라이언트ID> <클라이언트보안비밀번호>
```

출력된 `BLOGGER_REFRESH_TOKEN` 값을 복사해 둡니다. (비밀번호나 마찬가지이니 외부에 공유하지 마세요.)

### ⑤ GitHub에 비밀값 등록

저장소 → **Settings → Secrets and variables → Actions → New repository secret** 에서 3개를 등록합니다.

| 이름 | 값 |
|---|---|
| `BLOGGER_CLIENT_ID` | ③에서 받은 클라이언트 ID |
| `BLOGGER_CLIENT_SECRET` | ③에서 받은 보안 비밀번호 |
| `BLOGGER_REFRESH_TOKEN` | ④에서 출력된 토큰 |

블로그 주소는 코드에 기본값(`https://worldtraveler111.blogspot.com`)으로 들어가 있어서 따로 등록할 필요가 없습니다. 다른 블로그에 올리려면 같은 화면의 **Variables** 탭에서 `BLOGGER_BLOG_URL` 을 추가하세요.

---

## 글 올리는 법

`blogger-posts/` 안에 `.html` 파일을 만들면 됩니다. 파일 이름(확장자 제외)이 글의 식별자가 되므로, 한번 정하면 바꾸지 마세요 (바꾸면 새 글로 다시 발행됩니다).

```
---
title: 글 제목
labels: 영화, 영화리뷰, 크리스토퍼놀란
search_description: 검색 결과에 뜨는 설명입니다.
status: LIVE
---
<p>본문 HTML을 여기에 씁니다.</p>
```

- `status: LIVE` → 바로 공개 발행 / `status: DRAFT` → 초안으로만 저장
- `labels` → 블로거의 라벨(태그), 쉼표로 구분
- 이미지는 홈페이지에 올려둔 주소를 그대로 쓰면 됩니다 (`https://danielmoon82.github.io/moon/posts/images/...`)

## 발행 실행

- **자동**: `blogger-posts/*.html` 을 수정해서 main에 올리면 자동 실행
- **수동**: 저장소 → **Actions → Publish to Blogger → Run workflow**
  - `slug` 칸에 파일명(확장자 제외)을 넣으면 그 글만 발행

발행 결과(글 ID·주소)는 `data/blogger-published.json` 에 자동 기록됩니다. 이 파일이 중복 발행을 막아주므로 임의로 지우지 마세요.

## 수익화

블로거는 애드센스 연동이 가장 쉬운 플랫폼입니다. 블로거 관리화면 → **수익 창출** 에서 애드센스를 연결하면 글 사이·본문 중간에 광고가 자동 배치됩니다. 글마다 광고 코드를 넣을 필요가 없습니다.
